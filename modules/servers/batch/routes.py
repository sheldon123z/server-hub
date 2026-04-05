"""Fleet 批量操作 API 路由"""

import json
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from auth.dependencies import require_permission
from database import get_db
from modules.agents.stream_bridge import END_SENTINEL, HEARTBEAT_SENTINEL, StreamEvent, get_stream_bridge
from modules.servers.batch.executor import get_batch_executor
from modules.servers.batch.models import BatchJobCreate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["批量操作"])

# ─── 模板 ───


@router.get("/templates")
async def list_templates(user=Depends(require_permission("servers", "read"))):
    """列出所有批量操作模板"""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM batch_templates ORDER BY is_builtin DESC, created_at DESC")
    rows = await cursor.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        d["stop_on_failure"] = bool(d["stop_on_failure"])
        d["is_builtin"] = bool(d["is_builtin"])
        result.append(d)
    return result


# ─── 历史列表（必须在 /{job_id} 之前注册） ───


@router.get("/history")
async def list_batch_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    user=Depends(require_permission("servers", "read")),
):
    """分页查询批量任务历史"""
    db = await get_db()

    where = "WHERE status = ?" if status else ""
    params: list = [status] if status else []
    params += [limit, offset]

    cursor = await db.execute(
        f"SELECT * FROM batch_jobs {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
        params,
    )
    rows = await cursor.fetchall()

    cursor2 = await db.execute(
        f"SELECT COUNT(*) FROM batch_jobs {where}",  # noqa: S608
        [status] if status else [],
    )
    total = (await cursor2.fetchone())[0]

    items = []
    for row in rows:
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        d["server_ids"] = json.loads(d["server_ids"])
        d["stop_on_failure"] = bool(d["stop_on_failure"])
        d["progress"] = json.loads(d["progress"]) if d.get("progress") else None
        items.append(d)

    return {"items": items, "total": total, "limit": limit, "offset": offset}


# ─── 创建批量任务 ───


@router.post("/execute")
async def create_batch_job(
    body: BatchJobCreate,
    user=Depends(require_permission("servers", "execute")),
):
    """创建并立即提交批量任务"""
    job_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    db = await get_db()

    await db.execute(
        """INSERT INTO batch_jobs
           (id, name, type, payload, server_ids, strategy, rolling_batch_size,
            stop_on_failure, status, created_by, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
        (
            job_id,
            body.name,
            body.type,
            json.dumps(body.payload),
            json.dumps(body.server_ids),
            body.strategy,
            body.rolling_batch_size,
            1 if body.stop_on_failure else 0,
            user.get("username"),
            now,
        ),
    )
    await db.commit()

    # 后台异步执行，立即返回 job_id
    executor = get_batch_executor()
    await executor.submit(job_id)

    return {"ok": True, "id": job_id}


# ─── 查询单个任务 ───


@router.get("/{job_id}")
async def get_batch_job(
    job_id: str,
    user=Depends(require_permission("servers", "read")),
):
    """获取批量任务状态和每台服务器的执行结果"""
    db = await get_db()

    cursor = await db.execute("SELECT * FROM batch_jobs WHERE id = ?", (job_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"批量任务 {job_id} 不存在")

    job = dict(row)
    job["payload"] = json.loads(job["payload"])
    job["server_ids"] = json.loads(job["server_ids"])
    job["stop_on_failure"] = bool(job["stop_on_failure"])
    job["progress"] = json.loads(job["progress"]) if job.get("progress") else None

    cursor = await db.execute(
        "SELECT * FROM batch_job_results WHERE job_id = ? ORDER BY started_at",
        (job_id,),
    )
    results = [dict(r) for r in await cursor.fetchall()]
    job["results"] = results

    return job


# ─── 取消任务 ───


@router.post("/{job_id}/cancel")
async def cancel_batch_job(
    job_id: str,
    user=Depends(require_permission("servers", "execute")),
):
    """取消正在运行的批量任务"""
    db = await get_db()
    cursor = await db.execute("SELECT status FROM batch_jobs WHERE id = ?", (job_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"批量任务 {job_id} 不存在")

    if row["status"] not in ("pending", "running"):
        raise HTTPException(status_code=409, detail=f"任务状态为 {row['status']}，无法取消")

    executor = get_batch_executor()
    cancelled = await executor.cancel(job_id)

    # 若任务还在 pending（尚未提交到执行器），直接更新 DB
    if not cancelled:
        await db.execute(
            "UPDATE batch_jobs SET status = 'cancelled', completed_at = ? WHERE id = ?",
            (datetime.now(UTC).isoformat(), job_id),
        )
        await db.commit()

    return {"ok": True, "cancelled": True}


# ─── SSE 实时进度 ───


@router.get("/{job_id}/stream")
async def stream_batch_job(
    job_id: str,
    user=Depends(require_permission("servers", "read")),
):
    """SSE 实时进度推送 — 订阅 StreamBridge 队列"""
    bridge = get_stream_bridge()

    if not bridge.has_queue(job_id):
        # 任务已完成或队列已清理，返回当前最终状态
        db = await get_db()
        cursor = await db.execute("SELECT status, progress FROM batch_jobs WHERE id = ?", (job_id,))
        row = await cursor.fetchone()

        async def _done_stream():
            data = {"job_id": job_id, "status": "completed"}
            if row:
                data["status"] = row["status"]
                data["progress"] = json.loads(row["progress"]) if row["progress"] else None
            yield {"event": "done", "data": json.dumps(data)}

        return EventSourceResponse(_done_stream())

    async def _consumer():
        async for entry in bridge.subscribe(job_id):
            if entry is HEARTBEAT_SENTINEL:
                yield {"comment": "heartbeat"}
                continue
            if entry is END_SENTINEL:
                return
            if isinstance(entry, StreamEvent):
                yield {"event": entry.event, "data": entry.data}

    return EventSourceResponse(_consumer())

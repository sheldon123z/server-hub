"""剧本执行路由 — 同步 SSE / 异步后台"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import require_role
from database import get_db
from modules.playbooks import services
from modules.playbooks.schemas import PlaybookRunRequest

executions_router = APIRouter()

# 防止 asyncio 任务被 GC 回收的强引用集合
_background_tasks: set[asyncio.Task] = set()


@executions_router.post("/{playbook_id}/run-async")
async def run_playbook_async(playbook_id: str, body: PlaybookRunRequest, user=Depends(require_role("admin"))):
    """后台异步执行剧本"""
    pb = await services.get_playbook(playbook_id)
    if not pb:
        raise HTTPException(404, "剧本不存在")
    # 启动后台任务
    task = asyncio.create_task(services.execute_playbook(playbook_id, body.parameters, user["username"], "manual"))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"ok": True, "message": f"剧本 '{pb['name']}' 已在后台启动执行"}


@executions_router.get("/{playbook_id}/executions")
async def list_executions(playbook_id: str, limit: int = 20, user=Depends(require_role("admin"))):
    """获取剧本执行历史"""
    db = await get_db()
    rows = await (
        await db.execute(
            "SELECT id, playbook_id, parameters_json, status, triggered_by, trigger_type, "
            "started_at, completed_at, duration_seconds, tool_calls_count "
            "FROM playbook_executions WHERE playbook_id = ? ORDER BY started_at DESC LIMIT ?",
            (playbook_id, limit),
        )
    ).fetchall()
    return [
        {
            "id": r[0],
            "playbook_id": r[1],
            "parameters_json": json.loads(r[2] or "{}"),
            "status": r[3],
            "triggered_by": r[4],
            "trigger_type": r[5],
            "started_at": r[6],
            "completed_at": r[7],
            "duration_seconds": r[8],
            "tool_calls_count": r[9],
        }
        for r in rows
    ]


@executions_router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, user=Depends(require_role("admin"))):
    """获取执行详情（含完整报告）"""
    db = await get_db()
    row = await (
        await db.execute(
            "SELECT id, playbook_id, parameters_json, status, report, triggered_by, "
            "trigger_type, started_at, completed_at, duration_seconds, thread_id, tool_calls_count "
            "FROM playbook_executions WHERE id = ?",
            (execution_id,),
        )
    ).fetchone()
    if not row:
        raise HTTPException(404, "执行记录不存在")
    return {
        "id": row[0],
        "playbook_id": row[1],
        "parameters_json": json.loads(row[2] or "{}"),
        "status": row[3],
        "report": row[4],
        "triggered_by": row[5],
        "trigger_type": row[6],
        "started_at": row[7],
        "completed_at": row[8],
        "duration_seconds": row[9],
        "thread_id": row[10],
        "tool_calls_count": row[11],
    }

"""故障报告 + 案例库 + 事件路由"""

import contextlib
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

logger = logging.getLogger(__name__)

from auth.dependencies import require_role
from database import get_db

router = APIRouter()


# ─── 故障报告 ───


@router.get("/fault-reports")
async def list_fault_reports(limit: int = 20, status: str = "", user=Depends(require_role("admin"))):
    """获取故障报告列表"""
    db = await get_db()
    if status:
        cursor = await db.execute(
            "SELECT id, detected_at, source, severity, root_cause, status FROM fault_reports "
            "WHERE status = ? ORDER BY detected_at DESC LIMIT ?",
            (status, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT id, detected_at, source, severity, root_cause, status FROM fault_reports "
            "ORDER BY detected_at DESC LIMIT ?",
            (limit,),
        )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "detected_at": r[1],
            "source": r[2],
            "severity": r[3],
            "root_cause": (r[4] or "")[:200],
            "status": r[5],
        }
        for r in rows
    ]


@router.get("/fault-reports/{report_id}")
async def get_fault_report(report_id: str, user=Depends(require_role("admin"))):
    """获取故障报告详情"""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM fault_reports WHERE id = ?", (report_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "报告不存在")
    cols = [d[0] for d in cursor.description]
    result = dict(zip(cols, row))
    # 解析 JSON 字段
    for field in (
        "affected_components",
        "symptoms",
        "evidence",
        "immediate_actions",
        "long_term_solutions",
        "similar_cases",
    ):
        if result.get(field):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                result[field] = json.loads(result[field])
    return result


@router.put("/fault-reports/{report_id}/resolve")
async def resolve_fault_report(report_id: str, user=Depends(require_role("admin"))):
    """标记故障报告为已解决"""
    db = await get_db()
    await db.execute(
        "UPDATE fault_reports SET status = 'resolved', resolved_at = ? WHERE id = ?",
        (datetime.now().isoformat(), report_id),
    )
    await db.commit()
    return {"ok": True}


# ─── 案例库 ───


@router.get("/fault-cases")
async def list_fault_cases(q: str = "", category: str = "", limit: int = 30, user=Depends(require_role("admin"))):
    """搜索或列出故障案例"""
    db = await get_db()
    if q:
        like = f"%{q}%"
        cursor = await db.execute(
            "SELECT id, title, category, symptoms, root_cause, solution, tags, source, created_at "
            "FROM fault_cases WHERE title LIKE ? OR symptoms LIKE ? OR root_cause LIKE ? OR tags LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (like, like, like, like, limit),
        )
    elif category:
        cursor = await db.execute(
            "SELECT id, title, category, symptoms, root_cause, solution, tags, source, created_at "
            "FROM fault_cases WHERE category = ? ORDER BY created_at DESC LIMIT ?",
            (category, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT id, title, category, symptoms, root_cause, solution, tags, source, created_at "
            "FROM fault_cases ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "category": r[2],
            "symptoms": (r[3] or "")[:200],
            "root_cause": (r[4] or "")[:200],
            "solution": (r[5] or "")[:200],
            "tags": r[6],
            "source": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


@router.post("/fault-cases")
async def create_fault_case(request: Request, user=Depends(require_role("admin"))):
    """手动录入故障案例"""
    body = await request.json()
    if not body.get("title"):
        raise HTTPException(400, "缺少标题")
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO fault_cases (title, category, symptoms, root_cause, solution, tags, source) "
        "VALUES (?, ?, ?, ?, ?, ?, 'manual')",
        (
            body["title"],
            body.get("category", ""),
            body.get("symptoms", ""),
            body.get("root_cause", ""),
            body.get("solution", ""),
            body.get("tags", ""),
        ),
    )
    case_id = cursor.lastrowid
    # 更新 FTS5
    try:
        await db.execute(
            "INSERT INTO fault_cases_fts(rowid, title, symptoms, root_cause, solution, tags) VALUES (?, ?, ?, ?, ?, ?)",
            (
                case_id,
                body["title"],
                body.get("symptoms", ""),
                body.get("root_cause", ""),
                body.get("solution", ""),
                body.get("tags", ""),
            ),
        )
    except Exception as e:
        logger.debug("FTS5 索引写入失败: %s", e)
    await db.commit()
    return {"ok": True, "id": case_id}


@router.delete("/fault-cases/{case_id}")
async def delete_fault_case(case_id: int, user=Depends(require_role("admin"))):
    """删除故障案例"""
    db = await get_db()
    await db.execute("DELETE FROM fault_cases WHERE id = ?", (case_id,))
    try:
        await db.execute("DELETE FROM fault_cases_fts WHERE rowid = ?", (case_id,))
    except Exception as e:
        logger.debug("FTS5 索引删除失败: %s", e)
    await db.commit()
    return {"ok": True}


# ─── 事件 ───


@router.get("/events")
async def list_events(limit: int = 50, user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, event_type, tool_name, tool_input, risk_level, username, details "
        "FROM agent_events ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "timestamp": r[0],
            "event_type": r[1],
            "tool_name": r[2],
            "tool_input": r[3],
            "risk_level": r[4],
            "username": r[5],
            "details": r[6],
        }
        for r in rows
    ]

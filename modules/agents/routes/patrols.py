"""巡检任务 + 模板路由"""

import asyncio
import contextlib
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.dependencies import require_role
from database import get_db
from modules.agents.schemas import PatrolUpdate

logger = logging.getLogger(__name__)

# 防止 asyncio 任务被 GC 回收的强引用集合
_background_tasks: set[asyncio.Task] = set()

router = APIRouter()


# ─── 巡检任务 ───


@router.get("/patrols")
async def list_patrols(user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, display_name, description, interval_minutes, enabled, last_run, last_status, last_report, check_tools, prompt "
        "FROM agent_patrol_tasks ORDER BY id"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "display_name": r[1],
            "description": r[2],
            "interval_minutes": r[3],
            "enabled": bool(r[4]),
            "last_run": r[5],
            "last_status": r[6],
            "last_report": (r[7] or "")[:500],
            "check_tools": r[8] or "",
            "prompt": r[9] or "",
        }
        for r in rows
    ]


@router.put("/patrols/{patrol_id}")
async def update_patrol(patrol_id: str, body: PatrolUpdate, user=Depends(require_role("admin"))):
    db = await get_db()
    sets, vals = [], []
    if body.enabled is not None:
        sets.append("enabled = ?")
        vals.append(1 if body.enabled else 0)
    if body.interval_minutes is not None:
        sets.append("interval_minutes = ?")
        vals.append(body.interval_minutes)
    if body.prompt is not None:
        sets.append("prompt = ?")
        vals.append(body.prompt)
    if body.check_tools is not None:
        sets.append("check_tools = ?")
        vals.append(body.check_tools)
    if not sets:
        raise HTTPException(400, "没有要更新的字段")
    vals.append(patrol_id)
    await db.execute(f"UPDATE agent_patrol_tasks SET {', '.join(sets)} WHERE id = ?", vals)  # noqa: S608 — 列名来自代码白名单
    await db.commit()
    return {"ok": True}


@router.post("/patrols/{patrol_id}/run")
async def trigger_patrol(patrol_id: str, user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM agent_patrol_tasks WHERE id = ?", (patrol_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "巡检任务不存在")

    task_dict = {"id": row[0], "display_name": row[1], "description": row[2], "prompt": row[5]}
    from modules.agents.patrol import execute_patrol

    task = asyncio.create_task(execute_patrol(task_dict, triggered_by=user["username"]))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"ok": True, "message": f"巡检 {row[1]} 已触发"}


@router.get("/patrols/{patrol_id}/history")
async def get_patrol_history(patrol_id: str, limit: int = 20, user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, status, report, duration_seconds, report_json "
        "FROM agent_patrol_history WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
        (patrol_id, limit),
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        item = {"timestamp": r[0], "status": r[1], "report": (r[2] or "")[:1000], "duration": r[3]}
        if r[4]:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                item["report_json"] = json.loads(r[4])
        results.append(item)
    return results


@router.get("/patrols/{patrol_id}/report/{history_id}")
async def get_patrol_report(patrol_id: str, history_id: int, user=Depends(require_role("admin"))):
    """获取单次巡检的完整结构化报告"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, status, report, report_json, duration_seconds "
        "FROM agent_patrol_history WHERE id = ? AND task_id = ?",
        (history_id, patrol_id),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "巡检记录不存在")
    result = {
        "timestamp": row[0],
        "status": row[1],
        "report": row[2],
        "duration": row[4],
    }
    if row[3]:
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            result["report_json"] = json.loads(row[3])
    return result


# ─── 巡检模板 ───


@router.get("/templates")
async def list_templates(category: str = "", user=Depends(require_role("admin"))):
    """列出所有巡检模板"""
    db = await get_db()
    if category:
        cursor = await db.execute(
            "SELECT id, name, category, description, check_tools, prompt_template, variables, is_builtin "
            "FROM patrol_templates WHERE category = ? ORDER BY name",
            (category,),
        )
    else:
        cursor = await db.execute(
            "SELECT id, name, category, description, check_tools, prompt_template, variables, is_builtin "
            "FROM patrol_templates ORDER BY category, name"
        )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        item = {
            "id": r[0],
            "name": r[1],
            "category": r[2],
            "description": r[3],
            "check_tools": r[4],
            "prompt_template": r[5],
            "is_builtin": bool(r[7]),
        }
        try:
            item["variables"] = json.loads(r[6]) if r[6] else []
        except (json.JSONDecodeError, TypeError):
            item["variables"] = []
        results.append(item)
    return results


@router.post("/templates")
async def create_template(request: Request, user=Depends(require_role("admin"))):
    """创建自定义巡检模板"""
    body = await request.json()
    for field in ("id", "name", "check_tools", "prompt_template"):
        if field not in body:
            raise HTTPException(400, f"缺少必填字段: {field}")

    db = await get_db()
    existing = await db.execute("SELECT id FROM patrol_templates WHERE id = ?", (body["id"],))
    if await existing.fetchone():
        raise HTTPException(409, f"模板 ID 已存在: {body['id']}")

    variables = body.get("variables", [])
    if isinstance(variables, list):
        variables = json.dumps(variables, ensure_ascii=False)

    await db.execute(
        "INSERT INTO patrol_templates (id, name, category, description, check_tools, prompt_template, variables, is_builtin) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
        (
            body["id"],
            body["name"],
            body.get("category", "general"),
            body.get("description", ""),
            body["check_tools"],
            body["prompt_template"],
            variables,
        ),
    )
    await db.commit()
    return {"ok": True, "id": body["id"]}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, user=Depends(require_role("admin"))):
    """删除自定义巡检模板（内置模板不可删除）"""
    db = await get_db()
    cursor = await db.execute("SELECT is_builtin FROM patrol_templates WHERE id = ?", (template_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "模板不存在")
    if row[0]:
        raise HTTPException(403, "内置模板不可删除")
    await db.execute("DELETE FROM patrol_templates WHERE id = ?", (template_id,))
    await db.commit()
    return {"ok": True}


@router.post("/patrols/from-template")
async def create_patrol_from_template(request: Request, user=Depends(require_role("admin"))):
    """从模板创建巡检任务"""
    body = await request.json()
    template_id = body.get("template_id")
    if not template_id:
        raise HTTPException(400, "缺少 template_id")

    db = await get_db()
    cursor = await db.execute(
        "SELECT name, description, check_tools, prompt_template, variables FROM patrol_templates WHERE id = ?",
        (template_id,),
    )
    tpl = await cursor.fetchone()
    if not tpl:
        raise HTTPException(404, f"模板不存在: {template_id}")

    # 用传入的变量值替换 prompt 模板中的占位符
    prompt = tpl[3]
    variables = body.get("variables", {})
    if variables:
        with contextlib.suppress(KeyError):
            prompt = prompt.format(**variables)

    patrol_id = body.get("id") or f"custom_{template_id}_{int(datetime.now().timestamp())}"
    display_name = body.get("display_name") or tpl[0]
    interval = body.get("interval_minutes", 60)

    # 检查 ID 是否重复
    existing = await db.execute("SELECT id FROM agent_patrol_tasks WHERE id = ?", (patrol_id,))
    if await existing.fetchone():
        raise HTTPException(409, f"巡检任务 ID 已存在: {patrol_id}")

    await db.execute(
        "INSERT INTO agent_patrol_tasks (id, display_name, description, interval_minutes, check_tools, prompt) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (patrol_id, display_name, tpl[1] or "", interval, tpl[2], prompt),
    )
    await db.commit()
    return {"ok": True, "id": patrol_id, "display_name": display_name}

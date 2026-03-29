"""告警规则 + 告警历史路由"""

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.dependencies import require_role
from database import get_db

router = APIRouter()


@router.get("/alerts/rules")
async def list_alert_rules(user=Depends(require_role("admin"))):
    """获取所有告警规则"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, metric, operator, warning_threshold, critical_threshold, "
        "cooldown_minutes, notify, enabled FROM alert_rules ORDER BY id"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "metric": r[2],
            "operator": r[3],
            "warning_threshold": r[4],
            "critical_threshold": r[5],
            "cooldown_minutes": r[6],
            "notify": bool(r[7]),
            "enabled": bool(r[8]),
        }
        for r in rows
    ]


@router.put("/alerts/rules/{rule_id}")
async def update_alert_rule(rule_id: str, request: Request, user=Depends(require_role("admin"))):
    """更新告警规则"""
    db = await get_db()
    body = await request.json()
    sets, vals = [], []
    for field in ("name", "metric", "operator", "warning_threshold", "critical_threshold", "cooldown_minutes"):
        if field in body:
            sets.append(f"{field} = ?")
            vals.append(body[field])
    if "notify" in body:
        sets.append("notify = ?")
        vals.append(1 if body["notify"] else 0)
    if "enabled" in body:
        sets.append("enabled = ?")
        vals.append(1 if body["enabled"] else 0)
    if not sets:
        raise HTTPException(400, "没有要更新的字段")
    vals.append(rule_id)
    await db.execute(f"UPDATE alert_rules SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()
    return {"ok": True}


@router.post("/alerts/rules")
async def create_alert_rule(request: Request, user=Depends(require_role("admin"))):
    """创建自定义告警规则"""
    body = await request.json()
    required = ("id", "name", "metric")
    for field in required:
        if field not in body:
            raise HTTPException(400, f"缺少必填字段: {field}")
    db = await get_db()
    existing = await db.execute("SELECT id FROM alert_rules WHERE id = ?", (body["id"],))
    if await existing.fetchone():
        raise HTTPException(409, f"规则 ID 已存在: {body['id']}")
    await db.execute(
        "INSERT INTO alert_rules (id, name, metric, operator, warning_threshold, critical_threshold, cooldown_minutes, notify) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            body["id"],
            body["name"],
            body["metric"],
            body.get("operator", ">"),
            body.get("warning_threshold"),
            body.get("critical_threshold"),
            body.get("cooldown_minutes", 60),
            1 if body.get("notify", True) else 0,
        ),
    )
    await db.commit()
    return {"ok": True, "id": body["id"]}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str, user=Depends(require_role("admin"))):
    """删除告警规则"""
    db = await get_db()
    await db.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    await db.commit()
    return {"ok": True}


@router.get("/alerts/history")
async def list_alert_history(limit: int = 50, user=Depends(require_role("admin"))):
    """获取告警历史"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT ah.id, ah.rule_id, ar.name, ah.severity, ah.current_value, ah.message, ah.notified, ah.created_at "
        "FROM alert_history ah LEFT JOIN alert_rules ar ON ah.rule_id = ar.id "
        "ORDER BY ah.created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "rule_id": r[1],
            "rule_name": r[2] or r[1],
            "severity": r[3],
            "current_value": r[4],
            "message": r[5],
            "notified": bool(r[6]),
            "created_at": r[7],
        }
        for r in rows
    ]

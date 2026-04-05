"""告警规则 CRUD 与查询服务"""

import logging
import time
from datetime import datetime

from database import get_db

logger = logging.getLogger(__name__)

_RULE_FIELDS = (
    "id, name, enabled, resource, server_scope, metric, operator, threshold, "
    "duration_seconds, severity, cooldown_seconds, auto_action, auto_action_config, "
    "notification_channels, notification_template, created_by, updated_at, created_at"
)


def _row_to_rule(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "enabled": bool(row[2]),
        "resource": row[3],
        "server_scope": row[4],
        "metric": row[5],
        "operator": row[6],
        "threshold": row[7],
        "duration_seconds": row[8],
        "severity": row[9],
        "cooldown_seconds": row[10],
        "auto_action": row[11],
        "auto_action_config": row[12],
        "notification_channels": row[13],
        "notification_template": row[14],
        "created_by": row[15],
        "updated_at": row[16],
        "created_at": row[17],
    }


async def list_rules(enabled_only: bool = False) -> list[dict]:
    db = await get_db()
    where = "WHERE enabled=1" if enabled_only else ""
    rows = await (
        await db.execute(f"SELECT {_RULE_FIELDS} FROM alert_rules {where} ORDER BY created_at")  # noqa: S608
    ).fetchall()
    return [_row_to_rule(r) for r in rows]


async def get_rule(rule_id: str) -> dict | None:
    db = await get_db()
    row = await (
        await db.execute(f"SELECT {_RULE_FIELDS} FROM alert_rules WHERE id=?", (rule_id,))  # noqa: S608
    ).fetchone()
    return _row_to_rule(row) if row else None


async def create_rule(data: dict, created_by: str | None = None) -> dict:
    rule_id = f"rule-{int(time.time() * 1000)}"
    now = datetime.now().isoformat()
    db = await get_db()
    await db.execute(
        """INSERT INTO alert_rules
           (id, name, enabled, resource, server_scope, metric, operator, threshold,
            duration_seconds, severity, cooldown_seconds,
            auto_action, auto_action_config,
            notification_channels, notification_template,
            created_by, updated_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            rule_id,
            data["name"],
            1 if data.get("enabled", True) else 0,
            data.get("resource", "system"),
            data.get("server_scope", "*"),
            data["metric"],
            data.get("operator", ">"),
            data.get("threshold"),
            data.get("duration_seconds", 60),
            data.get("severity", "warning"),
            data.get("cooldown_seconds", 300),
            data.get("auto_action"),
            data.get("auto_action_config"),
            data.get("notification_channels"),
            data.get("notification_template"),
            created_by,
            now,
            now,
        ),
    )
    await db.commit()
    logger.info("创建告警规则: %s (%s)", rule_id, data["name"])
    return await get_rule(rule_id)


async def update_rule(rule_id: str, data: dict) -> dict | None:
    db = await get_db()
    existing = await (await db.execute("SELECT id FROM alert_rules WHERE id=?", (rule_id,))).fetchone()
    if not existing:
        return None

    allowed = {
        "name",
        "enabled",
        "resource",
        "server_scope",
        "metric",
        "operator",
        "threshold",
        "duration_seconds",
        "severity",
        "cooldown_seconds",
        "auto_action",
        "auto_action_config",
        "notification_channels",
        "notification_template",
    }
    updates = []
    params = []
    for key, val in data.items():
        if key not in allowed:
            continue
        if key == "enabled":
            val = 1 if val else 0
        updates.append(f"{key}=?")
        params.append(val)

    if not updates:
        return await get_rule(rule_id)

    updates.append("updated_at=?")
    params.append(datetime.now().isoformat())
    params.append(rule_id)
    await db.execute(
        f"UPDATE alert_rules SET {', '.join(updates)} WHERE id=?",  # noqa: S608
        params,
    )
    await db.commit()
    logger.info("更新告警规则: %s", rule_id)
    return await get_rule(rule_id)


async def delete_rule(rule_id: str) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
    await db.commit()
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info("删除告警规则: %s", rule_id)
    return deleted


async def toggle_rule(rule_id: str, enabled: bool) -> dict | None:
    return await update_rule(rule_id, {"enabled": enabled})


async def get_active_alerts(server_id: str | None = None, limit: int = 100) -> list[dict]:
    """获取当前处于 firing 状态的告警"""
    db = await get_db()
    params: list = []
    where = "WHERE h.status='firing'"
    if server_id:
        where += " AND h.server_id=?"
        params.append(server_id)

    rows = await (
        await db.execute(
            f"""SELECT h.id, h.rule_id, h.server_id, h.status, h.value, h.message,
                       h.severity, h.fired_at, h.resolved_at, h.acknowledged_by,
                       h.acknowledged_at, r.name as rule_name
                FROM alert_history h
                LEFT JOIN alert_rules r ON h.rule_id = r.id
                {where}
                ORDER BY h.fired_at DESC LIMIT ?""",  # noqa: S608
            (*params, limit),
        )
    ).fetchall()
    return [_row_to_history(r) for r in rows]


async def get_alert_history(
    limit: int = 50,
    offset: int = 0,
    server_id: str | None = None,
    severity: str | None = None,
    status: str | None = None,
) -> dict:
    db = await get_db()
    conditions = []
    params: list = []

    if server_id:
        conditions.append("h.server_id=?")
        params.append(server_id)
    if severity:
        conditions.append("h.severity=?")
        params.append(severity)
    if status:
        conditions.append("h.status=?")
        params.append(status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    count_row = await (
        await db.execute(
            f"SELECT COUNT(*) FROM alert_history h {where}",
            params,
        )
    ).fetchone()
    total = count_row[0] if count_row else 0

    rows = await (
        await db.execute(
            f"""SELECT h.id, h.rule_id, h.server_id, h.status, h.value, h.message,
                       h.severity, h.fired_at, h.resolved_at, h.acknowledged_by,
                       h.acknowledged_at, r.name as rule_name
                FROM alert_history h
                LEFT JOIN alert_rules r ON h.rule_id = r.id
                {where}
                ORDER BY h.fired_at DESC LIMIT ? OFFSET ?""",  # noqa: S608
            (*params, limit, offset),
        )
    ).fetchall()

    return {"items": [_row_to_history(r) for r in rows], "total": total}


def _row_to_history(row) -> dict:
    return {
        "id": row[0],
        "rule_id": row[1],
        "server_id": row[2],
        "status": row[3],
        "value": row[4],
        "message": row[5],
        "severity": row[6],
        "fired_at": row[7],
        "resolved_at": row[8],
        "acknowledged_by": row[9],
        "acknowledged_at": row[10],
        "rule_name": row[11] if len(row) > 11 else None,
    }


async def acknowledge_alert(history_id: int, username: str) -> bool:
    db = await get_db()
    now = datetime.now().isoformat()
    cursor = await db.execute(
        "UPDATE alert_history SET acknowledged_by=?, acknowledged_at=? WHERE id=? AND status='firing'",
        (username, now, history_id),
    )
    await db.commit()
    return cursor.rowcount > 0

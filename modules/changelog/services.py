"""变更日历业务逻辑 — 变更记录 CRUD、冻结窗口管理、统计聚合"""

import logging
from datetime import datetime

from database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 变更事件
# ---------------------------------------------------------------------------

_EVENT_FIELDS = (
    "id, timestamp, event_type, title, description, operator, affected_services, risk_level, duration_minutes"
)


def _row_to_event(row) -> dict:
    return {
        "id": row[0],
        "timestamp": row[1],
        "event_type": row[2],
        "title": row[3],
        "description": row[4],
        "operator": row[5],
        "affected_services": row[6],
        "risk_level": row[7],
        "duration_minutes": row[8],
    }


async def list_events(
    *,
    start: str | None = None,
    end: str | None = None,
    event_type: str | None = None,
    operator: str | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """查询变更事件列表，支持时间范围/类型/操作人筛选"""
    db = await get_db()
    conditions: list[str] = []
    params: list = []

    if start:
        conditions.append("timestamp >= ?")
        params.append(start)
    if end:
        conditions.append("timestamp <= ?")
        params.append(end)
    if event_type:
        conditions.append("event_type = ?")
        params.append(event_type)
    if operator:
        conditions.append("operator = ?")
        params.append(operator)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    count_row = await (
        await db.execute(f"SELECT COUNT(*) FROM changelog_events {where}", params)  # noqa: S608
    ).fetchone()
    total = count_row[0] if count_row else 0

    rows = await (
        await db.execute(
            f"SELECT {_EVENT_FIELDS} FROM changelog_events {where} "  # noqa: S608
            "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        )
    ).fetchall()

    return {"items": [_row_to_event(r) for r in rows], "total": total}


async def create_event(data: dict, operator: str | None = None) -> dict:
    """创建变更记录"""
    db = await get_db()
    now = datetime.now().isoformat()
    cursor = await db.execute(
        "INSERT INTO changelog_events "
        "(timestamp, event_type, title, description, operator, affected_services, risk_level, duration_minutes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            now,
            data["event_type"],
            data["title"],
            data.get("description"),
            operator,
            data.get("affected_services"),
            data.get("risk_level", "low"),
            data.get("duration_minutes"),
        ),
    )
    await db.commit()

    row = await (
        await db.execute(f"SELECT {_EVENT_FIELDS} FROM changelog_events WHERE id=?", (cursor.lastrowid,))  # noqa: S608
    ).fetchone()
    return _row_to_event(row)


async def get_event(event_id: int) -> dict | None:
    """获取单条变更记录"""
    db = await get_db()
    row = await (
        await db.execute(f"SELECT {_EVENT_FIELDS} FROM changelog_events WHERE id=?", (event_id,))  # noqa: S608
    ).fetchone()
    return _row_to_event(row) if row else None


async def delete_event(event_id: int) -> bool:
    """删除变更记录"""
    db = await get_db()
    cursor = await db.execute("DELETE FROM changelog_events WHERE id=?", (event_id,))
    await db.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------------------
# 冻结窗口
# ---------------------------------------------------------------------------

_FREEZE_FIELDS = "id, title, start_time, end_time, reason, created_by, created_at"


def _row_to_freeze(row) -> dict:
    return {
        "id": row[0],
        "title": row[1],
        "start_time": row[2],
        "end_time": row[3],
        "reason": row[4],
        "created_by": row[5],
        "created_at": row[6],
    }


async def list_freeze_windows(
    *,
    active_only: bool = False,
) -> list[dict]:
    """查询冻结窗口列表"""
    db = await get_db()
    if active_only:
        now = datetime.now().isoformat()
        rows = await (
            await db.execute(
                f"SELECT {_FREEZE_FIELDS} FROM changelog_freeze_windows "  # noqa: S608
                "WHERE start_time <= ? AND end_time >= ? ORDER BY start_time",
                (now, now),
            )
        ).fetchall()
    else:
        rows = await (
            await db.execute(
                f"SELECT {_FREEZE_FIELDS} FROM changelog_freeze_windows ORDER BY start_time DESC"  # noqa: S608
            )
        ).fetchall()
    return [_row_to_freeze(r) for r in rows]


async def create_freeze_window(data: dict, created_by: str | None = None) -> dict:
    """创建冻结窗口"""
    db = await get_db()
    now = datetime.now().isoformat()
    cursor = await db.execute(
        "INSERT INTO changelog_freeze_windows (title, start_time, end_time, reason, created_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            data["title"],
            data["start_time"],
            data["end_time"],
            data.get("reason"),
            created_by,
            now,
        ),
    )
    await db.commit()

    row = await (
        await db.execute(
            f"SELECT {_FREEZE_FIELDS} FROM changelog_freeze_windows WHERE id=?",  # noqa: S608
            (cursor.lastrowid,),
        )
    ).fetchone()
    return _row_to_freeze(row)


async def delete_freeze_window(window_id: int) -> bool:
    """删除冻结窗口"""
    db = await get_db()
    cursor = await db.execute("DELETE FROM changelog_freeze_windows WHERE id=?", (window_id,))
    await db.commit()
    return cursor.rowcount > 0


async def is_frozen_now() -> dict | None:
    """检查当前是否在冻结窗口内，返回匹配的窗口或 None"""
    windows = await list_freeze_windows(active_only=True)
    return windows[0] if windows else None


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


async def get_stats(
    *,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """变更统计 — 按天聚合 + 按类型聚合"""
    db = await get_db()
    conditions: list[str] = []
    params: list = []

    if start:
        conditions.append("timestamp >= ?")
        params.append(start)
    if end:
        conditions.append("timestamp <= ?")
        params.append(end)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    # 按天聚合
    daily_rows = await (
        await db.execute(
            f"SELECT DATE(timestamp) AS day, COUNT(*) AS cnt "  # noqa: S608
            f"FROM changelog_events {where} GROUP BY day ORDER BY day",
            params,
        )
    ).fetchall()
    by_day = [{"date": r[0], "count": r[1]} for r in daily_rows]

    # 按类型聚合
    type_rows = await (
        await db.execute(
            f"SELECT event_type, COUNT(*) AS cnt "  # noqa: S608
            f"FROM changelog_events {where} GROUP BY event_type ORDER BY cnt DESC",
            params,
        )
    ).fetchall()
    by_type = [{"event_type": r[0], "count": r[1]} for r in type_rows]

    # 按风险等级聚合
    risk_rows = await (
        await db.execute(
            f"SELECT risk_level, COUNT(*) AS cnt "  # noqa: S608
            f"FROM changelog_events {where} GROUP BY risk_level ORDER BY cnt DESC",
            params,
        )
    ).fetchall()
    by_risk = [{"risk_level": r[0], "count": r[1]} for r in risk_rows]

    # 总数
    total_row = await (
        await db.execute(f"SELECT COUNT(*) FROM changelog_events {where}", params)  # noqa: S608
    ).fetchone()

    return {
        "total": total_row[0] if total_row else 0,
        "by_day": by_day,
        "by_type": by_type,
        "by_risk": by_risk,
    }

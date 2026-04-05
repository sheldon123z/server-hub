"""通知管理服务：多渠道统一发送、渠道 CRUD、历史记录"""

import asyncio
import json
import logging
import time
from datetime import datetime

from config import settings
from database import get_db
from modules.notifications.channels import (
    CHANNEL_TYPES,
    mask_sensitive,
)

logger = logging.getLogger(__name__)


async def send_notification(message: str, channel_ids: list[str] | None = None) -> list[dict]:
    """统一发送接口。广播到所有启用渠道或指定渠道。"""
    db = await get_db()
    if channel_ids:
        rows = await (
            await db.execute(
                "SELECT id, channel_type, display_name, config_json FROM notification_channels WHERE id IN ({}) AND enabled=1".format(  # noqa: S608 — 占位符由 channel_ids 数量生成
                    ",".join("?" * len(channel_ids))
                ),
                channel_ids,
            )
        ).fetchall()
    else:
        rows = await (
            await db.execute(
                "SELECT id, channel_type, display_name, config_json FROM notification_channels WHERE enabled=1 ORDER BY priority"
            )
        ).fetchall()

    if not rows:
        return [{"channel_id": None, "channel": "none", "success": False, "error": "没有启用的通知渠道"}]

    # 并发发送
    async def _send_one(row):
        ch_id, ch_type, ch_name, config_str = row
        config = json.loads(config_str)
        cls = CHANNEL_TYPES.get(ch_type)
        if not cls:
            return {
                "channel_id": ch_id,
                "channel": ch_type,
                "display_name": ch_name,
                "success": False,
                "error": f"未知渠道类型: {ch_type}",
            }

        channel = cls(ch_id, ch_name, config)
        result = await channel.send(message)

        # 写入历史
        try:
            await db.execute(
                "INSERT INTO notifications (channel, message, success, error, channel_id) VALUES (?, ?, ?, ?, ?)",
                (ch_type, message, 1 if result["success"] else 0, result.get("error"), ch_id),
            )
            await db.commit()
        except Exception as e:
            logger.error(f"写入通知历史失败: {e}")

        return {"channel_id": ch_id, "channel": ch_type, "display_name": ch_name, **result}

    results = await asyncio.gather(*[_send_one(r) for r in rows], return_exceptions=True)
    # 处理异常
    final = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            final.append({"channel_id": rows[i][0], "channel": rows[i][1], "success": False, "error": str(r)})
        else:
            final.append(r)
    return final


async def send_telegram(message: str) -> dict:
    """向后兼容：发送 Telegram 通知。优先通过多渠道系统发送。"""
    results = await send_notification(message)
    # 找 telegram 类型的结果
    for r in results:
        if r.get("channel") == "telegram":
            return {"success": r["success"], "message": message, "error": r.get("error")}
    # 如果没有 telegram 渠道，返回第一个结果
    if results:
        r = results[0]
        return {"success": r["success"], "message": message, "error": r.get("error")}
    return {"success": False, "message": message, "error": "没有启用的通知渠道"}


def _mask_channel_config(channel_type: str, config: dict) -> dict:
    """对渠道配置中的敏感字段进行掩码处理"""
    cls = CHANNEL_TYPES.get(channel_type)
    if cls:
        schema = cls.config_schema()
        sensitive_fields = {f["name"] for f in schema if f.get("sensitive")}
        return {k: mask_sensitive(v) if k in sensitive_fields and v else v for k, v in config.items()}
    return config


def _row_to_channel_dict(row) -> dict:
    """将数据库行转为渠道字典（含掩码配置）"""
    config = json.loads(row[4])
    masked_config = _mask_channel_config(row[1], config)
    return {
        "id": row[0],
        "channel_type": row[1],
        "display_name": row[2],
        "enabled": bool(row[3]),
        "config": masked_config,
        "priority": row[5],
        "created_at": row[6],
        "updated_at": row[7],
        "last_test_at": row[8],
        "last_test_ok": row[9] if row[9] is not None else None,
    }


_CHANNEL_FIELDS = (
    "id, channel_type, display_name, enabled, config_json, priority, created_at, updated_at, last_test_at, last_test_ok"
)


async def get_channels() -> list[dict]:
    """获取所有渠道列表（敏感字段掩码）"""
    db = await get_db()
    rows = await (
        await db.execute(f"SELECT {_CHANNEL_FIELDS} FROM notification_channels ORDER BY priority, created_at")  # noqa: S608 — _CHANNEL_FIELDS 是常量
    ).fetchall()
    return [_row_to_channel_dict(r) for r in rows]


async def get_channel(channel_id: str) -> dict | None:
    """获取单个渠道（含掩码配置）"""
    db = await get_db()
    row = await (
        await db.execute(f"SELECT {_CHANNEL_FIELDS} FROM notification_channels WHERE id=?", (channel_id,))  # noqa: S608 — _CHANNEL_FIELDS 是常量
    ).fetchone()
    if not row:
        return None
    return _row_to_channel_dict(row)


async def create_channel(channel_type: str, display_name: str, config: dict, enabled: bool = True) -> dict:
    """创建通知渠道"""
    if channel_type not in CHANNEL_TYPES:
        raise ValueError(f"不支持的渠道类型: {channel_type}")

    channel_id = f"{channel_type}-{int(time.time() * 1000)}"
    db = await get_db()
    await db.execute(
        "INSERT INTO notification_channels (id, channel_type, display_name, enabled, config_json, priority) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (channel_id, channel_type, display_name, 1 if enabled else 0, json.dumps(config), 0),
    )
    await db.commit()
    logger.info(f"创建通知渠道: {channel_id} ({display_name})")
    return await get_channel(channel_id)


async def update_channel(channel_id: str, **kwargs) -> dict | None:
    """更新渠道配置。支持 display_name, config, enabled, priority"""
    db = await get_db()
    existing = await (
        await db.execute("SELECT config_json FROM notification_channels WHERE id=?", (channel_id,))
    ).fetchone()
    if not existing:
        return None

    old_config = json.loads(existing[0])
    updates = []
    params = []

    if "display_name" in kwargs:
        updates.append("display_name=?")
        params.append(kwargs["display_name"])

    if "config" in kwargs:
        new_config = kwargs["config"]
        # 编辑时前端会省略未改动的敏感字段，这里需要保留旧值，避免一次普通编辑把 webhook/token 清空。
        merged = old_config.copy()
        for k, v in new_config.items():
            if isinstance(v, str) and v.startswith("****"):
                merged[k] = old_config.get(k, v)
            else:
                merged[k] = v
        updates.append("config_json=?")
        params.append(json.dumps(merged))

    if "enabled" in kwargs:
        updates.append("enabled=?")
        params.append(1 if kwargs["enabled"] else 0)

    if "priority" in kwargs:
        updates.append("priority=?")
        params.append(kwargs["priority"])

    if updates:
        updates.append("updated_at=CURRENT_TIMESTAMP")
        params.append(channel_id)
        await db.execute(f"UPDATE notification_channels SET {', '.join(updates)} WHERE id=?", params)  # noqa: S608 — 列名来自代码白名单
        await db.commit()

    return await get_channel(channel_id)


async def delete_channel(channel_id: str) -> bool:
    """删除渠道"""
    db = await get_db()
    cursor = await db.execute("DELETE FROM notification_channels WHERE id=?", (channel_id,))
    await db.commit()
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info(f"删除通知渠道: {channel_id}")
    return deleted


async def test_channel(channel_id: str) -> dict:
    """测试渠道连通性"""
    db = await get_db()
    row = await (
        await db.execute(
            "SELECT channel_type, display_name, config_json FROM notification_channels WHERE id=?", (channel_id,)
        )
    ).fetchone()
    if not row:
        return {"success": False, "error": "渠道不存在"}

    ch_type, ch_name, config_str = row
    config = json.loads(config_str)
    cls = CHANNEL_TYPES.get(ch_type)
    if not cls:
        return {"success": False, "error": f"未知渠道类型: {ch_type}"}

    channel = cls(channel_id, ch_name, config)
    result = await channel.test()

    # 更新测试状态
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    await db.execute(
        "UPDATE notification_channels SET last_test_at=?, last_test_ok=? WHERE id=?",
        (now, 1 if result["success"] else 0, channel_id),
    )
    await db.commit()

    return result


async def get_notification_history(limit: int = 50, channel_id: str | None = None) -> list[dict]:
    """查询通知发送历史，支持按渠道筛选"""
    limit = min(max(1, limit), 500)
    db = await get_db()

    if channel_id:
        cursor = await db.execute(
            "SELECT id, timestamp, channel, message, success, error, channel_id "
            "FROM notifications WHERE channel_id=? ORDER BY timestamp DESC LIMIT ?",
            (channel_id, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT id, timestamp, channel, message, success, error, channel_id "
            "FROM notifications ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )

    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "timestamp": row[1],
            "channel": row[2],
            "message": row[3],
            "success": bool(row[4]),
            "error": row[5],
            "channel_id": row[6] if len(row) > 6 else None,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 站内通知 (inapp_notifications)
# ---------------------------------------------------------------------------


async def create_inapp_notification(
    title: str,
    content: str | None = None,
    severity: str = "info",
    user_id: str | None = None,
    type: str = "system",
    related_alert_id: str | None = None,
) -> dict:
    """写入一条站内通知，返回记录字典。"""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO inapp_notifications (user_id, type, title, content, severity, related_alert_id) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, type, title, content, severity, related_alert_id),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM inapp_notifications WHERE id=?", (cursor.lastrowid,))).fetchone()
    return _inapp_row_to_dict(row)


def _inapp_row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "user_id": row[1],
        "type": row[2],
        "title": row[3],
        "content": row[4],
        "severity": row[5],
        "read": bool(row[6]),
        "related_alert_id": row[7],
        "created_at": row[8],
    }


async def list_inapp_notifications(
    user_id: str | None = None,
    unread_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """分页查询站内通知列表。"""
    limit = min(max(1, limit), 200)
    db = await get_db()
    conditions = []
    params: list = []
    if user_id is not None:
        conditions.append("(user_id IS NULL OR user_id=?)")
        params.append(user_id)
    if unread_only:
        conditions.append("read=0")
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    count_row = await (
        await db.execute(f"SELECT COUNT(*) FROM inapp_notifications {where}", params)  # noqa: S608
    ).fetchone()
    total = count_row[0]
    rows = await (
        await db.execute(
            f"SELECT * FROM inapp_notifications {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
            [*params, limit, offset],
        )
    ).fetchall()
    return {"items": [_inapp_row_to_dict(r) for r in rows], "total": total}


async def get_unread_count(user_id: str | None = None) -> int:
    """查询未读站内通知数量。"""
    db = await get_db()
    if user_id is not None:
        row = await (
            await db.execute(
                "SELECT COUNT(*) FROM inapp_notifications WHERE (user_id IS NULL OR user_id=?) AND read=0",
                (user_id,),
            )
        ).fetchone()
    else:
        row = await (await db.execute("SELECT COUNT(*) FROM inapp_notifications WHERE read=0")).fetchone()
    return row[0]


async def mark_read(notification_id: int, user_id: str | None = None) -> bool:
    """标记单条站内通知为已读。"""
    db = await get_db()
    if user_id is not None:
        cursor = await db.execute(
            "UPDATE inapp_notifications SET read=1 WHERE id=? AND (user_id IS NULL OR user_id=?)",
            (notification_id, user_id),
        )
    else:
        cursor = await db.execute("UPDATE inapp_notifications SET read=1 WHERE id=?", (notification_id,))
    await db.commit()
    return cursor.rowcount > 0


async def mark_all_read(user_id: str | None = None) -> int:
    """全部标记为已读，返回影响行数。"""
    db = await get_db()
    if user_id is not None:
        cursor = await db.execute(
            "UPDATE inapp_notifications SET read=1 WHERE (user_id IS NULL OR user_id=?) AND read=0",
            (user_id,),
        )
    else:
        cursor = await db.execute("UPDATE inapp_notifications SET read=1 WHERE read=0")
    await db.commit()
    return cursor.rowcount


async def ensure_default_channels():
    """启动时确保至少有默认渠道。如果 notification_channels 表为空且 telegram 脚本已配置，自动创建。"""
    db = await get_db()
    count = (await (await db.execute("SELECT COUNT(*) FROM notification_channels")).fetchone())[0]
    if count == 0 and settings.telegram_script:
        await create_channel(
            channel_type="telegram",
            display_name="Telegram (默认)",
            config={"script_path": settings.telegram_script},
        )
        logger.info("自动创建默认 Telegram 渠道")

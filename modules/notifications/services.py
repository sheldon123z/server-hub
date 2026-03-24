"""通知管理服务：Telegram 发送和历史记录"""

import asyncio
from datetime import datetime

from config import settings
from database import get_db


async def send_telegram(message: str) -> dict:
    """通过配置的脚本发送 Telegram 通知"""
    success = False
    error_text = None

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", settings.telegram_script, message,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            success = True
        else:
            error_text = stderr.decode().strip() or stdout.decode().strip()
    except Exception as e:
        error_text = str(e)

    # 写入数据库
    try:
        db = await get_db()
        await db.execute(
            "INSERT INTO notifications (channel, message, success, error) VALUES (?, ?, ?, ?)",
            ("telegram", message, 1 if success else 0, error_text),
        )
        await db.commit()
    except Exception:
        pass

    result = {"success": success, "message": message}
    if error_text:
        result["error"] = error_text
    return result


async def get_notification_history(limit: int = 50) -> list[dict]:
    """查询通知发送历史"""
    limit = min(max(1, limit), 500)
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, timestamp, channel, message, success, error "
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
        }
        for row in rows
    ]

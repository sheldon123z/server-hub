"""后台心跳监控 — 定期检查所有注册服务器的存活状态"""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_heartbeat_task: asyncio.Task | None = None
HEARTBEAT_INTERVAL = 30  # seconds


async def _heartbeat_loop():
    """Main heartbeat loop"""
    while True:
        try:
            await _check_all_servers()
        except Exception as e:
            logger.exception("心跳检查异常: %s", e)
        await asyncio.sleep(HEARTBEAT_INTERVAL)


async def _check_all_servers():
    """Check all non-local servers"""
    from database import get_db
    from modules.servers.agent_client import AgentClient

    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM servers WHERE is_local = 0"
    )).fetchall()

    if not rows:
        return

    # Check servers in parallel (max 20 concurrent)
    sem = asyncio.Semaphore(20)

    async def check_one(server_dict):
        async with sem:
            client = AgentClient(server_dict)
            try:
                result = await asyncio.wait_for(client.health_check(), timeout=10)
                # AgentClient 返回 {"ok": true, "data": {"status": "ok", ...}}
                data = result.get("data", result) if result.get("ok") else result
                new_status = "online" if data.get("status") == "ok" else "degraded"
                agent_version = data.get("version", "")
            except Exception:
                new_status = "offline"
                agent_version = ""

            # Update status
            old_status = server_dict.get("status", "unknown")
            now = datetime.now(timezone.utc).isoformat()

            await db.execute(
                "UPDATE servers SET status = ?, last_heartbeat = ?, agent_version = ?, updated_at = ? WHERE id = ?",
                (new_status, now if new_status != "offline" else server_dict.get("last_heartbeat"),
                 agent_version, now, server_dict["id"]),
            )

            # Alert on status change
            if old_status != new_status and old_status != "unknown":
                logger.warning("服务器 %s 状态变更: %s -> %s", server_dict["name"], old_status, new_status)
                # TODO: Send notification via send_notification tool

    # Convert rows to dicts
    from modules.servers.services import _row_to_dict
    server_dicts = [_row_to_dict(r) for r in rows]

    await asyncio.gather(*[check_one(s) for s in server_dicts], return_exceptions=True)
    await db.commit()


async def start_heartbeat():
    global _heartbeat_task
    _heartbeat_task = asyncio.create_task(_heartbeat_loop())
    logger.info("[Heartbeat] 服务器心跳监控已启动 (间隔 %ds)", HEARTBEAT_INTERVAL)


async def stop_heartbeat():
    global _heartbeat_task
    if _heartbeat_task:
        _heartbeat_task.cancel()
        _heartbeat_task = None

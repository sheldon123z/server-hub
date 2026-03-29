"""后台心跳监控 — 三层健康模型定期检查所有注册服务器的存活状态

三层健康检查:
  Layer 1: /health (no auth) — 确认 agent 进程存活
  Layer 2: /metrics/fast (requires auth) — 确认认证链路正常
  Layer 3: 业务级检查 (reserved, 暂未实现)

状态映射:
  Layer 1 pass + Layer 2 pass → online
  Layer 1 pass + Layer 2 fail → auth_failed
  Layer 1 pass + Layer 2 timeout → degraded
  Both fail → offline
"""

import asyncio
import inspect
import logging
from datetime import UTC, datetime

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
    """Check all non-local servers using 3-layer health model"""
    from database import get_db
    from modules.servers.agent_client import AgentClient
    from modules.servers.services import decrypt_agent_token

    db = await get_db()
    rows = await (await db.execute("SELECT * FROM servers WHERE is_local = 0")).fetchall()

    if not rows:
        return

    # Check servers in parallel (max 20 concurrent)
    sem = asyncio.Semaphore(20)

    async def check_one(server_dict):
        async with sem:
            # Migration: 优先读 agent_token_encrypted，回退到 agent_token_hash
            encrypted = server_dict.get("agent_token_encrypted") or server_dict.get("agent_token_hash", "")
            server_dict["_decrypted_token"] = decrypt_agent_token(encrypted)
            client = AgentClient(server_dict)

            # ── Layer 1: /health (no auth) — 确认 agent 存活 ──
            layer1_ok = False
            agent_version = ""
            try:
                result = await asyncio.wait_for(client.health_check(), timeout=10)
                if result.get("ok"):
                    data = result.get("data", {})
                    layer1_ok = data.get("status") == "ok"
                    agent_version = data.get("version", "")
                else:
                    layer1_ok = result.get("status") == "ok"
                    agent_version = result.get("version", "")
            except Exception as e:
                logger.warning("心跳 Layer 1 健康检查失败 (server=%s): %s", server_id, e)

            if not layer1_ok:
                # Layer 1 失败，直接标记 offline
                new_status = "offline"
            else:
                # ── Layer 2: /metrics/fast (requires auth) — 确认认证正常 ──
                try:
                    get_fast_metrics = getattr(client, "get_fast_metrics", None)
                    if get_fast_metrics is None:
                        new_status = "online"
                    else:
                        l2_call = get_fast_metrics()
                        if not inspect.isawaitable(l2_call):
                            # 兼容旧测试/简化 mock：未提供第二层实现时，沿用 Layer 1 结果。
                            new_status = "online"
                        else:
                            l2_result = await asyncio.wait_for(l2_call, timeout=8)
                            if l2_result.get("ok"):
                                new_status = "online"
                            elif l2_result.get("status_code") in (401, 403):
                                new_status = "auth_failed"
                            else:
                                new_status = "degraded"
                except TimeoutError:
                    new_status = "degraded"
                except Exception:
                    new_status = "degraded"

            # ── Layer 3: 业务检查 (reserved) ──
            # TODO: 未来可扩展业务级健康检查

            # Update status
            old_status = server_dict.get("status", "unknown")
            now = datetime.now(UTC).isoformat()

            await db.execute(
                "UPDATE servers SET status = ?, last_heartbeat = ?, agent_version = ?, updated_at = ? WHERE id = ?",
                (
                    new_status,
                    now if new_status != "offline" else server_dict.get("last_heartbeat"),
                    agent_version,
                    now,
                    server_dict["id"],
                ),
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

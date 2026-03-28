"""
后台指标采集调度器
双频采集: 60s 全量快照存DB + 5s 轻量指标 WebSocket 推送
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from config import settings
from database import get_db
from modules.monitoring.collectors import collect_all, collect_realtime_fast

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None
_ws_task: asyncio.Task | None = None


async def _collect_and_store():
    """采集一次完整指标并写入数据库，同时通过 WS 广播"""
    try:
        snapshot = await asyncio.get_event_loop().run_in_executor(None, collect_all)
        db = await get_db()
        await db.execute(
            "INSERT INTO metrics (metric_type, value_json) VALUES (?, ?)",
            ("all", json.dumps(snapshot, ensure_ascii=False)),
        )
        await db.commit()

        # 基线偏离检测（不阻塞采集流程）
        try:
            from modules.agents.alert_engine import check_baseline_deviation
            await check_baseline_deviation(snapshot)
        except Exception as e:
            logger.debug(f"基线检测跳过: {e}")

        # 全量数据也通过 WS 广播
        try:
            from modules.monitoring.routes import ws_manager
            await ws_manager.broadcast({"type": "metrics_full", "server_id": "local", "data": snapshot})
        except Exception as e:
            logger.debug(f"WS全量广播跳过: {e}")

    except Exception as e:
        logger.error(f"指标采集失败: {e}")


async def _cleanup_old_metrics():
    """清理超过保留天数的过期指标

    使用 server_id + timestamp 条件以命中 idx_metrics_server_time 复合索引，
    避免全表扫描。按 server_id 分批删除，每批 LIMIT 防止长事务锁定。
    """
    try:
        cutoff = (datetime.now() - timedelta(days=settings.metrics_retention_days)).isoformat()
        db = await get_db()
        # 获取所有 server_id 以利用 idx_metrics_server_time 复合索引
        rows = await (await db.execute(
            "SELECT DISTINCT server_id FROM metrics WHERE timestamp < ?", (cutoff,)
        )).fetchall()
        if not rows:
            return
        for (sid,) in rows:
            await db.execute(
                "DELETE FROM metrics WHERE server_id = ? AND timestamp < ?",
                (sid, cutoff),
            )
        await db.commit()
    except Exception as e:
        logger.error(f"清理过期指标失败: {e}")


async def _check_quota_enforcement():
    """配额处置检查（非阻塞，异常不影响主循环）"""
    try:
        from modules.users.services import check_and_enforce_quotas
        await check_and_enforce_quotas()
    except Exception as e:
        logger.debug(f"配额处置检查跳过: {e}")


async def _scheduler_loop():
    """调度器主循环 - 60s 全量采集存库 + 配额处置"""
    logger.info(
        f"指标采集调度器已启动 (间隔: {settings.metrics_interval_seconds}s, "
        f"保留: {settings.metrics_retention_days}天)"
    )
    while True:
        await _collect_and_store()
        await _cleanup_old_metrics()
        await _check_quota_enforcement()
        await asyncio.sleep(settings.metrics_interval_seconds)


async def _ws_broadcast_loop():
    """5秒快速采集并广播到 WebSocket 客户端"""
    from modules.monitoring.routes import ws_manager

    logger.info(f"WebSocket 广播循环已启动 (间隔: {settings.ws_metrics_interval}s)")
    while True:
        if ws_manager.connection_count:
            try:
                snapshot = await asyncio.get_event_loop().run_in_executor(
                    None, collect_realtime_fast
                )
                await ws_manager.broadcast({"type": "metrics", "server_id": "local", "data": snapshot})
            except Exception as e:
                logger.error(f"WS广播失败: {e}")
        await asyncio.sleep(settings.ws_metrics_interval)


async def start_scheduler():
    """启动后台指标采集任务（双频: DB存储 + WS推送）"""
    global _scheduler_task, _ws_task

    if _scheduler_task is not None and not _scheduler_task.done():
        logger.warning("调度器已在运行中")
        return

    _scheduler_task = asyncio.create_task(_scheduler_loop())
    _ws_task = asyncio.create_task(_ws_broadcast_loop())
    logger.info("指标采集调度器任务已创建 (DB存储 + WS推送)")


async def stop_scheduler():
    """停止后台指标采集任务"""
    global _scheduler_task, _ws_task

    for task, name in [(_scheduler_task, "DB采集"), (_ws_task, "WS广播")]:
        if task is not None and not task.done():
            task.cancel()
            logger.info(f"{name}循环已停止")

    _scheduler_task = None
    _ws_task = None


# ---------------------------------------------------------------------------
# 远程服务器指标采集
# ---------------------------------------------------------------------------

_remote_task: asyncio.Task | None = None
REMOTE_COLLECT_INTERVAL = 60  # seconds


async def _remote_collect_loop():
    """远程服务器指标采集循环 — 每 60s 从所有在线远程服务器获取指标"""
    logger.info("远程指标采集循环已启动 (间隔: %ds)", REMOTE_COLLECT_INTERVAL)
    while True:
        try:
            await _collect_remote_metrics()
        except Exception as e:
            logger.error("远程指标采集异常: %s", e)
        await asyncio.sleep(REMOTE_COLLECT_INTERVAL)


async def _collect_remote_metrics():
    """从所有在线远程服务器采集指标并批量存储"""
    db = await get_db()
    rows = await (await db.execute(
        "SELECT * FROM servers WHERE is_local = 0 AND status = 'online'"
    )).fetchall()

    if not rows:
        return

    from modules.servers.services import _row_to_dict, decrypt_agent_token
    from modules.servers.agent_client import AgentClient

    sem = asyncio.Semaphore(10)
    # 收集所有成功结果，最后批量写入
    collected: list[tuple[dict, dict]] = []  # (server_dict, snapshot)

    async def collect_one(server_dict):
        async with sem:
            server_dict["_decrypted_token"] = decrypt_agent_token(server_dict.get("agent_token_hash", ""))
            client = AgentClient(server_dict)
            try:
                result = await asyncio.wait_for(client.get_metrics(), timeout=15)
                # AgentClient 返回 {"ok": true, "data": {...}} 格式
                if not result.get("ok"):
                    logger.debug("远程指标采集失败 [%s]: %s", server_dict["name"], result.get("error", ""))
                    return
                snapshot = result["data"]
            except Exception as e:
                logger.debug("远程指标采集异常 [%s]: %s", server_dict["name"], e)
                return

            collected.append((server_dict, snapshot))

            # 通过 WS 广播（带 server_id）
            try:
                from modules.monitoring.routes import ws_manager
                await ws_manager.broadcast({
                    "type": "metrics_full",
                    "server_id": server_dict["id"],
                    "data": snapshot,
                })
            except Exception as e:
                logger.debug("远程指标WS广播跳过 [%s]: %s", server_dict["name"], e)

    server_dicts = [_row_to_dict(r) for r in rows]
    await asyncio.gather(*[collect_one(s) for s in server_dicts], return_exceptions=True)

    # 批量写入 — 单次 executemany + 单次 commit
    if collected:
        insert_rows = [
            (server_dict["id"], "all", json.dumps(snapshot, ensure_ascii=False))
            for server_dict, snapshot in collected
        ]
        await db.executemany(
            "INSERT INTO metrics (server_id, metric_type, value_json) VALUES (?, ?, ?)",
            insert_rows,
        )
        await db.commit()


async def start_remote_scheduler():
    """启动远程服务器指标采集任务"""
    global _remote_task

    if _remote_task is not None and not _remote_task.done():
        logger.warning("远程采集调度器已在运行中")
        return

    _remote_task = asyncio.create_task(_remote_collect_loop())
    logger.info("远程指标采集调度器任务已创建")


async def stop_remote_scheduler():
    """停止远程服务器指标采集任务"""
    global _remote_task

    if _remote_task is not None and not _remote_task.done():
        _remote_task.cancel()
        logger.info("远程采集循环已停止")

    _remote_task = None

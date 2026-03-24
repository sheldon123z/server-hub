"""
后台指标采集调度器
定时采集系统指标并存入数据库，同时清理过期数据
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from config import settings
from database import get_db
from modules.monitoring.collectors import collect_all

logger = logging.getLogger(__name__)

_scheduler_task: asyncio.Task | None = None


async def _collect_and_store():
    """采集一次指标并写入数据库"""
    try:
        snapshot = await asyncio.get_event_loop().run_in_executor(None, collect_all)
        db = await get_db()
        await db.execute(
            "INSERT INTO metrics (metric_type, value_json) VALUES (?, ?)",
            ("all", json.dumps(snapshot, ensure_ascii=False)),
        )
        await db.commit()
    except Exception as e:
        logger.error(f"指标采集失败: {e}")


async def _cleanup_old_metrics():
    """清理超过保留天数的过期指标"""
    try:
        cutoff = (datetime.now() - timedelta(days=settings.metrics_retention_days)).isoformat()
        db = await get_db()
        await db.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
        await db.commit()
    except Exception as e:
        logger.error(f"清理过期指标失败: {e}")


async def _scheduler_loop():
    """调度器主循环"""
    logger.info(
        f"指标采集调度器已启动 (间隔: {settings.metrics_interval_seconds}s, "
        f"保留: {settings.metrics_retention_days}天)"
    )
    while True:
        await _collect_and_store()
        await _cleanup_old_metrics()
        await asyncio.sleep(settings.metrics_interval_seconds)


async def start_scheduler():
    """启动后台指标采集任务"""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        logger.warning("调度器已在运行中")
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("指标采集调度器任务已创建")


async def stop_scheduler():
    """停止后台指标采集任务"""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        _scheduler_task.cancel()
        logger.info("指标采集调度器已停止")
    _scheduler_task = None

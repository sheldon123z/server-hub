"""剧本定时触发调度器"""

import asyncio
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)
_scheduler_task = None


async def _schedule_loop():
    while True:
        try:
            from database import get_db

            db = await get_db()
            rows = await (
                await db.execute("SELECT id, trigger_config FROM playbooks WHERE trigger_config LIKE '%schedule%'")
            ).fetchall()
            for pid, trigger_json in rows:
                trigger = json.loads(trigger_json or "{}")
                if trigger.get("type") != "schedule" or not trigger.get("schedule"):
                    continue
                if _should_run(pid, trigger.get("schedule")):
                    from modules.playbooks.services import execute_playbook

                    asyncio.create_task(execute_playbook(pid, {}, "scheduler", "schedule"))
                    logger.info("定时剧本已触发: %s", pid)
        except Exception as e:
            logger.error("剧本调度器错误: %s", e)
        await asyncio.sleep(60)


def _should_run(playbook_id: str, cron_expr: str) -> bool:
    try:
        from croniter import croniter

        now = datetime.now()
        cron = croniter(cron_expr, now)
        prev = cron.get_prev(datetime)
        # If prev execution time is within the last 60 seconds
        return (now - prev).total_seconds() < 60
    except Exception:
        return False


async def start_playbook_scheduler():
    global _scheduler_task
    if _scheduler_task is None or _scheduler_task.done():
        _scheduler_task = asyncio.create_task(_schedule_loop())
        logger.info("剧本调度器已启动")


async def stop_playbook_scheduler():
    global _scheduler_task
    if _scheduler_task and not _scheduler_task.done():
        _scheduler_task.cancel()
    _scheduler_task = None

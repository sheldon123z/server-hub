"""Pipeline 触发系统 — Cron 定时 + 告警联动 + API 触发"""

import asyncio
import json
import logging
from datetime import datetime

from database import get_db

logger = logging.getLogger(__name__)

# Cron 触发器注册表 {pipeline_id: cron_expr}
_cron_triggers: dict[str, str] = {}

# 调度循环任务引用
_scheduler_task: asyncio.Task | None = None


async def setup_pipeline_triggers():
    """启动时注册所有 Cron 触发器并启动调度循环"""
    global _scheduler_task

    try:
        db = await get_db()
        rows = await (
            await db.execute("SELECT id, trigger_json FROM pipelines WHERE enabled = 1 AND trigger_json IS NOT NULL")
        ).fetchall()

        for pid, trigger_json in rows:
            if not trigger_json:
                continue
            try:
                trigger = json.loads(trigger_json)
                if trigger.get("type") == "cron" and trigger.get("cron"):
                    _cron_triggers[pid] = trigger["cron"]
                    logger.info("注册 Pipeline Cron 触发器: %s -> %s", pid, trigger["cron"])
            except json.JSONDecodeError:
                logger.warning("Pipeline %s 触发器 JSON 解析失败", pid)

        if _cron_triggers and _scheduler_task is None:
            _scheduler_task = asyncio.create_task(_cron_trigger_check())
            logger.info("Pipeline Cron 调度循环已启动 (共 %d 个触发器)", len(_cron_triggers))
    except Exception:
        logger.exception("Pipeline 触发器初始化失败")


async def _cron_trigger_check():
    """定期检查 Cron 触发器（60s 间隔，复用 patrol 调度模式）"""
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.now()

            for pipeline_id, cron_expr in list(_cron_triggers.items()):
                try:
                    if _cron_matches(cron_expr, now):
                        logger.info("Cron 触发 Pipeline: %s (表达式: %s)", pipeline_id, cron_expr)
                        from modules.pipelines.executor import start_pipeline_run

                        await start_pipeline_run(
                            pipeline_id=pipeline_id,
                            trigger_type="cron",
                            started_by="cron",
                        )
                except Exception:
                    logger.exception("Cron 触发 Pipeline 失败: %s", pipeline_id)

        except asyncio.CancelledError:
            logger.info("Pipeline Cron 调度循环已停止")
            break
        except Exception:
            logger.exception("Cron 调度循环异常")
            await asyncio.sleep(10)


async def trigger_from_alert(alert_rule_id: str, alert_context: dict) -> list[str]:
    """告警触发入口 — 查找绑定该告警规则的 Pipeline 并启动

    Returns: 已触发的 run_id 列表
    """
    db = await get_db()
    rows = await (
        await db.execute("SELECT id, trigger_json FROM pipelines WHERE enabled = 1 AND trigger_json IS NOT NULL")
    ).fetchall()

    triggered_runs: list[str] = []
    for pid, trigger_json in rows:
        if not trigger_json:
            continue
        try:
            trigger = json.loads(trigger_json)
            if trigger.get("type") == "alert" and trigger.get("alert_rule_id") == alert_rule_id:
                from modules.pipelines.executor import start_pipeline_run

                # 将告警上下文作为参数注入
                params = {"alert_context": alert_context, "alert_rule_id": alert_rule_id}
                run_id = await start_pipeline_run(
                    pipeline_id=pid,
                    params=params,
                    trigger_type="alert",
                    started_by=f"alert:{alert_rule_id}",
                )
                triggered_runs.append(run_id)
                logger.info("告警触发 Pipeline: %s -> run %s", pid, run_id)
        except Exception:
            logger.exception("告警触发 Pipeline %s 失败", pid)

    return triggered_runs


def register_pipeline_cron(pipeline_id: str, cron_expr: str):
    """注册 Pipeline Cron 触发器"""
    _cron_triggers[pipeline_id] = cron_expr
    logger.info("注册 Cron 触发器: %s -> %s", pipeline_id, cron_expr)


def unregister_pipeline_cron(pipeline_id: str):
    """注销 Pipeline Cron 触发器"""
    removed = _cron_triggers.pop(pipeline_id, None)
    if removed:
        logger.info("注销 Cron 触发器: %s", pipeline_id)


def _cron_matches(cron_expr: str, now: datetime) -> bool:
    """简易 Cron 表达式匹配（分 时 日 月 周）

    仅在分钟为 0 时检查（因为调度间隔 60s），避免重复触发。
    """
    if now.second > 5:
        # 只在每分钟前 5 秒内触发，防止重复
        return False

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        return False

    fields = [
        (parts[0], now.minute),
        (parts[1], now.hour),
        (parts[2], now.day),
        (parts[3], now.month),
        (parts[4], now.isoweekday() % 7),  # 0=Sunday
    ]

    return all(_field_matches(pattern, value) for pattern, value in fields)


def _field_matches(pattern: str, value: int) -> bool:
    """匹配单个 Cron 字段"""
    if pattern == "*":
        return True

    # 处理 */n 步长
    if pattern.startswith("*/"):
        try:
            step = int(pattern[2:])
            return value % step == 0
        except ValueError:
            return False

    # 处理逗号分隔的多值
    for part in pattern.split(","):
        # 处理范围 a-b
        if "-" in part:
            try:
                low, high = part.split("-", 1)
                if int(low) <= value <= int(high):
                    return True
            except ValueError:
                continue
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                continue

    return False

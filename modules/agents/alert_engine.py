"""告警规则引擎 — 可配置阈值 + 分级 + 去重"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from database import get_db

logger = logging.getLogger(__name__)

# ─── 默认告警规则 ───

DEFAULT_ALERT_RULES = [
    {
        "id": "mem_high",
        "name": "系统内存使用率过高",
        "metric": "memory_percent",
        "operator": ">",
        "warning_threshold": 85,
        "critical_threshold": 95,
        "cooldown_minutes": 60,
    },
    {
        "id": "swap_high",
        "name": "Swap 使用率过高",
        "metric": "swap_percent",
        "operator": ">",
        "warning_threshold": 60,
        "critical_threshold": 85,
        "cooldown_minutes": 60,
    },
    {
        "id": "disk_root_high",
        "name": "系统盘使用率过高",
        "metric": "disk_root_percent",
        "operator": ">",
        "warning_threshold": 85,
        "critical_threshold": 95,
        "cooldown_minutes": 360,
    },
    {
        "id": "gpu_temp_high",
        "name": "GPU 温度过高",
        "metric": "gpu_temperature",
        "operator": ">",
        "warning_threshold": 80,
        "critical_threshold": 85,
        "cooldown_minutes": 30,
    },
    {
        "id": "gpu_mem_high",
        "name": "GPU 显存使用率过高",
        "metric": "gpu_memory_percent",
        "operator": ">",
        "warning_threshold": 90,
        "critical_threshold": 98,
        "cooldown_minutes": 60,
    },
    {
        "id": "cpu_high",
        "name": "CPU 使用率持续过高",
        "metric": "cpu_percent",
        "operator": ">",
        "warning_threshold": 90,
        "critical_threshold": 98,
        "cooldown_minutes": 30,
    },
    {
        "id": "load_high",
        "name": "系统负载过高",
        "metric": "load_1m",
        "operator": ">",
        "warning_threshold": 120,
        "critical_threshold": 150,
        "cooldown_minutes": 30,
    },
]


async def seed_default_alert_rules():
    """初始化默认告警规则（如果不存在）"""
    db = await get_db()
    for rule in DEFAULT_ALERT_RULES:
        existing = await db.execute("SELECT id FROM alert_rules WHERE id = ?", (rule["id"],))
        if not await existing.fetchone():
            await db.execute(
                "INSERT INTO alert_rules (id, name, metric, operator, warning_threshold, critical_threshold, cooldown_minutes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rule["id"], rule["name"], rule["metric"], rule["operator"],
                 rule["warning_threshold"], rule["critical_threshold"], rule["cooldown_minutes"]),
            )
    await db.commit()


def _compare(value: float, operator: str, threshold: float) -> bool:
    """比较值与阈值"""
    if operator == ">":
        return value > threshold
    elif operator == ">=":
        return value >= threshold
    elif operator == "<":
        return value < threshold
    elif operator == "<=":
        return value <= threshold
    elif operator == "==":
        return value == threshold
    return False


async def _should_alert(rule_id: str, cooldown_minutes: int) -> bool:
    """检查是否在冷却期内（去重）。

    注意：SQLite DEFAULT CURRENT_TIMESTAMP 存 UTC 时间，
    所以必须用 SQLite 的 datetime() 函数在数据库侧做时间比较，避免时区不一致。
    """
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) FROM alert_history WHERE rule_id = ? AND created_at > datetime('now', ?)",
        (rule_id, f"-{cooldown_minutes} minutes"),
    )
    row = await cursor.fetchone()
    return row[0] == 0


async def fire_alert(rule: dict, severity: str, value: float):
    """触发告警：先写入历史（确保 cooldown 生效），再异步发送通知"""
    db = await get_db()
    message = f"[{severity.upper()}] {rule['name']}: 当前值 {value} (阈值: {rule.get(f'{severity}_threshold', 'N/A')})"

    # 先写入数据库（确保下次评估时 cooldown 能查到这条记录）
    await db.execute(
        "INSERT INTO alert_history (rule_id, severity, current_value, message, notified) VALUES (?, ?, ?, ?, 0)",
        (rule["id"], severity, value, message),
    )
    await db.commit()
    logger.warning(f"告警触发: {message}")

    # 再异步发送通知（不阻塞告警流程）
    if rule.get("notify", True):
        try:
            from modules.notifications.services import send_telegram
            emoji = "🚨" if severity == "critical" else "⚠️"
            await send_telegram(f"{emoji} 告警: {rule['name']}\n当前值: {value}\n级别: {severity}")
            await db.execute("UPDATE alert_history SET notified = 1 WHERE rule_id = ? AND message = ? ORDER BY created_at DESC LIMIT 1", (rule["id"], message))
            await db.commit()
        except Exception as e:
            logger.error(f"告警通知发送失败: {e}")


async def evaluate_rules(metrics: dict) -> list[dict]:
    """
    用指标快照评估所有启用的告警规则。

    参数:
        metrics: 扁平化的指标字典，如 {"memory_percent": 87.5, "gpu_temperature": 75}

    返回:
        触发的告警列表
    """
    if not metrics:
        return []

    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, metric, operator, warning_threshold, critical_threshold, cooldown_minutes, notify "
        "FROM alert_rules WHERE enabled = 1"
    )
    rules = await cursor.fetchall()

    fired = []
    for row in rules:
        rule = {
            "id": row[0], "name": row[1], "metric": row[2], "operator": row[3],
            "warning_threshold": row[4], "critical_threshold": row[5],
            "cooldown_minutes": row[6], "notify": bool(row[7]),
        }

        value = metrics.get(rule["metric"])
        if value is None:
            continue

        try:
            value = float(value)
        except (ValueError, TypeError):
            continue

        severity = None
        if rule["critical_threshold"] is not None and _compare(value, rule["operator"], rule["critical_threshold"]):
            severity = "critical"
        elif rule["warning_threshold"] is not None and _compare(value, rule["operator"], rule["warning_threshold"]):
            severity = "warning"

        if severity and await _should_alert(rule["id"], rule["cooldown_minutes"]):
            await fire_alert(rule, severity, value)
            fired.append({"rule_id": rule["id"], "name": rule["name"], "severity": severity, "value": value})

    return fired


def extract_metrics_from_report(report_json: dict | None) -> dict:
    """从结构化巡检报告中提取扁平化指标字典，供规则引擎使用"""
    if not report_json:
        return {}

    metrics = {}

    # 直接从 metrics_snapshot 提取
    snapshot = report_json.get("metrics_snapshot", {})
    if isinstance(snapshot, dict):
        metrics.update(snapshot)

    # 从 check_items 提取 current_value（尝试转为数字）
    for item in report_json.get("check_items", []):
        name = item.get("name", "")
        val = item.get("current_value", "")
        if val:
            try:
                metrics[name] = float(val.rstrip("%").strip())
            except (ValueError, TypeError):
                pass

    return metrics

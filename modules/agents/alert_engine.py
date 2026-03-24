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
            await db.execute(
                "UPDATE alert_history SET notified = 1 WHERE rowid = ("
                "SELECT rowid FROM alert_history WHERE rule_id = ? AND message = ? ORDER BY created_at DESC LIMIT 1"
                ")", (rule["id"], message),
            )
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
        "SELECT id, name, metric, operator, warning_threshold, critical_threshold, cooldown_minutes, notify, rule_type "
        "FROM alert_rules WHERE enabled = 1"
    )
    rules = await cursor.fetchall()

    fired = []
    for row in rules:
        rule = {
            "id": row[0], "name": row[1], "metric": row[2], "operator": row[3],
            "warning_threshold": row[4], "critical_threshold": row[5],
            "cooldown_minutes": row[6], "notify": bool(row[7]),
            "rule_type": row[8] if len(row) > 8 else "threshold",
        }

        # 跳过基线规则（由 check_baseline_deviation 单独处理）
        if rule.get("rule_type") == "baseline":
            continue

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


# ─── 异常基线检测 ───

# 内存缓存：{metric: {"mean": float, "stddev": float, "computed_at": float}}
_baseline_cache: dict[str, dict] = {}
_CACHE_TTL_SECONDS = 3600  # 每小时刷新一次


def _extract_metric_from_snapshot(snapshot: dict, metric_key: str) -> float | None:
    """从 collect_all() 的嵌套结构中提取指定指标值"""
    mapping = {
        "cpu_percent": lambda d: d.get("cpu", {}).get("overall_percent"),
        "memory_percent": lambda d: d.get("memory", {}).get("ram", {}).get("percent"),
        "swap_percent": lambda d: d.get("memory", {}).get("swap", {}).get("percent"),
        "gpu_util": lambda d: d.get("gpu", {}).get("util") if d.get("gpu", {}).get("available") else None,
        "gpu_temperature": lambda d: d.get("gpu", {}).get("temp") if d.get("gpu", {}).get("available") else None,
    }
    extractor = mapping.get(metric_key)
    if extractor:
        val = extractor(snapshot)
        return float(val) if val is not None else None
    return None


async def _compute_baseline(metric_key: str, window_hours: int = 168) -> dict | None:
    """计算 μ±σ 基线（7 天滑动窗口），带 1 小时缓存"""
    import time

    # 检查缓存
    cached = _baseline_cache.get(metric_key)
    if cached and (time.time() - cached.get("computed_at", 0)) < _CACHE_TTL_SECONDS:
        return cached

    db = await get_db()
    cursor = await db.execute(
        "SELECT value_json FROM metrics WHERE metric_type = 'all' AND timestamp > datetime('now', ?)",
        (f"-{window_hours} hours",),
    )
    rows = await cursor.fetchall()

    if len(rows) < 50:
        return None  # 数据量不足以建立可靠基线

    values = []
    for row in rows:
        try:
            data = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            val = _extract_metric_from_snapshot(data, metric_key)
            if val is not None:
                values.append(val)
        except (json.JSONDecodeError, TypeError):
            continue

    if len(values) < 50:
        return None

    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    stddev = variance ** 0.5

    result = {"mean": mean, "stddev": stddev, "sample_count": n, "computed_at": time.time()}
    _baseline_cache[metric_key] = result
    return result


# 连续偏离计数：{metric: count}
_deviation_counts: dict[str, int] = {}
_CONSECUTIVE_THRESHOLD = 3  # 连续 3 次偏离才告警


async def check_baseline_deviation(snapshot: dict):
    """
    检查当前采集快照中的指标是否偏离基线。
    由 scheduler.py 每 60s 调用一次。连续 N 次偏离触发告警。
    """
    db = await get_db()

    # 查询所有启用的基线规则
    try:
        cursor = await db.execute(
            "SELECT id, name, metric, cooldown_minutes, notify, baseline_window_hours, stddev_multiplier "
            "FROM alert_rules WHERE enabled = 1 AND rule_type = 'baseline'"
        )
        rules = await cursor.fetchall()
    except Exception:
        return  # rule_type 列可能还不存在

    for row in rules:
        rule_id, name, metric_key, cooldown, notify, window_hours, multiplier = row
        window_hours = window_hours or 168
        multiplier = multiplier or 3.0

        # 提取当前值
        current = _extract_metric_from_snapshot(snapshot, metric_key)
        if current is None:
            continue

        # 获取基线
        baseline = await _compute_baseline(metric_key, window_hours)
        if not baseline:
            continue

        mean = baseline["mean"]
        stddev = baseline["stddev"]
        if stddev < 0.1:
            continue  # 标准差太小，不做偏离检测（指标几乎恒定）

        upper = mean + multiplier * stddev
        lower = mean - multiplier * stddev
        is_deviation = current > upper or current < lower

        if is_deviation:
            _deviation_counts[metric_key] = _deviation_counts.get(metric_key, 0) + 1
        else:
            _deviation_counts[metric_key] = 0

        if _deviation_counts.get(metric_key, 0) >= _CONSECUTIVE_THRESHOLD:
            # 连续 N 次偏离，触发告警
            if await _should_alert(rule_id, cooldown or 60):
                direction = "偏高" if current > upper else "偏低"
                rule = {
                    "id": rule_id, "name": name, "notify": bool(notify),
                    "warning_threshold": f"μ±{multiplier}σ",
                }
                await fire_alert(rule, "warning", current)
                logger.warning(
                    f"基线偏离告警: {name} 当前={current:.1f}, 基线={mean:.1f}±{stddev:.1f}, {direction}, 连续{_deviation_counts[metric_key]}次"
                )
            _deviation_counts[metric_key] = 0  # 告警后重置计数


# ─── 默认基线规则 ───

DEFAULT_BASELINE_RULES = [
    {
        "id": "baseline_cpu",
        "name": "CPU 使用率偏离基线",
        "metric": "cpu_percent",
        "rule_type": "baseline",
        "cooldown_minutes": 120,
        "baseline_window_hours": 168,
        "stddev_multiplier": 3.0,
    },
    {
        "id": "baseline_memory",
        "name": "内存使用率偏离基线",
        "metric": "memory_percent",
        "rule_type": "baseline",
        "cooldown_minutes": 120,
        "baseline_window_hours": 168,
        "stddev_multiplier": 3.0,
    },
    {
        "id": "baseline_gpu",
        "name": "GPU 利用率偏离基线",
        "metric": "gpu_util",
        "rule_type": "baseline",
        "cooldown_minutes": 120,
        "baseline_window_hours": 168,
        "stddev_multiplier": 3.0,
    },
]


async def seed_baseline_rules():
    """初始化默认基线告警规则"""
    db = await get_db()
    for rule in DEFAULT_BASELINE_RULES:
        existing = await db.execute("SELECT id FROM alert_rules WHERE id = ?", (rule["id"],))
        if not await existing.fetchone():
            try:
                await db.execute(
                    "INSERT INTO alert_rules (id, name, metric, operator, cooldown_minutes, rule_type, baseline_window_hours, stddev_multiplier) "
                    "VALUES (?, ?, ?, '>', ?, ?, ?, ?)",
                    (rule["id"], rule["name"], rule["metric"], rule["cooldown_minutes"],
                     rule["rule_type"], rule["baseline_window_hours"], rule["stddev_multiplier"]),
                )
            except Exception as e:
                logger.debug(f"基线规则 {rule['id']} 创建失败（可能列不存在）: {e}")
    await db.commit()

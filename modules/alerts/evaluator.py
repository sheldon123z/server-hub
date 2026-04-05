"""告警评估引擎 — 状态机 (OK→Pending→Firing→Resolved)"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from database import get_db

logger = logging.getLogger(__name__)


@dataclass
class AlertState:
    """单条规则 + 单台服务器的运行时状态"""

    status: str = "ok"  # ok | pending | firing | resolved
    pending_since: datetime | None = None
    fired_at: datetime | None = None
    last_notified_at: datetime | None = None
    history_id: int | None = None  # 当前开放的 alert_history 行 ID


# {rule_id: {server_id: AlertState}}
_states: dict[str, dict[str, AlertState]] = {}


def _get_state(rule_id: str, server_id: str) -> AlertState:
    return _states.setdefault(rule_id, {}).setdefault(server_id, AlertState())


def get_metric_value(snapshot: dict, metric_path: str) -> float | None:
    """从指标快照中按点号路径取值。

    支持路径:
      swap.percent            → snapshot["swap"]["percent"]
      cpu.percent             → snapshot["cpu"]["percent"]
      memory.percent          → snapshot["memory"]["percent"]
      disks./.percent         → snapshot["disks"]["/"]["percent"]
      gpu.0.temperature       → snapshot["gpu"][0]["temperature"]
      gpu.0.memory_used_pct   → snapshot["gpu"][0]["memory_used_pct"]
    """
    parts = metric_path.split(".")
    node: Any = snapshot
    for part in parts:
        if node is None:
            return None
        if isinstance(node, dict):
            node = node.get(part)
        elif isinstance(node, list):
            try:
                node = node[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    if isinstance(node, (int, float)):
        return float(node)
    return None


def _eval_condition(value: float, operator: str, threshold: float) -> bool:
    ops = {
        ">": lambda v, t: v > t,
        ">=": lambda v, t: v >= t,
        "<": lambda v, t: v < t,
        "<=": lambda v, t: v <= t,
        "==": lambda v, t: v == t,
        "!=": lambda v, t: v != t,
    }
    fn = ops.get(operator)
    return fn(value, threshold) if fn else False


async def _fire_alert(rule: dict, server_id: str, value: float, state: AlertState) -> None:
    """转入 Firing 状态：写 alert_history、发通知、执行自动动作"""
    now = datetime.now()
    state.status = "firing"
    state.fired_at = now
    state.last_notified_at = now

    severity = rule.get("severity") or "warning"
    message = _build_message(rule, value, severity)

    # 写 alert_history
    db = await get_db()
    cursor = await db.execute(
        """INSERT INTO alert_history
           (rule_id, server_id, status, value, message, severity, fired_at, created_at)
           VALUES (?, ?, 'firing', ?, ?, ?, ?, ?)""",
        (rule["id"], server_id, value, message, severity, now.isoformat(), now.isoformat()),
    )
    await db.commit()
    state.history_id = cursor.lastrowid

    logger.warning("告警触发 [%s] server=%s value=%.2f %s", rule["name"], server_id, value, severity)

    # 发通知
    await _send_alert_notification(rule, message, severity)

    # 自动动作
    auto_action = rule.get("auto_action")
    if auto_action:
        await _execute_auto_action(auto_action, rule.get("auto_action_config"), server_id, rule, value)


async def _resolve_alert(rule: dict, server_id: str, state: AlertState) -> None:
    """条件恢复：更新 alert_history resolved_at，转入 Resolved"""
    now = datetime.now()
    old_status = state.status
    state.status = "ok"
    state.pending_since = None
    state.fired_at = None

    if state.history_id:
        db = await get_db()
        await db.execute(
            "UPDATE alert_history SET status='resolved', resolved_at=? WHERE id=?",
            (now.isoformat(), state.history_id),
        )
        await db.commit()
        state.history_id = None

    if old_status == "firing":
        logger.info("告警恢复 [%s] server=%s", rule["name"], server_id)


def _build_message(rule: dict, value: float, severity: str) -> str:
    template = rule.get("notification_template") or (
        "告警: {name} | 当前值: {value:.2f} {operator} 阈值: {threshold} | 严重度: {severity}"
    )
    try:
        return template.format(
            name=rule.get("name", ""),
            value=value,
            operator=rule.get("operator", ">"),
            threshold=rule.get("threshold", ""),
            severity=severity,
            metric=rule.get("metric", ""),
            server_id="local",
        )
    except (KeyError, ValueError):
        return f"告警: {rule.get('name')} 当前值={value:.2f} 阈值={rule.get('threshold')}"


async def _send_alert_notification(rule: dict, message: str, severity: str) -> None:
    try:
        from modules.notifications.services import send_notification

        channel_ids_str = rule.get("notification_channels")
        channel_ids = [c.strip() for c in channel_ids_str.split(",")] if channel_ids_str else None
        results = await send_notification(message, channel_ids)
        ok = sum(1 for r in results if r.get("success"))
        logger.info("告警通知发送: %d/%d 渠道成功", ok, len(results))
    except Exception as e:
        logger.error("告警通知发送失败: %s", e)


async def _execute_auto_action(action: str, config_str: str | None, server_id: str, rule: dict, value: float) -> None:
    config: dict = {}
    if config_str:
        try:
            config = json.loads(config_str)
        except json.JSONDecodeError:
            logger.warning("auto_action_config JSON 解析失败: %s", config_str)

    try:
        if action == "kill_user_processes":
            username = config.get("username")
            if username:
                from modules.users.services import kill_user_processes_by_name

                await kill_user_processes_by_name(username)
                logger.info("自动动作: kill_user_processes username=%s", username)

        elif action == "notify_user":
            username = config.get("username")
            message = config.get("message") or f"告警: {rule.get('name')} 值={value:.2f}"
            if username:
                from modules.notifications.services import send_notification

                await send_notification(f"[通知用户 {username}] {message}")

        elif action == "restart_service":
            service_name = config.get("service")
            if service_name:
                from modules.services.services import control_service

                await control_service(service_name, "restart")
                logger.info("自动动作: restart_service service=%s", service_name)

    except Exception as e:
        logger.error("自动动作 %s 执行失败: %s", action, e)


async def evaluate(snapshot: dict, server_id: str = "local") -> None:
    """评估所有启用的告警规则，驱动状态机。由采集调度器在每次采集后调用。"""
    db = await get_db()
    rows = await (
        await db.execute(
            """SELECT id, name, resource, server_scope, metric, operator, threshold,
                      duration_seconds, severity, cooldown_seconds,
                      auto_action, auto_action_config,
                      notification_channels, notification_template
               FROM alert_rules WHERE enabled=1"""
        )
    ).fetchall()

    now = datetime.now()

    for row in rows:
        rule = dict(row)
        rule_id = rule["id"]

        # server_scope 过滤
        scope = rule.get("server_scope") or "*"
        if scope != "*" and scope != server_id:
            continue

        metric_path = rule.get("metric") or ""
        threshold = rule.get("threshold")
        operator = rule.get("operator") or ">"
        duration_seconds = rule.get("duration_seconds") or 60
        cooldown_seconds = rule.get("cooldown_seconds") or 300

        if threshold is None or not metric_path:
            continue

        value = get_metric_value(snapshot, metric_path)
        if value is None:
            continue

        condition_met = _eval_condition(value, operator, threshold)
        state = _get_state(rule_id, server_id)

        if condition_met:
            if state.status == "ok":
                # 进入 Pending
                state.status = "pending"
                state.pending_since = now
                logger.debug("告警 Pending [%s] server=%s value=%.2f", rule["name"], server_id, value)

            elif state.status == "pending":
                elapsed = (now - state.pending_since).total_seconds() if state.pending_since else 0
                if elapsed >= duration_seconds:
                    await _fire_alert(rule, server_id, value, state)

            elif state.status == "firing":
                # 冷却期内不重复通知
                if state.last_notified_at:
                    since_notify = (now - state.last_notified_at).total_seconds()
                    if since_notify >= cooldown_seconds:
                        # 冷却已过，重新发通知（持续告警提醒）
                        message = _build_message(rule, value, rule.get("severity") or "warning")
                        await _send_alert_notification(rule, message, rule.get("severity") or "warning")
                        state.last_notified_at = now

        else:
            # 条件不满足
            if state.status in ("pending", "firing"):
                await _resolve_alert(rule, server_id, state)
            elif state.status == "resolved":
                state.status = "ok"


async def evaluate_rule_now(rule_id: str, snapshot: dict, server_id: str = "local") -> dict:
    """立即对单条规则求值（用于「测试」按钮）"""
    db = await get_db()
    row = await (await db.execute("SELECT * FROM alert_rules WHERE id=?", (rule_id,))).fetchone()
    if not row:
        return {"ok": False, "error": "规则不存在"}

    rule = dict(row)
    metric_path = rule.get("metric") or ""
    threshold = rule.get("threshold")
    operator = rule.get("operator") or ">"

    if threshold is None or not metric_path:
        return {"ok": False, "error": "规则配置不完整（缺少 metric 或 threshold）"}

    value = get_metric_value(snapshot, metric_path)
    if value is None:
        return {"ok": True, "found": False, "message": f"指标 {metric_path} 在当前快照中不存在"}

    condition_met = _eval_condition(value, operator, threshold)
    return {
        "ok": True,
        "found": True,
        "metric": metric_path,
        "value": value,
        "operator": operator,
        "threshold": threshold,
        "condition_met": condition_met,
        "message": f"{metric_path}={value:.2f} {operator} {threshold} → {'触发' if condition_met else '未触发'}",
    }


def get_all_states() -> dict:
    """返回所有规则的当前状态（供 API 查询）"""
    result = {}
    for rule_id, servers in _states.items():
        result[rule_id] = {
            server_id: {
                "status": s.status,
                "pending_since": s.pending_since.isoformat() if s.pending_since else None,
                "fired_at": s.fired_at.isoformat() if s.fired_at else None,
                "last_notified_at": s.last_notified_at.isoformat() if s.last_notified_at else None,
            }
            for server_id, s in servers.items()
        }
    return result

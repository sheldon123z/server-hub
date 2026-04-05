"""内置告警规则初始化 — 替代散落的 Bash 脚本硬编码阈值"""

import logging

from database import get_db

logger = logging.getLogger(__name__)

BUILTIN_RULES = [
    {
        "id": "builtin-swap-warning",
        "name": "Swap 使用率过高",
        "enabled": 1,
        "resource": "system",
        "server_scope": "*",
        "metric": "swap.percent",
        "operator": ">",
        "threshold": 50.0,
        "duration_seconds": 300,  # 5 分钟
        "severity": "warning",
        "cooldown_seconds": 300,
        "auto_action": None,
        "auto_action_config": None,
        "notification_channels": None,
        "notification_template": "⚠️ Swap 使用率 {value:.1f}% 超过 {threshold}%，持续 5 分钟",
        "created_by": "system",
    },
    {
        "id": "builtin-user-memory-quota",
        "name": "用户内存超出配额",
        "enabled": 1,
        "resource": "users",
        "server_scope": "*",
        "metric": "users.over_quota_count",
        "operator": ">",
        "threshold": 0.0,
        "duration_seconds": 60,
        "severity": "critical",
        "cooldown_seconds": 300,
        "auto_action": None,
        "auto_action_config": None,
        "notification_channels": None,
        "notification_template": "🚨 有 {value:.0f} 个用户内存超出配额，请检查并处置",
        "created_by": "system",
    },
    {
        "id": "builtin-container-restart",
        "name": "容器频繁重启",
        "enabled": 1,
        "resource": "docker",
        "server_scope": "*",
        "metric": "docker.restart_count_1h",
        "operator": ">",
        "threshold": 3.0,
        "duration_seconds": 0,
        "severity": "warning",
        "cooldown_seconds": 3600,
        "auto_action": None,
        "auto_action_config": None,
        "notification_channels": None,
        "notification_template": "⚠️ 容器在过去 1 小时内重启 {value:.0f} 次，请检查容器日志",
        "created_by": "system",
    },
    {
        "id": "builtin-user-idle",
        "name": "用户长时间空闲",
        "enabled": 1,
        "resource": "users",
        "server_scope": "*",
        "metric": "users.idle_over_6h_count",
        "operator": ">",
        "threshold": 0.0,
        "duration_seconds": 0,
        "severity": "info",
        "cooldown_seconds": 21600,  # 6 小时
        "auto_action": None,
        "auto_action_config": None,
        "notification_channels": None,
        "notification_template": "ℹ️ 有 {value:.0f} 个用户已空闲超过 6 小时",
        "created_by": "system",
    },
    {
        "id": "builtin-disk-warning",
        "name": "磁盘使用率警告",
        "enabled": 1,
        "resource": "system",
        "server_scope": "*",
        "metric": "disks./.percent",
        "operator": ">",
        "threshold": 85.0,
        "duration_seconds": 60,
        "severity": "warning",
        "cooldown_seconds": 3600,
        "auto_action": None,
        "auto_action_config": None,
        "notification_channels": None,
        "notification_template": "⚠️ 根分区磁盘使用率 {value:.1f}% 超过 {threshold}%",
        "created_by": "system",
    },
    {
        "id": "builtin-disk-critical",
        "name": "磁盘使用率严重",
        "enabled": 1,
        "resource": "system",
        "server_scope": "*",
        "metric": "disks./.percent",
        "operator": ">",
        "threshold": 95.0,
        "duration_seconds": 0,
        "severity": "critical",
        "cooldown_seconds": 1800,
        "auto_action": None,
        "auto_action_config": None,
        "notification_channels": None,
        "notification_template": "🚨 根分区磁盘使用率 {value:.1f}% 超过 {threshold}%，请立即处置！",
        "created_by": "system",
    },
    {
        "id": "builtin-gpu-temp",
        "name": "GPU 温度过高",
        "enabled": 1,
        "resource": "gpu",
        "server_scope": "*",
        "metric": "gpu.0.temperature",
        "operator": ">",
        "threshold": 85.0,
        "duration_seconds": 60,
        "severity": "critical",
        "cooldown_seconds": 600,
        "auto_action": None,
        "auto_action_config": None,
        "notification_channels": None,
        "notification_template": "🚨 GPU 温度 {value:.1f}°C 超过 {threshold}°C，请检查散热！",
        "created_by": "system",
    },
]


async def seed_builtin_rules() -> None:
    """启动时插入内置规则（如已存在则跳过）"""
    db = await get_db()
    inserted = 0
    for rule in BUILTIN_RULES:
        existing = await (await db.execute("SELECT id FROM alert_rules WHERE id=?", (rule["id"],))).fetchone()
        if existing:
            continue
        await db.execute(
            """INSERT INTO alert_rules
               (id, name, enabled, resource, server_scope, metric, operator, threshold,
                duration_seconds, severity, cooldown_seconds,
                auto_action, auto_action_config,
                notification_channels, notification_template, created_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                rule["id"],
                rule["name"],
                rule["enabled"],
                rule["resource"],
                rule["server_scope"],
                rule["metric"],
                rule["operator"],
                rule["threshold"],
                rule["duration_seconds"],
                rule["severity"],
                rule["cooldown_seconds"],
                rule["auto_action"],
                rule["auto_action_config"],
                rule["notification_channels"],
                rule["notification_template"],
                rule["created_by"],
            ),
        )
        inserted += 1

    if inserted:
        await db.commit()
        logger.info("内置告警规则已初始化: 插入 %d 条", inserted)
    else:
        logger.debug("内置告警规则已存在，跳过初始化")

"""Fleet 批量操作预置模板 — 在应用启动时写入 batch_templates 表"""

import json
import logging

logger = logging.getLogger(__name__)

BUILTIN_TEMPLATES = [
    {
        "id": "builtin-sysinfo",
        "name": "批量系统信息",
        "description": "并行采集所有服务器的系统基本信息（uname / uptime / 磁盘）",
        "type": "command",
        "payload": json.dumps({"command": "uname -a && echo '---' && uptime && echo '---' && df -h /", "timeout": 15}),
        "strategy": "parallel",
        "rolling_batch_size": 1,
        "stop_on_failure": 0,
        "is_builtin": 1,
    },
    {
        "id": "builtin-service-restart",
        "name": "批量服务重启",
        "description": "滚动逐台重启指定 systemd 服务（需在 payload 中填写 name 和 action）",
        "type": "service_action",
        "payload": json.dumps({"name": "", "action": "restart"}),
        "strategy": "rolling",
        "rolling_batch_size": 1,
        "stop_on_failure": 1,
        "is_builtin": 1,
    },
    {
        "id": "builtin-docker-prune",
        "name": "批量 Docker 清理",
        "description": "并行在所有服务器上执行 docker system prune -f，释放闲置镜像和容器",
        "type": "docker_action",
        "payload": json.dumps({"action": "prune", "name": ""}),
        "strategy": "parallel",
        "rolling_batch_size": 1,
        "stop_on_failure": 0,
        "is_builtin": 1,
    },
    {
        "id": "builtin-security-check",
        "name": "批量安全检查",
        "description": "并行检查所有服务器的 SSH 配置、开放端口和失败登录",
        "type": "command",
        "payload": json.dumps(
            {
                "command": (
                    "echo '=== SSH Config ===' && grep -E '^(PermitRootLogin|PasswordAuthentication|Port)' /etc/ssh/sshd_config 2>/dev/null; "
                    "echo '=== Listening Ports ===' && ss -tlnp 2>/dev/null | head -20; "
                    "echo '=== Recent Auth Failures ===' && grep 'Failed password' /var/log/auth.log 2>/dev/null | tail -5 || echo 'N/A'"
                ),
                "timeout": 20,
            }
        ),
        "strategy": "parallel",
        "rolling_batch_size": 1,
        "stop_on_failure": 0,
        "is_builtin": 1,
    },
]


async def seed_batch_templates() -> None:
    """将内置模板写入数据库（已存在则跳过）"""
    from database import get_db

    db = await get_db()
    inserted = 0
    for tpl in BUILTIN_TEMPLATES:
        cursor = await db.execute("SELECT id FROM batch_templates WHERE id = ?", (tpl["id"],))
        if await cursor.fetchone() is None:
            await db.execute(
                """INSERT INTO batch_templates
                   (id, name, description, type, payload, strategy, rolling_batch_size, stop_on_failure, is_builtin)
                   VALUES (:id, :name, :description, :type, :payload, :strategy, :rolling_batch_size, :stop_on_failure, :is_builtin)""",
                tpl,
            )
            inserted += 1
    if inserted:
        await db.commit()
        logger.info("批量操作: 已写入 %d 个内置模板", inserted)

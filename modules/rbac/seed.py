"""RBAC 内置角色初始化"""

import logging
import uuid

import aiosqlite

logger = logging.getLogger(__name__)

# 内置角色定义: (name, display_name, description, permissions)
# permissions: list of (resource, action, scope)
BUILTIN_ROLES: list[tuple[str, str, str, list[tuple[str, str, str]]]] = [
    (
        "super-admin",
        "超级管理员",
        "拥有所有资源的所有操作权限",
        [("*", "*", "*")],
    ),
    (
        "operator",
        "运维人员",
        "可管理 Docker、服务、定时任务和服务器，但不能管理用户和系统设置",
        [
            ("docker", "read", "*"),
            ("docker", "write", "*"),
            ("docker", "execute", "*"),
            ("services", "read", "*"),
            ("services", "write", "*"),
            ("services", "execute", "*"),
            ("cron", "read", "*"),
            ("cron", "write", "*"),
            ("cron", "execute", "*"),
            ("servers", "read", "*"),
            ("servers", "write", "*"),
            ("servers", "execute", "*"),
            ("monitoring", "read", "*"),
            ("alerts", "read", "*"),
            ("alerts", "write", "*"),
            ("logs", "read", "*"),
        ],
    ),
    (
        "viewer",
        "只读观察者",
        "可查看所有资源但不能修改",
        [("*", "read", "*")],
    ),
    (
        "agent-user",
        "AI 助手用户",
        "仅可使用 AI 助手功能和查看系统信息",
        [
            ("agents", "read", "*"),
            ("agents", "execute", "*"),
            ("system", "read", "*"),
        ],
    ),
]


async def seed_builtin_roles(db: aiosqlite.Connection) -> None:
    """初始化内置角色和权限，幂等操作（已存在则跳过）。"""
    for name, display_name, description, permissions in BUILTIN_ROLES:
        # 检查角色是否已存在
        cursor = await db.execute("SELECT id FROM roles WHERE name = ?", (name,))
        row = await cursor.fetchone()

        if row is None:
            role_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO roles (id, name, display_name, description, builtin) VALUES (?, ?, ?, ?, 1)",
                (role_id, name, display_name, description),
            )
            logger.info("RBAC: 创建内置角色 %s (id=%s)", name, role_id)
        else:
            role_id = row[0]

        # 确保权限记录存在（INSERT OR IGNORE 保证幂等）
        for resource, action, scope in permissions:
            await db.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, resource, action, scope) VALUES (?, ?, ?, ?)",
                (role_id, resource, action, scope),
            )

    await db.commit()
    logger.info("RBAC: 内置角色初始化完成")

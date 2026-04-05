"""RBAC 权限矩阵 — 核心服务层"""

import logging
import uuid
from typing import Any

import aiosqlite

from database import get_db
from modules.rbac.models import Permission, Role

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 权限缓存 (进程内, 轻量级 TTL 缓存)
# ---------------------------------------------------------------------------

_permission_cache: dict[str, list[Permission]] = {}


def _invalidate_user_cache(user_id: str) -> None:
    _permission_cache.pop(user_id, None)


def invalidate_all_cache() -> None:
    """清空全部权限缓存（角色/权限变更后调用）。"""
    _permission_cache.clear()


# ---------------------------------------------------------------------------
# 权限查询
# ---------------------------------------------------------------------------


async def get_user_permissions(user_id: str) -> list[Permission]:
    """获取用户的所有权限（通过其角色聚合），带进程内缓存。"""
    if user_id in _permission_cache:
        return _permission_cache[user_id]

    db = await get_db()
    cursor = await db.execute(
        """
        SELECT DISTINCT rp.id, rp.role_id, rp.resource, rp.action, rp.scope
        FROM user_roles ur
        JOIN role_permissions rp ON ur.role_id = rp.role_id
        WHERE ur.user_id = ?
        """,
        (str(user_id),),
    )
    rows = await cursor.fetchall()
    perms = [Permission(id=row[0], role_id=row[1], resource=row[2], action=row[3], scope=row[4]) for row in rows]
    _permission_cache[user_id] = perms
    return perms


def _matches(pattern: str, value: str) -> bool:
    """通配符匹配: '*' 匹配所有。"""
    return pattern == "*" or pattern == value


async def has_permission(
    user_id: str,
    resource: str,
    action: str,
    scope: str | None = None,
) -> bool:
    """检查用户是否拥有指定权限。

    通配符规则:
    - resource/action/scope 任一为 '*' 时视为全匹配
    - scope 为 None 时只检查 resource + action
    """
    perms = await get_user_permissions(str(user_id))
    for p in perms:
        if not _matches(p.resource, resource):
            continue
        if not _matches(p.action, action):
            continue
        if scope is not None and not _matches(p.scope, scope):
            continue
        return True
    return False


# ---------------------------------------------------------------------------
# 角色查询
# ---------------------------------------------------------------------------


async def get_all_roles(db: aiosqlite.Connection | None = None) -> list[Role]:
    """返回所有角色（含权限列表）。"""
    if db is None:
        db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, display_name, description, builtin, created_at FROM roles ORDER BY builtin DESC, name"
    )
    role_rows = await cursor.fetchall()

    roles: list[Role] = []
    for row in role_rows:
        role_id, name, display_name, description, builtin, created_at = row
        perm_cursor = await db.execute(
            "SELECT id, role_id, resource, action, scope FROM role_permissions WHERE role_id = ?",
            (role_id,),
        )
        perm_rows = await perm_cursor.fetchall()
        perms = [Permission(id=pr[0], role_id=pr[1], resource=pr[2], action=pr[3], scope=pr[4]) for pr in perm_rows]
        roles.append(
            Role(
                id=role_id,
                name=name,
                display_name=display_name,
                description=description,
                builtin=bool(builtin),
                created_at=created_at,
                permissions=perms,
            )
        )
    return roles


async def get_role_permissions(role_id: str) -> list[Permission]:
    """获取指定角色的权限列表。"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, role_id, resource, action, scope FROM role_permissions WHERE role_id = ?",
        (role_id,),
    )
    rows = await cursor.fetchall()
    return [Permission(id=r[0], role_id=r[1], resource=r[2], action=r[3], scope=r[4]) for r in rows]


async def get_user_roles(user_id: str) -> list[str]:
    """返回用户已分配的角色 ID 列表。"""
    db = await get_db()
    cursor = await db.execute("SELECT role_id FROM user_roles WHERE user_id = ?", (str(user_id),))
    rows = await cursor.fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------------------
# 角色分配
# ---------------------------------------------------------------------------


async def assign_role(user_id: str, role_id: str) -> None:
    """为用户分配角色（幂等）。"""
    db = await get_db()
    await db.execute(
        "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
        (str(user_id), role_id),
    )
    await db.commit()
    _invalidate_user_cache(str(user_id))
    logger.info("RBAC: 用户 %s 分配角色 %s", user_id, role_id)


async def remove_role(user_id: str, role_id: str) -> None:
    """移除用户的角色。"""
    db = await get_db()
    await db.execute(
        "DELETE FROM user_roles WHERE user_id = ? AND role_id = ?",
        (str(user_id), role_id),
    )
    await db.commit()
    _invalidate_user_cache(str(user_id))
    logger.info("RBAC: 用户 %s 移除角色 %s", user_id, role_id)


# ---------------------------------------------------------------------------
# 角色 CRUD
# ---------------------------------------------------------------------------


async def create_role(
    name: str,
    display_name: str,
    description: str,
    permissions: list[dict[str, Any]],
) -> Role:
    """创建自定义角色。"""
    db = await get_db()

    # 唯一性检查
    cursor = await db.execute("SELECT id FROM roles WHERE name = ?", (name,))
    if await cursor.fetchone():
        raise ValueError(f"角色名 '{name}' 已存在")

    role_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO roles (id, name, display_name, description, builtin) VALUES (?, ?, ?, ?, 0)",
        (role_id, name, display_name, description),
    )

    for perm in permissions:
        await db.execute(
            "INSERT OR IGNORE INTO role_permissions (role_id, resource, action, scope) VALUES (?, ?, ?, ?)",
            (role_id, perm.get("resource", "*"), perm.get("action", "read"), perm.get("scope", "*")),
        )

    await db.commit()
    invalidate_all_cache()
    logger.info("RBAC: 创建角色 %s (id=%s)", name, role_id)

    return Role(
        id=role_id,
        name=name,
        display_name=display_name,
        description=description,
        builtin=False,
    )


async def update_role(
    role_id: str,
    display_name: str | None = None,
    description: str | None = None,
    permissions: list[dict[str, Any]] | None = None,
) -> Role | None:
    """更新角色信息（内置角色不允许修改权限）。"""
    db = await get_db()

    cursor = await db.execute("SELECT id, name, display_name, description, builtin FROM roles WHERE id = ?", (role_id,))
    row = await cursor.fetchone()
    if not row:
        return None

    r_id, r_name, r_display, r_desc, r_builtin = row

    new_display = display_name if display_name is not None else r_display
    new_desc = description if description is not None else r_desc

    await db.execute(
        "UPDATE roles SET display_name = ?, description = ? WHERE id = ?",
        (new_display, new_desc, role_id),
    )

    if permissions is not None and not r_builtin:
        await db.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        for perm in permissions:
            await db.execute(
                "INSERT OR IGNORE INTO role_permissions (role_id, resource, action, scope) VALUES (?, ?, ?, ?)",
                (role_id, perm.get("resource", "*"), perm.get("action", "read"), perm.get("scope", "*")),
            )

    await db.commit()
    invalidate_all_cache()

    perm_list = await get_role_permissions(role_id)
    return Role(
        id=r_id,
        name=r_name,
        display_name=new_display,
        description=new_desc,
        builtin=bool(r_builtin),
        permissions=perm_list,
    )


async def delete_role(role_id: str) -> bool:
    """删除自定义角色（内置角色不可删除）。"""
    db = await get_db()

    cursor = await db.execute("SELECT builtin FROM roles WHERE id = ?", (role_id,))
    row = await cursor.fetchone()
    if not row:
        return False
    if row[0]:
        raise ValueError("内置角色不可删除")

    await db.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    await db.commit()
    invalidate_all_cache()
    logger.info("RBAC: 删除角色 %s", role_id)
    return True


# ---------------------------------------------------------------------------
# 迁移: 旧 role 字段 → user_roles 表
# ---------------------------------------------------------------------------


async def migrate_legacy_roles(db: aiosqlite.Connection) -> None:
    """将 panel_users.role 字段值迁移到 user_roles 表。

    admin → super-admin
    user  → viewer

    幂等操作: 已在 user_roles 中有记录的用户跳过。
    """
    # 获取映射关系: 旧 role 名 → 新角色 name
    role_map = {"admin": "super-admin", "user": "viewer"}

    for old_role, new_role_name in role_map.items():
        # 查找对应新角色 ID
        cursor = await db.execute("SELECT id FROM roles WHERE name = ?", (new_role_name,))
        role_row = await cursor.fetchone()
        if not role_row:
            logger.warning("RBAC 迁移: 找不到内置角色 %s，跳过", new_role_name)
            continue
        new_role_id = role_row[0]

        # 找出需要迁移的用户（旧 role 字段存在且 user_roles 中还没有记录）
        cursor = await db.execute(
            """
            SELECT u.username
            FROM panel_users u
            WHERE u.role = ?
              AND NOT EXISTS (
                  SELECT 1 FROM user_roles ur WHERE ur.user_id = u.username
              )
            """,
            (old_role,),
        )
        users = await cursor.fetchall()

        for (username,) in users:
            await db.execute(
                "INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                (username, new_role_id),
            )
            logger.info("RBAC 迁移: 用户 %s (%s) → %s", username, old_role, new_role_name)

    await db.commit()
    logger.info("RBAC 迁移: 旧 role 字段迁移完成")

"""面板用户存储（SQLite）。"""

import logging
from datetime import datetime, timezone

from passlib.hash import bcrypt

from config import get_or_create_bootstrap_admin_password, settings
from database import get_db

logger = logging.getLogger(__name__)


def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.verify(password, hashed)


def get_token_version(user: dict | None) -> int:
    """读取用户的令牌版本号。"""
    if not user:
        return 0
    return int(user.get("token_version") or 0)


async def ensure_admin():
    """首次启动时创建默认管理员"""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT id FROM panel_users WHERE username = ?", (settings.admin_username,)
    )
    if not row:
        admin_password = settings.admin_password or get_or_create_bootstrap_admin_password()
        await db.execute(
            "INSERT INTO panel_users (username, hashed_password, display_name, role) VALUES (?, ?, ?, ?)",
            (settings.admin_username, hash_password(admin_password), "管理员", "admin"),
        )
        await db.commit()
        logger.warning("首次启动已创建默认管理员 %s，请尽快修改密码", settings.admin_username)


async def authenticate(username: str, password: str) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM panel_users WHERE username = ? AND disabled = 0", (username,)
    )
    if not rows:
        return None
    user = dict(rows[0])
    if not verify_password(password, user["hashed_password"]):
        return None
    # 更新最后登录时间
    last_login = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE panel_users SET last_login = ? WHERE id = ?",
        (last_login, user["id"]),
    )
    await db.commit()
    user["last_login"] = last_login
    return user


async def get_user_by_name(username: str) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM panel_users WHERE username = ?", (username,)
    )
    return dict(rows[0]) if rows else None


async def bump_token_version(user_id: int) -> int:
    """使指定用户的现有会话全部失效。"""
    db = await get_db()
    await db.execute(
        "UPDATE panel_users SET token_version = COALESCE(token_version, 0) + 1 WHERE id = ?",
        (user_id,),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT token_version FROM panel_users WHERE id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def list_users() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT id, username, display_name, role, disabled, created_at, last_login FROM panel_users ORDER BY id"
    )
    return [dict(r) for r in rows]


async def create_user(username: str, password: str, display_name: str = "", role: str = "user") -> dict:
    db = await get_db()
    await db.execute(
        "INSERT INTO panel_users (username, hashed_password, display_name, role) VALUES (?, ?, ?, ?)",
        (username, hash_password(password), display_name, role),
    )
    await db.commit()
    return await get_user_by_name(username)


async def update_user(user_id: int, **kwargs) -> bool:
    db = await get_db()
    sets = []
    vals = []
    should_invalidate = False
    for k, v in kwargs.items():
        if k == "password":
            sets.append("hashed_password = ?")
            vals.append(hash_password(v))
            should_invalidate = True
        elif k in ("display_name", "role", "disabled"):
            sets.append(f"{k} = ?")
            vals.append(v)
            if k in {"role", "disabled"}:
                should_invalidate = True
    if not sets:
        return False
    if should_invalidate:
        sets.append("token_version = COALESCE(token_version, 0) + 1")
    vals.append(user_id)
    await db.execute(f"UPDATE panel_users SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()
    return True


async def delete_user(user_id: int) -> bool:
    db = await get_db()
    await db.execute("DELETE FROM panel_users WHERE id = ?", (user_id,))
    await db.commit()
    return True

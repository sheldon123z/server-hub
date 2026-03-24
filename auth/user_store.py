"""面板用户存储（SQLite）"""

from passlib.hash import bcrypt
from database import get_db
from config import settings
from datetime import datetime, timezone


def hash_password(password: str) -> str:
    return bcrypt.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.verify(password, hashed)


async def ensure_admin():
    """首次启动时创建默认管理员"""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT id FROM panel_users WHERE username = ?", (settings.admin_username,)
    )
    if not row:
        await db.execute(
            "INSERT INTO panel_users (username, hashed_password, display_name, role) VALUES (?, ?, ?, ?)",
            (settings.admin_username, hash_password(settings.admin_password), "管理员", "admin"),
        )
        await db.commit()


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
    await db.execute(
        "UPDATE panel_users SET last_login = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), user["id"]),
    )
    await db.commit()
    return user


async def get_user_by_name(username: str) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM panel_users WHERE username = ?", (username,)
    )
    return dict(rows[0]) if rows else None


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
    for k, v in kwargs.items():
        if k == "password":
            sets.append("hashed_password = ?")
            vals.append(hash_password(v))
        elif k in ("display_name", "role", "disabled"):
            sets.append(f"{k} = ?")
            vals.append(v)
    if not sets:
        return False
    vals.append(user_id)
    await db.execute(f"UPDATE panel_users SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()
    return True


async def delete_user(user_id: int) -> bool:
    db = await get_db()
    await db.execute("DELETE FROM panel_users WHERE id = ?", (user_id,))
    await db.commit()
    return True

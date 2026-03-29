"""凭据加密管理 — Fernet 对称加密"""

import base64
import hashlib
import uuid

from cryptography.fernet import Fernet

from config import settings
from database import get_db


def _get_fernet() -> Fernet:
    """从 settings.secret_key 派生 Fernet 密钥"""
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


async def store_credential(
    name: str,
    value: str,
    description: str = "",
    credential_type: str = "generic",
    created_by: str = "system",
) -> str:
    """加密并存储凭据，返回 credential id"""
    fernet = _get_fernet()
    encrypted = fernet.encrypt(value.encode()).decode()
    db = await get_db()
    cred_id = uuid.uuid4().hex[:12]
    await db.execute(
        "INSERT OR REPLACE INTO playbook_credentials "
        "(id, name, description, encrypted_value, credential_type, created_by) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (cred_id, name, description, encrypted, credential_type, created_by),
    )
    await db.commit()
    return cred_id


async def decrypt_credential(name: str) -> str:
    """按名称解密凭据"""
    db = await get_db()
    row = await (
        await db.execute(
            "SELECT encrypted_value FROM playbook_credentials WHERE name = ?",
            (name,),
        )
    ).fetchone()
    if not row:
        raise ValueError(f"凭据不存在: {name}")
    return _get_fernet().decrypt(row[0].encode()).decode()


async def list_credentials() -> list[dict]:
    """列出所有凭据（不含密文）"""
    db = await get_db()
    rows = await (
        await db.execute(
            "SELECT name, description, credential_type, created_by, created_at "
            "FROM playbook_credentials ORDER BY created_at DESC"
        )
    ).fetchall()
    return [
        {
            "name": r[0],
            "description": r[1],
            "credential_type": r[2],
            "created_by": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


async def delete_credential(name: str) -> None:
    """删除凭据"""
    db = await get_db()
    await db.execute("DELETE FROM playbook_credentials WHERE name = ?", (name,))
    await db.commit()

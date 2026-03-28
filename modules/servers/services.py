"""多服务器管理业务逻辑 — CRUD、连通性测试、舰队概览"""

import asyncio
import hashlib
import json
import logging
import secrets
import uuid
from datetime import datetime, timezone

from database import get_db

logger = logging.getLogger(__name__)

SERVER_COLUMNS = [
    "id", "name", "hostname", "ip_address", "agent_port",
    "agent_token_hash", "ssh_user", "ssh_port", "ssh_key_credential",
    "os_info", "tags", "is_local", "status", "last_heartbeat",
    "agent_version", "created_at", "updated_at",
]


def _row_to_dict(row) -> dict | None:
    """将数据库行转换为字典，解析 JSON 字段"""
    if row is None:
        return None
    d = dict(row)
    # 解析 tags JSON
    if "tags" in d and isinstance(d["tags"], str):
        try:
            d["tags"] = json.loads(d["tags"])
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
    # bool 化 is_local
    if "is_local" in d:
        d["is_local"] = bool(d["is_local"])
    return d


# ─── Agent Token ───


def _get_fernet():
    """获取 Fernet 加密实例（复用 playbook credentials 的密钥）"""
    from cryptography.fernet import Fernet
    from config import settings
    import base64
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
    return Fernet(key)


def generate_agent_token() -> tuple[str, str]:
    """生成 agent token。返回 (plaintext_token, encrypted_token)。
    encrypted_token 存入 DB 的 agent_token_hash 字段（实际是加密值，可逆）。
    """
    token = secrets.token_urlsafe(32)
    encrypted = _get_fernet().encrypt(token.encode()).decode()
    return token, encrypted


def decrypt_agent_token(encrypted: str) -> str:
    """解密 agent token（从 DB 的 agent_token_hash 字段恢复明文）"""
    if not encrypted:
        return ""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except Exception:
        # 兼容旧的 SHA256 hash（不可逆，返回空）
        return ""


# ─── 服务器 CRUD ───


async def list_servers(status_filter: str | None = None) -> list[dict]:
    """列出所有服务器，可按状态过滤，包含所属分组名称"""
    db = await get_db()
    sql = (
        "SELECT s.*, "
        "GROUP_CONCAT(g.name) AS groups "
        "FROM servers s "
        "LEFT JOIN server_group_members m ON m.server_id = s.id "
        "LEFT JOIN server_groups g ON g.id = m.group_id "
    )
    if status_filter:
        sql += "WHERE s.status = ? "
        sql += "GROUP BY s.id ORDER BY s.is_local DESC, s.name"
        rows = await (await db.execute(sql, (status_filter,))).fetchall()
    else:
        sql += "GROUP BY s.id ORDER BY s.is_local DESC, s.name"
        rows = await (await db.execute(sql)).fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_server(server_id: str) -> dict | None:
    """获取单个服务器详情"""
    db = await get_db()
    row = await (
        await db.execute("SELECT * FROM servers WHERE id = ?", (server_id,))
    ).fetchone()
    return _row_to_dict(row)


async def create_server(data: dict, created_by: str) -> tuple[str, str]:
    """创建新服务器记录，返回 (server_id, plaintext_agent_token)"""
    db = await get_db()
    server_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    tags_json = json.dumps(data.get("tags", []), ensure_ascii=False)

    # 自动生成 agent token
    plaintext_token, token_hash = generate_agent_token()

    await db.execute(
        "INSERT INTO servers "
        "(id, name, hostname, ip_address, agent_port, agent_token_hash, ssh_user, ssh_port, "
        "ssh_key_credential, tags, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            server_id,
            data["name"],
            data["hostname"],
            data["ip_address"],
            data.get("agent_port", 9901),
            token_hash,
            data.get("ssh_user"),
            data.get("ssh_port", 22),
            data.get("ssh_key_credential"),
            tags_json,
            now,
            now,
        ),
    )
    await db.commit()
    logger.info("服务器已创建: %s (%s) by %s", data["name"], server_id, created_by)
    return server_id, plaintext_token


async def rotate_agent_token(server_id: str) -> str:
    """轮换服务器的 agent token，返回新的明文 token"""
    db = await get_db()
    existing = await get_server(server_id)
    if existing is None:
        raise ValueError(f"服务器 {server_id} 不存在")

    plaintext_token, token_hash = generate_agent_token()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        "UPDATE servers SET agent_token_hash = ?, updated_at = ? WHERE id = ?",
        (token_hash, now, server_id),
    )
    await db.commit()
    logger.info("服务器 %s 的 agent token 已轮换", server_id)
    return plaintext_token


async def update_server(server_id: str, updates: dict) -> None:
    """更新服务器信息（不允许修改 is_local）"""
    db = await get_db()
    existing = await get_server(server_id)
    if existing is None:
        raise ValueError(f"服务器 {server_id} 不存在")

    # 过滤不可修改字段（保留 None 值以允许清空字段，exclude_unset 已在路由层处理）
    updates.pop("is_local", None)
    updates.pop("id", None)
    fields = dict(updates)
    if not fields:
        return

    # tags 序列化
    if "tags" in fields and isinstance(fields["tags"], list):
        fields["tags"] = json.dumps(fields["tags"], ensure_ascii=False)

    fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values()) + [server_id]
    await db.execute(
        f"UPDATE servers SET {set_clause} WHERE id = ?",
        values,
    )
    await db.commit()


async def delete_server(server_id: str) -> None:
    """删除服务器（不允许删除本机）"""
    db = await get_db()
    existing = await get_server(server_id)
    if existing is None:
        raise ValueError(f"服务器 {server_id} 不存在")
    if existing.get("is_local"):
        raise ValueError("不能删除本机服务器记录")

    await db.execute("DELETE FROM server_group_members WHERE server_id = ?", (server_id,))
    await db.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    await db.commit()
    logger.info("服务器已删除: %s", server_id)


# ─── 连通性测试 ───


async def test_connectivity(server_id: str) -> dict:
    """测试服务器连通性: ping + SSH + Agent HTTP"""
    db = await get_db()
    server = await get_server(server_id)
    if server is None:
        raise ValueError(f"服务器 {server_id} 不存在")

    ip = server["ip_address"]
    result = {"ping_ok": False, "ping_ms": None, "ssh_ok": False, "ssh_error": None, "agent_ok": False}

    async def _test_ping() -> None:
        """Ping 测试"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "1", "-W", "3", ip,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            if proc.returncode == 0:
                result["ping_ok"] = True
                output = stdout.decode()
                for part in output.split():
                    if part.startswith("time="):
                        result["ping_ms"] = float(part.split("=")[1])
                        break
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug("Ping %s 失败: %s", ip, e)

    async def _test_ssh() -> None:
        """SSH 测试"""
        ssh_user = server.get("ssh_user")
        ssh_port = server.get("ssh_port", 22)
        if not ssh_user:
            return
        try:
            import asyncssh
            async with asyncio.timeout(5):
                async with asyncssh.connect(
                    ip,
                    port=ssh_port,
                    username=ssh_user,
                    known_hosts=None,
                ) as _conn:
                    result["ssh_ok"] = True
        except ImportError:
            result["ssh_error"] = "asyncssh 未安装"
        except Exception as e:
            result["ssh_error"] = str(e)[:200]

    async def _test_agent() -> None:
        """Agent HTTP 健康检查"""
        agent_port = server.get("agent_port", 9901)
        try:
            import httpx
            async with httpx.AsyncClient() as http_client:
                resp = await http_client.get(f"http://{ip}:{agent_port}/health", timeout=5)
                result["agent_ok"] = resp.status_code == 200
        except ImportError:
            pass
        except Exception:
            pass

    # 并行执行所有连通性测试
    await asyncio.gather(
        _test_ping(),
        _test_ssh(),
        _test_agent(),
        return_exceptions=True,
    )

    # 更新服务器状态
    now = datetime.now(timezone.utc).isoformat()
    if result["ping_ok"]:
        new_status = "online" if result["agent_ok"] else "degraded"
    else:
        new_status = "offline"

    await db.execute(
        "UPDATE servers SET status = ?, last_heartbeat = ?, updated_at = ? WHERE id = ?",
        (new_status, now, now, server_id),
    )
    await db.commit()

    return result


# ─── 舰队概览 ───


async def get_fleet_overview() -> dict:
    """获取服务器舰队概览统计"""
    db = await get_db()
    rows = await (
        await db.execute(
            "SELECT status, COUNT(*) as cnt FROM servers GROUP BY status"
        )
    ).fetchall()

    counts = {row["status"]: row["cnt"] for row in rows}
    total = sum(counts.values())

    return {
        "total": total,
        "online": counts.get("online", 0),
        "offline": counts.get("offline", 0),
        "degraded": counts.get("degraded", 0),
        "unknown": counts.get("unknown", 0),
    }


# ─── 服务器分组 ───


async def list_groups() -> list[dict]:
    """列出所有服务器分组，含成员数"""
    db = await get_db()
    rows = await (
        await db.execute(
            "SELECT g.*, "
            "(SELECT COUNT(*) FROM server_group_members m WHERE m.group_id = g.id) AS member_count "
            "FROM server_groups g ORDER BY g.name"
        )
    ).fetchall()
    return [dict(r) for r in rows]


async def create_group(data: dict) -> str:
    """创建服务器分组，返回 id"""
    db = await get_db()
    group_id = uuid.uuid4().hex[:12]
    await db.execute(
        "INSERT INTO server_groups (id, name, description, color) VALUES (?, ?, ?, ?)",
        (group_id, data["name"], data.get("description"), data.get("color", "#38bdf8")),
    )
    await db.commit()
    logger.info("服务器分组已创建: %s (%s)", data["name"], group_id)
    return group_id


async def delete_group(group_id: str) -> None:
    """删除服务器分组"""
    db = await get_db()
    row = await (
        await db.execute("SELECT id FROM server_groups WHERE id = ?", (group_id,))
    ).fetchone()
    if row is None:
        raise ValueError(f"分组 {group_id} 不存在")

    await db.execute("DELETE FROM server_group_members WHERE group_id = ?", (group_id,))
    await db.execute("DELETE FROM server_groups WHERE id = ?", (group_id,))
    await db.commit()
    logger.info("服务器分组已删除: %s", group_id)


# ─── 分组成员管理 ───


async def add_server_to_group(group_id: str, server_id: str) -> None:
    """将服务器添加到分组"""
    db = await get_db()
    # 验证分组和服务器存在
    group = await (
        await db.execute("SELECT id FROM server_groups WHERE id = ?", (group_id,))
    ).fetchone()
    if group is None:
        raise ValueError(f"分组 {group_id} 不存在")

    server = await get_server(server_id)
    if server is None:
        raise ValueError(f"服务器 {server_id} 不存在")

    # 检查是否已在组中
    existing = await (
        await db.execute(
            "SELECT 1 FROM server_group_members WHERE group_id = ? AND server_id = ?",
            (group_id, server_id),
        )
    ).fetchone()
    if existing:
        return  # 幂等操作

    await db.execute(
        "INSERT INTO server_group_members (group_id, server_id) VALUES (?, ?)",
        (group_id, server_id),
    )
    await db.commit()
    logger.info("服务器 %s 已添加到分组 %s", server_id, group_id)


async def remove_server_from_group(group_id: str, server_id: str) -> None:
    """从分组中移除服务器"""
    db = await get_db()
    result = await db.execute(
        "DELETE FROM server_group_members WHERE group_id = ? AND server_id = ?",
        (group_id, server_id),
    )
    await db.commit()
    if result.rowcount == 0:
        raise ValueError(f"服务器 {server_id} 不在分组 {group_id} 中")
    logger.info("服务器 %s 已从分组 %s 移除", server_id, group_id)


async def get_group_members(group_id: str) -> list[dict]:
    """获取分组内所有服务器"""
    db = await get_db()
    # 验证分组存在
    group = await (
        await db.execute("SELECT id FROM server_groups WHERE id = ?", (group_id,))
    ).fetchone()
    if group is None:
        raise ValueError(f"分组 {group_id} 不存在")

    rows = await (
        await db.execute(
            "SELECT s.* FROM servers s "
            "JOIN server_group_members m ON m.server_id = s.id "
            "WHERE m.group_id = ? ORDER BY s.name",
            (group_id,),
        )
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


async def get_server_groups(server_id: str) -> list[dict]:
    """获取服务器所属的所有分组"""
    db = await get_db()
    rows = await (
        await db.execute(
            "SELECT g.* FROM server_groups g "
            "JOIN server_group_members m ON m.group_id = g.id "
            "WHERE m.server_id = ? ORDER BY g.name",
            (server_id,),
        )
    ).fetchall()
    return [dict(r) for r in rows]

"""SSH TOFU (Trust On First Use) 主机密钥管理

Trust On First Use: 首次连接时自动信任并保存主机密钥，
后续连接验证密钥一致性（不一致则拒绝，可能为 MITM 攻击）。
"""

import asyncio
import logging
import os

import asyncssh

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
)
KNOWN_HOSTS_PATH = os.path.join(_DATA_DIR, "ssh_known_hosts")

# 文件写入锁，防止并发 SSH 连接时 known_hosts 损坏
_write_lock = asyncio.Lock()


def _ensure_file() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(KNOWN_HOSTS_PATH):
        with open(KNOWN_HOSTS_PATH, "a"):
            pass


def _host_in_known_hosts(host: str, port: int) -> bool:
    """检查主机是否已在 known_hosts 文件中（不验证密钥，仅检查是否有记录）。"""
    try:
        known_hosts = asyncssh.read_known_hosts(KNOWN_HOSTS_PATH)
        trusted, _, _ = asyncssh.match_known_hosts(
            known_hosts, host, host, port,
        )[:3]
        return len(trusted) > 0
    except Exception:
        return False


def _save_host_key(host: str, port: int, server_host_key: asyncssh.SSHKey) -> None:
    """保存主机密钥到 known_hosts 文件（OpenSSH 格式）。"""
    _ensure_file()
    host_label = f"[{host}]:{port}" if port != 22 else host
    # export_public_key("openssh") 返回 "ssh-type AAAA..." 格式
    key_str = server_host_key.export_public_key("openssh").decode().strip()
    line = f"{host_label} {key_str}\n"
    with open(KNOWN_HOSTS_PATH, "a") as f:
        f.write(line)
    logger.info("SSH TOFU: 已保存主机密钥 host=%s port=%d", host, port)


async def tofu_connect(
    host: str, port: int = 22, *, accept_new: bool = True, **kwargs
) -> asyncssh.SSHClientConnection:
    """SSH 连接，使用 TOFU (Trust On First Use) 主机密钥验证。

    Args:
        host: 主机地址
        port: SSH 端口
        accept_new: 是否接受新主机密钥 (TOFU 信任)
        **kwargs: 传递给 asyncssh.connect 的其他参数

    Returns:
        asyncssh.SSHClientConnection

    Raises:
        asyncssh.HostKeyNotVerifiable: 主机密钥不匹配或新主机且 accept_new=False
    """
    _ensure_file()
    try:
        return await asyncssh.connect(
            host, port=port, known_hosts=KNOWN_HOSTS_PATH, **kwargs
        )
    except asyncssh.HostKeyNotVerifiable:
        # 区分"新主机"和"密钥变更"
        if _host_in_known_hosts(host, port):
            # 主机已记录但密钥不匹配 → 可能 MITM，拒绝连接
            logger.error(
                "SSH TOFU: 主机密钥不匹配! 可能存在 MITM 攻击 host=%s port=%d. "
                "如确认安全，请手动删除 %s 中对应条目",
                host, port, KNOWN_HOSTS_PATH,
            )
            raise

        # 新主机，TOFU 信任
        if not accept_new:
            raise

        logger.info("SSH TOFU: 首次连接新主机 host=%s port=%d, 信任其密钥", host, port)

        # 用 known_hosts=None 连接以获取服务端密钥
        conn = await asyncssh.connect(
            host, port=port, known_hosts=None, **kwargs
        )
        server_key = conn.get_server_host_key()
        async with _write_lock:
            _save_host_key(host, port, server_key)
        return conn

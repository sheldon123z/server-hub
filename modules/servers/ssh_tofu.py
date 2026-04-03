"""SSH TOFU (Trust On First Use) 主机密钥管理

Trust On First Use: 首次连接时自动信任并保存主机密钥，
后续连接验证密钥一致性（不一致则拒绝，可能为 MITM 攻击击）。
"""

import base64
import logging
import os

import asyncssh

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
)
KNOWN_HOSTS_PATH = os.path.join(_DATA_DIR, "ssh_known_hosts")


def _ensure_file() -> None:
    os.makedirs(_DATA_DIR, exist_ok=True)
    if not os.path.exists(KNOWN_HOSTS_PATH):
        open(KNOWN_HOSTS_PATH, "a").close()


def get_known_hosts_path() -> str | None:
    """返回 known_hosts 文件路径，确保文件存在。用于 asyncssh.connect(known_hosts=path)。"""
    try:
        _ensure_file()
        return KNOWN_HOSTS_PATH
    except Exception:
        return None


def _encode_host_key(host: str, port: int, server_host_key) -> str:
    """将 SSH 主机密钥编码为 known_hosts 行 (OpenSSH 格式)。"""
    host_label = f"[{host}]:{port}" if port != 22 else host
    key_b64 = base64.b64encode(server_host_key.data).decode()
    return f"{host_label} {server_host_key.key_type} {key_b64}\n"


def _save_host_key(host: str, port: int, server_host_key) -> None:
    """保存主机密钥到 known_hosts 文件。"""
    _ensure_file()
    line = _encode_host_key(host, port, server_host_key)
    with open(KNOWN_HOSTS_PATH, "a") as f:
        f.write(line)
    logger.info("SSH TOFU: 已保存主机密钥 host=%s port=%d", host, port)


async def tofu_connect(host: str, port: int = 22, *, accept_new: bool = True, **kwargs) -> asyncssh.SSHClientConnection:
    """
    SSH 连接，使用 TOFU (Trust On First Use) 主机密钥验证。

    Args:
        host: 主机地址
        port: SSH 端口
        accept_new: 是否接受新主机密钥 (TOFU 信任)
        **kwargs: 传递给 asyncssh.connect 的其他参数

    Returns:
        asyncssh.SSHClientConnection

    Raises:
        HostKeyMismatch: 主机密钥不匹配 (可能 MITM)
        HostKeyNotKnown: 新主机且 accept_new=False
    """
    _ensure_file()
    try:
        return await asyncssh.connect(host, port=port, known_hosts=KNOWN_HOSTS_PATH, **kwargs)
    except asyncssh.HostKeyNotKnown as exc:
        if not accept_new:
            raise
        logger.info("SSH TOFU: 发现新主机密钥 host=%s port=%d", host, port)
        _save_host_key(host, port, exc.server_host_key)
        return await asyncssh.connect(host, port=port, known_hosts=KNOWN_HOSTS_PATH, **kwargs)
    except asyncssh.hostKeyMismatch:
        logger.error(
            "SSH TOFU: 主机密钥不匹配! 可能存在 MITM 攻击 host=%s port=%d",
            host,
            port,
        )
        raise

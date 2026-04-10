"""Pipeline 安全工具 — Shell 转义、SSRF 防护、日志脱敏"""

import ipaddress
import re
import shlex
import socket
from urllib.parse import urlparse


def escape_for_shell(value: str) -> str:
    """用 shlex.quote() 转义注入 shell 命令的变量值"""
    return shlex.quote(str(value))


_PRIVATE_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


def is_url_safe(url: str) -> tuple[bool, str]:
    """SSRF 防护 — 检查 URL 目标是否为私有地址。

    先 DNS 解析再检查 IP，返回 (is_safe, reason) 元组。
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "无法解析主机名"

        # DNS 解析获取 IP
        try:
            addr_infos = socket.getaddrinfo(hostname, parsed.port or 80)
        except socket.gaierror:
            return False, f"DNS 解析失败: {hostname}"

        for _family, _type, _proto, _canonname, sockaddr in addr_infos:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)
            for network in _PRIVATE_NETWORKS:
                if ip in network:
                    return False, f"目标地址 {ip_str} 属于私有网络 {network}"

        return True, "ok"
    except Exception as exc:
        return False, f"URL 检查异常: {exc}"


_SENSITIVE_KEYS_RE = re.compile(
    r"(password|secret|token|api_key|apikey|private_key|credential)",
    re.IGNORECASE,
)


def redact_sensitive(data: dict) -> dict:
    """递归脱敏 dict 中包含敏感关键字的字段值为 '****'"""

    def _redact(obj):
        if isinstance(obj, dict):
            return {k: "****" if _SENSITIVE_KEYS_RE.search(k) else _redact(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_redact(item) for item in obj]
        return obj

    return _redact(data)

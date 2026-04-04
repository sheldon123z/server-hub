"""共享工具模块。"""

import os

from starlette.requests import Request

# 默认信任的代理 IP（本机回环），仅当直连 IP 在此集合中才读取 X-Forwarded-For / X-Real-IP
_DEFAULT_TRUSTED_PROXIES = {"127.0.0.1", "::1"}

_extra = os.environ.get("SERVERHUB_TRUSTED_PROXIES", "")
TRUSTED_PROXIES: set[str] = _DEFAULT_TRUSTED_PROXIES | {ip.strip() for ip in _extra.split(",") if ip.strip()}


def get_client_ip(request: Request) -> str:
    """
    提取真实客户端 IP，兼容 nginx 反代场景。

    仅当 request.client.host 在 TRUSTED_PROXIES 中时，
    才信任 X-Forwarded-For / X-Real-IP 头，防止客户端伪造 IP。

    优先级: X-Forwarded-For 第一个 IP > X-Real-IP > request.client.host
    """
    direct_ip = request.client.host if request.client else "unknown"

    # 只有来自可信代理的请求，才读取转发头
    if direct_ip not in TRUSTED_PROXIES:
        return direct_ip

    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2 — 取第一个（真实客户端）
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return direct_ip

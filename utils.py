"""通用工具函数"""

from starlette.requests import Request


def get_client_ip(request: Request) -> str:
    """
    提取真实客户端 IP，兼容 nginx 反代场景。

    优先级: X-Forwarded-For 第一个 IP > X-Real-IP > request.client.host
    当 nginx 反代时 request.client.host 始终为 127.0.0.1，
    必须从 X-Forwarded-For 头提取真实客户端 IP。
    """
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2 — 取第一个（真实客户端）
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "unknown"

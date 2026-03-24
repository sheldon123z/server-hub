"""
审计日志中间件
自动记录所有 POST/PUT/DELETE API 请求
"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from database import get_db

logger = logging.getLogger(__name__)


async def log_audit(
    username: str,
    action: str,
    target: str,
    details: str = "",
    ip: str = "",
    success: bool = True,
):
    """
    写入审计日志记录

    Args:
        username: 操作用户
        action: 操作类型 (POST/PUT/DELETE 等)
        target: 操作目标 (API 路径)
        details: 详细信息
        ip: 客户端 IP
        success: 是否成功
    """
    try:
        db = await get_db()
        await db.execute(
            "INSERT INTO audit_log (username, action, target, details, ip_address, success) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (username, action, target, details, ip, 1 if success else 0),
        )
        await db.commit()
    except Exception as e:
        logger.error(f"审计日志写入失败: {e}")


class AuditMiddleware(BaseHTTPMiddleware):
    """
    审计中间件: 记录所有 /api/ 路径下的 POST/PUT/DELETE 请求
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # 仅拦截写操作
        if request.method not in ("POST", "PUT", "DELETE"):
            return await call_next(request)

        # 仅拦截 API 路由
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # 提取用户名
        username = "anonymous"
        # request.state.user 由认证中间件设置
        if hasattr(request.state, "user") and request.state.user:
            user = request.state.user
            if isinstance(user, dict):
                username = user.get("username", "anonymous")
            elif hasattr(user, "username"):
                username = user.username

        # 客户端 IP
        ip = request.client.host if request.client else ""

        # 执行请求
        response = await call_next(request)

        # 记录审计日志
        success = 200 <= response.status_code < 400
        await log_audit(
            username=username,
            action=request.method,
            target=request.url.path,
            details=f"status={response.status_code}",
            ip=ip,
            success=success,
        )

        return response

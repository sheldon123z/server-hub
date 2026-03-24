"""认证依赖注入"""

from fastapi import Request, HTTPException, status
from auth.jwt_handler import verify_token
from auth.user_store import get_user_by_name
from auth.models import TokenData


async def get_current_user(request: Request) -> dict:
    """从 Cookie 或 Authorization Header 提取并验证用户"""
    token = None

    # 优先从 Cookie 读取
    token = request.cookies.get("access_token")

    # 回退到 Authorization Header
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    payload = verify_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期")

    user = await get_user_by_name(payload["sub"])
    if not user or user.get("disabled"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户已禁用")

    return user


def require_role(*roles: str):
    """角色校验依赖工厂"""
    async def checker(request: Request) -> dict:
        user = await get_current_user(request)
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user
    return checker

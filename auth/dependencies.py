"""认证依赖注入"""

from fastapi import HTTPException, Request, status

from auth.jwt_handler import verify_token
from auth.user_store import get_token_version, get_user_by_name


def extract_bearer_token(request: Request) -> str | None:
    """从 Cookie 或 Authorization Header 中提取访问令牌。"""
    token = None

    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    return token


async def get_user_from_access_token(token: str | None) -> dict | None:
    """校验访问令牌并返回用户。"""
    if not token:
        return None
    payload = verify_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user = await get_user_by_name(payload["sub"])
    if not user or user.get("disabled"):
        return None
    if int(payload.get("ver", 0)) != get_token_version(user):
        return None

    return user


async def get_user_from_token(token: str | None, *, token_type: str) -> tuple[dict | None, dict | None]:
    """校验指定类型令牌并返回用户和载荷。"""
    if not token:
        return None, None

    payload = verify_token(token)
    if not payload or payload.get("type") != token_type:
        return None, None

    user = await get_user_by_name(payload["sub"])
    if not user or user.get("disabled"):
        return None, None
    if int(payload.get("ver", 0)) != get_token_version(user):
        return None, None
    return user, payload


async def get_current_user_optional(request: Request) -> dict | None:
    """尝试从请求中解析用户，失败时返回 None。"""
    return await get_user_from_access_token(extract_bearer_token(request))


async def get_current_user(request: Request) -> dict:
    """从 Cookie 或 Authorization Header 提取并验证用户。"""
    user = await get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效、已失效或未登录")
    return user


def require_role(*roles: str):
    """角色校验依赖工厂"""

    async def checker(request: Request) -> dict:
        user = await get_current_user(request)
        if user["role"] not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return checker

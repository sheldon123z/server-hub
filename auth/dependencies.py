"""认证依赖注入"""

import logging

from fastapi import HTTPException, Request, status

from auth.jwt_handler import verify_token
from auth.user_store import get_token_version, get_user_by_name

logger = logging.getLogger(__name__)


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


def require_permission(resource: str, action: str = "read"):
    """权限校验依赖工厂 — 基于 RBAC 角色权限矩阵。

    用法: user=Depends(require_permission("docker", "write"))
    降级策略: RBAC 不可用时仅允许 role="admin" 的用户通过。
    """

    async def checker(request: Request) -> dict:
        user = await get_current_user(request)
        try:
            from modules.rbac.services import has_permission as _has_perm

            if not await _has_perm(str(user["id"]), resource, action):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"缺少权限: {resource}:{action}",
                )
        except HTTPException:
            raise
        except Exception:
            logger.debug("RBAC 不可用，降级到 role 字段检查", exc_info=True)
            if user.get("role") != "admin":
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")
        return user

    return checker


def require_role(*roles: str):
    """角色校验依赖工厂 — 向后兼容，内部委托 RBAC 检查。

    require_role("admin") 映射为 has_permission("*", "admin")，
    RBAC 不可用时降级到旧 role 字段检查。
    """

    async def checker(request: Request) -> dict:
        user = await get_current_user(request)
        # RBAC 优先: 角色名映射为 has_permission("*", role_name)
        try:
            from modules.rbac.services import has_permission as _has_perm

            for role in roles:
                if await _has_perm(str(user["id"]), "*", role):
                    return user
        except Exception:
            logger.debug("RBAC 不可用，降级到旧 role 字段检查", exc_info=True)
        # 降级兜底: 旧 role 字段检查
        if user.get("role") in roles:
            return user
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    return checker

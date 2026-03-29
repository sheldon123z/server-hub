"""认证路由"""

import logging
import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth.dependencies import get_current_user, get_user_from_token
from auth.jwt_handler import create_access_token, create_refresh_token
from auth.models import ChangePasswordRequest, LoginRequest
from auth.user_store import (
    authenticate,
    get_token_version,
    hash_password,
    verify_password,
)
from config import settings
from database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["认证"])


# ─── 登录速率限制（内存实现） ───

# {ip: [timestamp, timestamp, ...]}  — 滑动窗口内的请求时间戳
_login_attempts: dict[str, list[float]] = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # 秒
_RATE_LIMIT_MAX = 5  # 窗口内最大尝试次数


def _check_login_rate_limit(client_ip: str) -> None:
    """检查登录速率限制，超限则抛出 429"""
    now = time.time()
    attempts = _login_attempts[client_ip]
    # 清理过期记录
    _login_attempts[client_ip] = [t for t in attempts if now - t < _RATE_LIMIT_WINDOW]
    attempts = _login_attempts[client_ip]

    if len(attempts) >= _RATE_LIMIT_MAX:
        logger.warning("登录速率限制触发: IP=%s, 尝试次数=%d/%d", client_ip, len(attempts), _RATE_LIMIT_MAX)
        raise HTTPException(
            status_code=429,
            detail=f"登录尝试过于频繁，请 {_RATE_LIMIT_WINDOW} 秒后重试",
        )


def _record_login_attempt(client_ip: str) -> None:
    """记录一次登录尝试"""
    _login_attempts[client_ip].append(time.time())


def _cookie_secure(request: Request) -> bool:
    """根据部署模式决定是否启用 Secure Cookie。"""
    if settings.cookie_secure_mode in {"1", "true", "yes", "always"}:
        return True
    if settings.cookie_secure_mode in {"0", "false", "no", "never"}:
        return False
    forwarded = request.headers.get("x-forwarded-proto", "")
    if forwarded:
        return forwarded.split(",")[0].strip().lower() == "https"
    return request.url.scheme == "https"


def _set_auth_cookie(response: Response, key: str, value: str, max_age: int, secure: bool) -> None:
    """统一设置认证 Cookie。"""
    response.set_cookie(
        key=key,
        value=value,
        httponly=True,
        samesite=settings.cookie_samesite,
        secure=secure,
        max_age=max_age,
    )


def _clear_auth_cookies(response: Response, secure: bool) -> None:
    """统一清理认证 Cookie。"""
    response.delete_cookie("access_token", secure=secure, samesite=settings.cookie_samesite)
    response.delete_cookie("refresh_token", secure=secure, samesite=settings.cookie_samesite)


@router.post("/login")
async def login(req: LoginRequest, response: Response, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate_limit(client_ip)
    _record_login_attempt(client_ip)

    user = await authenticate(req.username, req.password)
    if not user:
        logger.warning("登录失败: username=%s, IP=%s", req.username, client_ip)
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    secure = _cookie_secure(request)
    token_version = get_token_version(user)
    access_token = create_access_token(user["username"], user["role"], token_version)
    refresh_token = create_refresh_token(user["username"], token_version)

    _set_auth_cookie(response, "access_token", access_token, 86400, secure)
    _set_auth_cookie(response, "refresh_token", refresh_token, 86400 * 30, secure)

    return {
        "ok": True,
        "user": {
            "username": user["username"],
            "display_name": user["display_name"],
            "role": user["role"],
        },
    }


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    user, _ = await get_user_from_token(token, token_type="refresh")  # noqa: S106 — token_type 非密码
    if not user:
        raise HTTPException(status_code=401, detail="会话已失效，请重新登录")

    access_token = create_access_token(user["username"], user["role"], get_token_version(user))
    _set_auth_cookie(response, "access_token", access_token, 86400, _cookie_secure(request))
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    response: Response,
    user=Depends(get_current_user),
):
    if not verify_password(req.old_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="原密码错误")

    db = await get_db()
    await db.execute(
        "UPDATE panel_users SET hashed_password = ?, token_version = COALESCE(token_version, 0) + 1 WHERE id = ?",
        (hash_password(req.new_password), user["id"]),
    )
    await db.commit()
    _clear_auth_cookies(response, _cookie_secure(request))
    return {"ok": True, "reauth_required": True}


@router.post("/logout")
async def logout(request: Request, response: Response):
    _clear_auth_cookies(response, _cookie_secure(request))
    return {"ok": True}

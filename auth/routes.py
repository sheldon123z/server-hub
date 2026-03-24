"""认证路由"""

from fastapi import APIRouter, HTTPException, Response, Depends, Request
from auth.dependencies import get_current_user, get_user_from_token
from auth.jwt_handler import create_access_token, create_refresh_token
from auth.models import ChangePasswordRequest, LoginRequest
from auth.user_store import (
    authenticate,
    get_token_version,
    verify_password,
    hash_password,
)
from config import settings
from database import get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


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
    user = await authenticate(req.username, req.password)
    if not user:
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
    user, _ = await get_user_from_token(token, token_type="refresh")
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

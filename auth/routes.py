"""认证路由"""

from fastapi import APIRouter, HTTPException, Response, Depends, Request
from auth.models import LoginRequest, ChangePasswordRequest
from auth.jwt_handler import create_access_token, create_refresh_token, verify_token
from auth.user_store import authenticate, get_user_by_name, verify_password, hash_password
from auth.dependencies import get_current_user
from database import get_db

router = APIRouter(prefix="/api/auth", tags=["认证"])


@router.post("/login")
async def login(req: LoginRequest, response: Response):
    user = await authenticate(req.username, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    access_token = create_access_token(user["username"], user["role"])
    refresh_token = create_refresh_token(user["username"])

    # 设置 HttpOnly Cookie
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=86400,  # 24h
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        max_age=86400 * 30,
    )

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
    if not token:
        raise HTTPException(status_code=401, detail="无刷新令牌")

    payload = verify_token(token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="刷新令牌无效")

    user = await get_user_by_name(payload["sub"])
    if not user or user.get("disabled"):
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    access_token = create_access_token(user["username"], user["role"])
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        max_age=86400,
    )
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return {
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


@router.post("/change-password")
async def change_password(req: ChangePasswordRequest, user=Depends(get_current_user)):
    if not verify_password(req.old_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="原密码错误")

    db = await get_db()
    await db.execute(
        "UPDATE panel_users SET hashed_password = ? WHERE id = ?",
        (hash_password(req.new_password), user["id"]),
    )
    await db.commit()
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token")
    return {"ok": True}

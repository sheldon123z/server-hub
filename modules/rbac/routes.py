"""RBAC 权限管理 API 路由

提供角色、权限、用户角色分配的 CRUD 接口。
所有管理操作均需要 rbac:admin 权限（内置角色: super-admin）。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.dependencies import get_current_user, require_permission
from modules.rbac.models import AssignRoleRequest, RoleCreate, RoleUpdate
from modules.rbac.services import (
    assign_role,
    create_role,
    delete_role,
    get_all_roles,
    get_role_permissions,
    get_user_permissions,
    get_user_roles,
    remove_role,
    update_role,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rbac", tags=["权限管理"])

_ADMIN = Depends(require_permission("rbac", "admin"))


class SetPermissionsRequest(BaseModel):
    permissions: list[dict]


# ─── 角色管理 ───


@router.get("/roles")
async def list_roles(_user=_ADMIN):
    """列出所有角色（含权限）。"""
    roles = await get_all_roles()
    return [r.model_dump() for r in roles]


@router.post("/roles")
async def create_role_endpoint(body: RoleCreate, user=_ADMIN):
    """创建自定义角色。"""
    try:
        role = await create_role(body.name, body.display_name, body.description, body.permissions)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    logger.info("RBAC: 用户 %s 创建角色 %s", user.get("id"), role.name)
    return {"ok": True, "role": role.model_dump()}


@router.put("/roles/{role_id}")
async def update_role_endpoint(role_id: str, body: RoleUpdate, user=_ADMIN):
    """更新角色信息（内置角色不允许修改权限）。"""
    role = await update_role(role_id, body.display_name, body.description, body.permissions)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    logger.info("RBAC: 用户 %s 更新角色 %s", user.get("id"), role_id)
    return {"ok": True, "role": role.model_dump()}


@router.delete("/roles/{role_id}")
async def delete_role_endpoint(role_id: str, user=_ADMIN):
    """删除自定义角色（内置角色不可删除）。"""
    try:
        deleted = await delete_role(role_id)
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="角色不存在")
    logger.info("RBAC: 用户 %s 删除角色 %s", user.get("id"), role_id)
    return {"ok": True}


# ─── 角色权限 ───


@router.get("/roles/{role_id}/permissions")
async def get_permissions(role_id: str, _user=_ADMIN):
    """获取角色的权限列表。"""
    perms = await get_role_permissions(role_id)
    return {"role_id": role_id, "permissions": [p.model_dump() for p in perms]}


@router.put("/roles/{role_id}/permissions")
async def set_permissions(role_id: str, body: SetPermissionsRequest, user=_ADMIN):
    """设置角色权限（替换全部权限，内置角色不可修改）。"""
    role = await update_role(role_id, permissions=body.permissions)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    logger.info("RBAC: 用户 %s 更新角色 %s 权限", user.get("id"), role_id)
    return {"ok": True, "permissions": [p.model_dump() for p in role.permissions]}


# ─── 用户角色分配 ───


@router.get("/users/{user_id}/roles")
async def get_user_role_list(user_id: str, _user=_ADMIN):
    """获取用户的角色 ID 列表。"""
    roles = await get_user_roles(user_id)
    return {"user_id": user_id, "roles": roles}


@router.put("/users/{user_id}/roles")
async def assign_user_role(user_id: str, body: AssignRoleRequest, user=_ADMIN):
    """为用户分配角色（幂等）。"""
    await assign_role(user_id, body.role_id)
    logger.info("RBAC: 用户 %s 为 %s 分配角色 %s", user.get("id"), user_id, body.role_id)
    roles = await get_user_roles(user_id)
    return {"ok": True, "user_id": user_id, "roles": roles}


@router.delete("/users/{user_id}/roles/{role_id}")
async def remove_user_role(user_id: str, role_id: str, user=_ADMIN):
    """移除用户的指定角色。"""
    await remove_role(user_id, role_id)
    logger.info("RBAC: 用户 %s 从 %s 移除角色 %s", user.get("id"), user_id, role_id)
    return {"ok": True}


# ─── 当前用户权限查询 ───


@router.get("/users/me/permissions")
async def get_my_permissions(user=Depends(get_current_user)):
    """获取当前登录用户的权限列表。"""
    user_id = str(user.get("id") or user.get("username", ""))
    perms = await get_user_permissions(user_id)
    return {"user_id": user_id, "permissions": [p.model_dump() for p in perms]}

"""RBAC 权限管理 API 路由"""

import logging

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user, require_role
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

router = APIRouter(prefix="/api/rbac", tags=["rbac"])


@router.get("/roles")
async def list_roles(_user=Depends(require_role("admin"))):
    """列出所有角色（含权限）。"""
    roles = await get_all_roles()
    return [r.model_dump() for r in roles]


@router.post("/roles")
async def create_role_endpoint(body: RoleCreate, _user=Depends(require_role("admin"))):
    """创建自定义角色。"""
    try:
        role = await create_role(body.name, body.display_name, body.description, body.permissions)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "role": role.model_dump()}


@router.get("/roles/{role_id}/permissions")
async def get_permissions(role_id: str, _user=Depends(require_role("admin"))):
    """获取角色的权限列表。"""
    perms = await get_role_permissions(role_id)
    return [p.model_dump() for p in perms]


@router.put("/roles/{role_id}")
async def update_role_endpoint(role_id: str, body: RoleUpdate, _user=Depends(require_role("admin"))):
    """更新角色信息。"""
    role = await update_role(role_id, body.display_name, body.description, body.permissions)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"ok": True, "role": role.model_dump()}


@router.delete("/roles/{role_id}")
async def delete_role_endpoint(role_id: str, _user=Depends(require_role("admin"))):
    """删除自定义角色。"""
    try:
        deleted = await delete_role(role_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="角色不存在")
    return {"ok": True}


@router.get("/users/{user_id}/roles")
async def get_user_role_list(user_id: str, _user=Depends(require_role("admin"))):
    """获取用户的角色列表。"""
    roles = await get_user_roles(user_id)
    return roles


@router.post("/users/{user_id}/roles")
async def assign_user_role(user_id: str, body: AssignRoleRequest, _user=Depends(require_role("admin"))):
    """为用户分配角色。"""
    await assign_role(user_id, body.role_id)
    return {"ok": True}


@router.delete("/users/{user_id}/roles/{role_id}")
async def remove_user_role(user_id: str, role_id: str, _user=Depends(require_role("admin"))):
    """移除用户的角色。"""
    await remove_role(user_id, role_id)
    return {"ok": True}


@router.get("/users/me/permissions")
async def get_my_permissions(user=Depends(get_current_user)):
    """获取当前用户的权限列表。"""
    perms = await get_user_permissions(str(user["id"] if "id" in user else user["username"]))
    return [p.model_dump() for p in perms]

"""多服务器管理 API 路由"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.dependencies import require_role
from modules.servers.schemas import (
    ServerCreateRequest,
    ServerGroupCreateRequest,
    ServerUpdateRequest,
)
from modules.servers.services import (
    add_server_to_group,
    create_group,
    create_server_with_token,
    delete_group,
    delete_server,
    get_fleet_overview,
    get_group_members,
    get_server,
    list_groups,
    list_servers,
    remove_server_from_group,
    rotate_agent_token,
    test_connectivity,
    update_server,
)

router = APIRouter(prefix="/api/servers", tags=["服务器管理"])


# ─── 舰队概览 ───


@router.get("/overview")
async def fleet_overview(user=Depends(require_role("admin"))):
    """获取服务器舰队概览统计"""
    return await get_fleet_overview()


# ─── 服务器分组 (必须在 /{server_id} 之前注册，避免路由冲突) ───


@router.get("/groups")
async def api_list_groups(user=Depends(require_role("admin"))):
    """列出所有服务器分组"""
    return await list_groups()


@router.post("/groups")
async def api_create_group(
    body: ServerGroupCreateRequest,
    user=Depends(require_role("admin")),
):
    """创建服务器分组"""
    try:
        group_id = await create_group(body.model_dump())
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail=f"分组名 {body.name} 已存在")
        raise
    return {"ok": True, "id": group_id}


@router.delete("/groups/{group_id}")
async def api_delete_group(group_id: str, user=Depends(require_role("admin"))):
    """删除服务器分组"""
    try:
        await delete_group(group_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


# ─── 分组成员管理 ───


class GroupMemberRequest(BaseModel):
    server_id: str


@router.get("/groups/{group_id}/members")
async def api_get_group_members(group_id: str, user=Depends(require_role("admin"))):
    """列出分组内所有服务器"""
    try:
        return await get_group_members(group_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/groups/{group_id}/members")
async def api_add_group_member(
    group_id: str,
    body: GroupMemberRequest,
    user=Depends(require_role("admin")),
):
    """将服务器添加到分组"""
    try:
        await add_server_to_group(group_id, body.server_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.delete("/groups/{group_id}/members/{server_id}")
async def api_remove_group_member(
    group_id: str,
    server_id: str,
    user=Depends(require_role("admin")),
):
    """从分组中移除服务器"""
    try:
        await remove_server_from_group(group_id, server_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


# ─── 服务器 CRUD ───


@router.get("/")
async def api_list_servers(
    status: str | None = None,
    user=Depends(require_role("admin")),
):
    """列出所有服务器"""
    return await list_servers(status_filter=status)


@router.get("/{server_id}")
async def api_get_server(server_id: str, user=Depends(require_role("admin"))):
    """获取单个服务器详情"""
    server = await get_server(server_id)
    if server is None:
        raise HTTPException(status_code=404, detail=f"服务器 {server_id} 不存在")
    return server


@router.post("/")
async def api_create_server(
    body: ServerCreateRequest,
    user=Depends(require_role("admin")),
):
    """注册新服务器，返回一次性可见的 agent token"""
    try:
        server_id, agent_token = await create_server_with_token(body.model_dump(), created_by=user["username"])
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail=f"服务器名称 '{body.name}' 已存在")
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": server_id, "agent_token": agent_token}


@router.put("/{server_id}")
async def api_update_server(
    server_id: str,
    body: ServerUpdateRequest,
    user=Depends(require_role("admin")),
):
    """更新服务器信息"""
    try:
        await update_server(server_id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@router.delete("/{server_id}")
async def api_delete_server(server_id: str, user=Depends(require_role("admin"))):
    """删除服务器"""
    try:
        await delete_server(server_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}


# ─── 连通性测试 ───


@router.post("/{server_id}/test")
async def api_test_connectivity(server_id: str, user=Depends(require_role("admin"))):
    """测试服务器连通性"""
    try:
        result = await test_connectivity(server_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, **result}


# ─── Token 管理 ───


@router.post("/{server_id}/rotate-token")
async def api_rotate_token(server_id: str, user=Depends(require_role("admin"))):
    """轮换服务器 agent token，返回一次性可见的新 token"""
    try:
        new_token = await rotate_agent_token(server_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True, "token": new_token}

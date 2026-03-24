"""
用户管理 API 路由
提供用户列表、进程终止、配额管理接口
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.dependencies import get_current_user, require_role
from modules.users.services import (
    get_user_stats,
    kill_user_processes,
    read_quotas,
    save_quotas,
)

router = APIRouter(prefix="/api/users", tags=["用户管理"])


class QuotaEntry(BaseModel):
    key: str
    mem_gb: int
    proc_limit: int
    comment: str = ""


@router.get("/")
async def list_users(user=Depends(get_current_user)):
    """获取所有用户资源使用统计"""
    import asyncio
    stats = await asyncio.get_event_loop().run_in_executor(None, get_user_stats)
    return stats


@router.post("/{username}/kill")
async def kill_user(username: str, user=Depends(require_role("admin"))):
    """终止指定用户的所有进程（仅管理员）"""
    result = kill_user_processes(username)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"ok": True, "message": f"已终止用户 {username} 的所有进程"}


@router.get("/quotas")
async def list_quotas(user=Depends(require_role("admin"))):
    """获取所有配额配置（仅管理员）"""
    return read_quotas()


@router.put("/quotas")
async def update_quotas(
    quotas: list[QuotaEntry],
    user=Depends(require_role("admin")),
):
    """全量替换配额配置（仅管理员）"""
    save_quotas([q.model_dump() for q in quotas])
    return {"ok": True, "message": "配额已更新"}


@router.post("/quotas")
async def add_quota(
    quota: QuotaEntry,
    user=Depends(require_role("admin")),
):
    """添加单条配额（仅管理员）"""
    quotas = read_quotas()
    # 检查是否已存在
    for q in quotas:
        if q["key"] == quota.key:
            raise HTTPException(status_code=409, detail=f"配额 {quota.key} 已存在")
    quotas.append(quota.model_dump())
    save_quotas(quotas)
    return {"ok": True, "message": f"已添加配额 {quota.key}"}


@router.delete("/quotas/{key}")
async def delete_quota(key: str, user=Depends(require_role("admin"))):
    """删除指定配额（仅管理员）"""
    quotas = read_quotas()
    new_quotas = [q for q in quotas if q["key"] != key]
    if len(new_quotas) == len(quotas):
        raise HTTPException(status_code=404, detail=f"配额 {key} 不存在")
    save_quotas(new_quotas)
    return {"ok": True, "message": f"已删除配额 {key}"}

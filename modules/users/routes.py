"""
用户管理 API 路由
提供用户列表、进程终止、配额管理、用户增删改、登录审计接口
"""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user, require_role
from modules.audit.middleware import log_audit
from modules.users.services import (
    get_user_stats,
    kill_user_processes,
    read_quotas,
    save_quotas,
    get_all_linux_users,
    get_user_login_history,
    get_active_sessions,
    create_linux_user,
    delete_linux_user,
    modify_linux_user,
    set_user_password,
    kill_single_process,
)

router = APIRouter(prefix="/api/users", tags=["用户管理"])


# ─── Request Models ───

class QuotaEntry(BaseModel):
    key: str
    mem_gb: int
    proc_limit: int
    comment: str = ""


class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=32, pattern=r"^[a-zA-Z0-9_-]+$")
    groups: str = ""
    shell: str = "/bin/bash"
    password: str = Field("", min_length=0, max_length=128)


class ModifyUserRequest(BaseModel):
    groups: str | None = None
    shell: str | None = None


class SetPasswordRequest(BaseModel):
    password: str = Field(..., min_length=6, max_length=128)


# ─── 资源监控 ───

@router.get("/")
async def list_users(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    """获取所有用户资源使用统计"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.user_stats()
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        return result["data"].get("users", [])
    stats = await asyncio.to_thread(get_user_stats)
    return stats


# ─── 用户列表与详情 ───

@router.get("/all")
async def list_all_users(user=Depends(require_role("admin"))):
    """获取所有 Linux 用户详细信息（含管理员）"""
    users = await asyncio.to_thread(get_all_linux_users)
    return {"users": users}


# ─── 登录审计 ───

@router.get("/sessions")
async def active_sessions(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    """获取当前活跃登录会话"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.user_sessions()
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        # 解析 who 输出
        sessions = []
        for line in result["data"].get("output", "").strip().splitlines():
            parts = line.split()
            if len(parts) >= 3:
                sessions.append({
                    "user": parts[0],
                    "terminal": parts[1],
                    "login_time": " ".join(parts[2:4]) if len(parts) >= 4 else parts[2],
                    "from": parts[4].strip("()") if len(parts) >= 5 else "",
                })
        return {"sessions": sessions, "count": len(sessions)}
    sessions = await asyncio.to_thread(get_active_sessions)
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/{username}/history")
async def user_login_history(username: str, count: int = 20, user=Depends(require_role("admin"))):
    """获取指定用户的登录历史"""
    try:
        entries = await asyncio.to_thread(get_user_login_history, username, count)
        return {"entries": entries, "count": len(entries)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── 配额状态 & 处置策略（固定路径必须在 /{username} 之前） ───

@router.get("/quota-status")
async def quota_status(user=Depends(get_current_user)):
    """获取所有用户配额使用状态"""
    from modules.users.services import get_quota_status
    return get_quota_status()


@router.get("/enforcement")
async def get_enforcement(user=Depends(require_role("admin"))):
    """获取处置策略配置"""
    from modules.users.services import get_enforcement_config
    return get_enforcement_config()


@router.put("/enforcement")
async def update_enforcement(request: Request, user=Depends(require_role("admin"))):
    """更新处置策略配置"""
    from modules.users.services import save_enforcement_config
    data = await request.json()
    save_enforcement_config(data)
    return {"ok": True}


@router.get("/violations")
async def get_violations(
    limit: int = 50, offset: int = 0,
    user=Depends(require_role("admin")),
):
    """获取配额违规历史"""
    from database import get_db
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, username, violation_type, mem_gb, quota_mem_gb, usage_pct, action_taken, created_at "
        "FROM quota_violations ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0], "username": r[1], "type": r[2],
            "mem_gb": r[3], "quota_mem_gb": r[4], "usage_pct": r[5],
            "action": r[6], "time": r[7],
        }
        for r in rows
    ]


# ─── 用户增删改 ───

@router.post("/create")
async def do_create_user(body: CreateUserRequest, request: Request, user=Depends(require_role("admin"))):
    """创建新的 Linux 用户"""
    result = await asyncio.to_thread(create_linux_user, body.username, body.groups, body.shell)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])

    # 设置密码（如果提供）
    if body.password:
        pwd_result = await asyncio.to_thread(set_user_password, body.username, body.password)
        if not pwd_result["ok"]:
            return {"ok": True, "warning": f"用户已创建，但设置密码失败: {pwd_result['error']}"}

    await log_audit(
        username=user["username"],
        action="user.create",
        target=body.username,
        ip=request.client.host if request.client else "unknown",
        detail=f"groups={body.groups}, shell={body.shell}",
    )
    return {"ok": True, "message": f"用户 {body.username} 已创建"}


@router.delete("/{username}")
async def do_delete_user(
    username: str,
    request: Request,
    remove_home: bool = False,
    user=Depends(require_role("admin")),
):
    """删除 Linux 用户"""
    result = await asyncio.to_thread(delete_linux_user, username, remove_home)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])

    await log_audit(
        username=user["username"],
        action="user.delete",
        target=username,
        ip=request.client.host if request.client else "unknown",
        detail=f"remove_home={remove_home}",
    )
    return {"ok": True, "message": f"用户 {username} 已删除"}


@router.put("/{username}")
async def do_modify_user(
    username: str,
    body: ModifyUserRequest,
    request: Request,
    user=Depends(require_role("admin")),
):
    """修改用户属性（组、shell）"""
    result = await asyncio.to_thread(modify_linux_user, username, body.groups, body.shell)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])

    await log_audit(
        username=user["username"],
        action="user.modify",
        target=username,
        ip=request.client.host if request.client else "unknown",
        detail=f"groups={body.groups}, shell={body.shell}",
    )
    return {"ok": True, "message": f"用户 {username} 已修改"}


@router.post("/{username}/password")
async def do_set_password(
    username: str,
    body: SetPasswordRequest,
    request: Request,
    user=Depends(require_role("admin")),
):
    """设置用户密码"""
    result = await asyncio.to_thread(set_user_password, username, body.password)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])

    await log_audit(
        username=user["username"],
        action="user.password",
        target=username,
        ip=request.client.host if request.client else "unknown",
    )
    return {"ok": True, "message": f"用户 {username} 的密码已更新"}


# ─── 进程管理 ───

@router.post("/{username}/kill")
async def kill_user(username: str, request: Request, user=Depends(require_role("admin"))):
    """终止指定用户的所有进程（仅管理员）"""
    result = kill_user_processes(username)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])

    await log_audit(
        username=user["username"],
        action="user.kill_all",
        target=username,
        ip=request.client.host if request.client else "unknown",
    )
    return {"ok": True, "message": f"已终止用户 {username} 的所有进程"}


@router.post("/{username}/kill/{pid}")
async def kill_process(
    username: str,
    pid: int,
    request: Request,
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(require_role("admin")),
):
    """终止指定用户的单个进程"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.kill_process(pid)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        await log_audit(
            username=user["username"],
            action="user.kill_process",
            target=f"{server_id}:{username}:{pid}",
            ip=request.client.host if request.client else "unknown",
        )
        return {"ok": True, "message": f"已终止远程进程 {pid}"}
    result = await asyncio.to_thread(kill_single_process, pid, username)
    if not result["ok"]:
        raise HTTPException(status_code=400, detail=result["error"])

    await log_audit(
        username=user["username"],
        action="user.kill_process",
        target=f"{username}:{pid}",
        ip=request.client.host if request.client else "unknown",
    )
    return {"ok": True, "message": f"已终止进程 {pid}"}


# ─── 配额管理 ───

@router.get("/quotas")
async def list_quotas(user=Depends(require_role("admin"))):
    """获取所有配额配置（仅管理员）"""
    return read_quotas()


@router.put("/quotas")
async def update_quotas(quotas: list[QuotaEntry], user=Depends(require_role("admin"))):
    """全量替换配额配置（仅管理员）"""
    save_quotas([q.model_dump() for q in quotas])
    return {"ok": True, "message": "配额已更新"}


@router.post("/quotas")
async def add_quota(quota: QuotaEntry, user=Depends(require_role("admin"))):
    """添加单条配额（仅管理员）"""
    quotas = read_quotas()
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


# ─── 进程列表 (需要在 /{username} DELETE 之后) ───

@router.get("/{username}/processes")
async def user_processes(
    username: str, sort: str = "mem", search: str = "",
    user=Depends(require_role("admin")),
):
    """获取用户完整进程列表"""
    from modules.users.services import get_user_processes
    procs = get_user_processes(username, sort_by=sort, search=search)
    return {"processes": procs, "count": len(procs)}

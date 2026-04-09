"""Cron 任务 API — 查看 + CRUD + 备份"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user, require_role
from modules.audit.middleware import log_audit
from modules.cron.services import (
    add_cron_job,
    backup_crontab,
    delete_cron_job,
    get_cron_history,
    get_root_crontab,
    get_user_crontab,
    list_cron_backups,
    toggle_cron_job,
    update_cron_schedule,
    validate_cron_expression,
)

router = APIRouter(prefix="/api/cron", tags=["定时任务"])


# ─── Request Models ───


class UpdateScheduleRequest(BaseModel):
    cron_user: str
    old_schedule: str
    command: str
    new_schedule: str


class CreateJobRequest(BaseModel):
    cron_user: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    schedule: str
    command: str = Field(..., min_length=1)
    comment: str = ""


class DeleteJobRequest(BaseModel):
    cron_user: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    schedule: str
    command: str


class ToggleJobRequest(BaseModel):
    cron_user: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    schedule: str
    command: str
    enabled: bool


class ValidateRequest(BaseModel):
    expression: str


# ─── 查询端点 ───


@router.get("")
@router.get("/")
async def list_user_crontab(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client

        client = await get_agent_client(server_id)
        result = await client.cron_list()
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        return {"jobs_raw": result["data"].get("output", ""), "user": "remote"}
    try:
        entries = await get_user_crontab()
        return {"jobs": entries, "user": "zhengxiaodong"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/root")
async def list_root_crontab(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(require_role("admin")),
):
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client

        client = await get_agent_client(server_id)
        result = await client.cron_list(user="root")
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        return {"jobs_raw": result["data"].get("output", ""), "user": "root"}
    try:
        entries = await get_root_crontab()
        return {"jobs": entries, "user": "root"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 验证 ───


@router.post("/validate")
async def validate_expression(body: ValidateRequest, user=Depends(get_current_user)):
    """验证 cron 表达式，返回中文描述和未来 5 次执行时间"""
    return validate_cron_expression(body.expression)


# ─── CRUD 端点 ───


@router.put("/schedule")
async def update_schedule(body: UpdateScheduleRequest, request: Request, user=Depends(require_role("admin"))):
    """修改 cron 任务的执行时间"""
    try:
        await update_cron_schedule(
            cron_user=body.cron_user,
            old_schedule=body.old_schedule,
            old_command=body.command,
            new_schedule=body.new_schedule,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action="cron.modify",
        target=f"{body.cron_user}: {body.command[:60]}",
        ip=request.client.host if request.client else "unknown",
        detail=f"{body.old_schedule} -> {body.new_schedule}",
    )
    return {"ok": True, "new_schedule": body.new_schedule}


@router.post("/jobs")
async def create_job(body: CreateJobRequest, request: Request, user=Depends(require_role("admin"))):
    """创建新的 cron 任务"""
    try:
        await add_cron_job(
            cron_user=body.cron_user,
            schedule=body.schedule,
            command=body.command,
            comment=body.comment,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action="cron.create",
        target=f"{body.cron_user}: {body.command[:60]}",
        ip=request.client.host if request.client else "unknown",
        detail=f"schedule={body.schedule}",
    )
    return {"ok": True, "schedule": body.schedule, "command": body.command}


@router.delete("/jobs")
async def remove_job(body: DeleteJobRequest, request: Request, user=Depends(require_role("admin"))):
    """删除 cron 任务"""
    try:
        await delete_cron_job(
            cron_user=body.cron_user,
            schedule=body.schedule,
            command=body.command,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action="cron.delete",
        target=f"{body.cron_user}: {body.command[:60]}",
        ip=request.client.host if request.client else "unknown",
        detail=f"schedule={body.schedule}",
    )
    return {"ok": True}


@router.put("/jobs/toggle")
async def toggle_job(body: ToggleJobRequest, request: Request, user=Depends(require_role("admin"))):
    """启用或禁用 cron 任务"""
    try:
        await toggle_cron_job(
            cron_user=body.cron_user,
            schedule=body.schedule,
            command=body.command,
            enabled=body.enabled,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    action = "cron.enable" if body.enabled else "cron.disable"
    await log_audit(
        username=user["username"],
        action=action,
        target=f"{body.cron_user}: {body.command[:60]}",
        ip=request.client.host if request.client else "unknown",
    )
    return {"ok": True, "enabled": body.enabled}


# ─── 历史 ───


@router.get("/history")
async def cron_history(
    pattern: str = "",
    hours: int = 24,
    user=Depends(require_role("admin")),
):
    """获取 cron 执行历史（从 journal）"""
    if hours < 1 or hours > 720:
        raise HTTPException(status_code=400, detail="hours 范围 1-720")
    try:
        entries = await get_cron_history(command_pattern=pattern, hours=hours)
        return {"entries": entries, "count": len(entries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 备份 ───


@router.post("/backup")
async def do_backup(request: Request, cron_user: str = "zhengxiaodong", user=Depends(require_role("admin"))):
    """备份指定用户的 crontab"""
    try:
        path = await backup_crontab(cron_user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action="cron.backup",
        target=cron_user,
        ip=request.client.host if request.client else "unknown",
        detail=path,
    )
    return {"ok": True, "path": path}


@router.get("/backups")
async def list_backups(cron_user: str = "", user=Depends(require_role("admin"))):
    """列出可用的 crontab 备份"""
    return {"backups": list_cron_backups(cron_user)}

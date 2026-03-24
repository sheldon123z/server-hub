"""Cron 任务 API — 查看 + 修改时间"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.dependencies import get_current_user, require_role
from modules.cron.services import get_user_crontab, get_root_crontab, update_cron_schedule

router = APIRouter(prefix="/api/cron", tags=["定时任务"])


class UpdateScheduleRequest(BaseModel):
    cron_user: str          # "root" 或 "zhengxiaodong"
    old_schedule: str       # 原表达式
    command: str            # 命令（用于匹配）
    new_schedule: str       # 新表达式


@router.get("/")
async def list_user_crontab(user=Depends(get_current_user)):
    try:
        entries = await get_user_crontab()
        return {"jobs": entries, "user": "zhengxiaodong"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/root")
async def list_root_crontab(user=Depends(require_role("admin"))):
    try:
        entries = await get_root_crontab()
        return {"jobs": entries, "user": "root"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/schedule")
async def update_schedule(body: UpdateScheduleRequest, user=Depends(require_role("admin"))):
    """修改 cron 任务的执行时间"""
    try:
        await update_cron_schedule(
            cron_user=body.cron_user,
            old_schedule=body.old_schedule,
            old_command=body.command,
            new_schedule=body.new_schedule,
        )
        return {"ok": True, "new_schedule": body.new_schedule}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

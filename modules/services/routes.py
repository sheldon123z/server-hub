"""
服务管理 API 路由
提供 systemd 服务的查询与控制接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth.dependencies import get_current_user, require_role
from modules.services.services import (
    list_services,
    service_status,
    service_action,
    service_journal,
)
from modules.audit.middleware import log_audit

router = APIRouter(prefix="/api/services", tags=["服务管理"])


@router.get("/")
async def get_services(user=Depends(get_current_user)):
    """列出所有受管 systemd 服务的状态"""
    try:
        return await list_services()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{name}/status")
async def get_service_status(
    name: str,
    user=Depends(get_current_user),
):
    """获取服务的详细状态信息"""
    try:
        output = await service_status(name)
        return {"name": name, "status": output}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{name}/{action}")
async def do_service_action(
    name: str,
    action: str,
    request: Request,
    user=Depends(require_role("admin")),
):
    """对服务执行 start / stop / restart（仅管理员）"""
    try:
        result = await service_action(name, action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action=f"service.{action}",
        target=name,
        ip=request.client.host if request.client else "unknown",
        detail=result,
    )

    return {"ok": True, "action": action, "service": name, "output": result}


@router.get("/{name}/journal")
async def get_service_journal(
    name: str,
    lines: int = Query(default=100, ge=1, le=5000),
    user=Depends(get_current_user),
):
    """获取服务的 journal 日志"""
    try:
        output = await service_journal(name, lines=lines)
        return {"name": name, "journal": output}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

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
    service_enable_disable,
    service_reload,
    service_resource_usage,
    service_dependencies,
)
from modules.audit.middleware import log_audit

router = APIRouter(prefix="/api/services", tags=["服务管理"])


@router.get("/")
async def get_services(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    """列出所有受管 systemd 服务的状态"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.get_services()
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        # Agent 返回 {"services": [...], "total": N}，前端期望数组
        data = result.get("data", {})
        return data.get("services", []) if isinstance(data, dict) else data
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
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(require_role("admin")),
):
    """对服务执行 start / stop / restart（仅管理员）"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        if action not in ("start", "stop", "restart"):
            raise HTTPException(status_code=400, detail=f"不支持的操作: {action}")
        client = await get_agent_client(server_id)
        result = await client.service_action(name, action)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        await log_audit(
            username=user["username"],
            action=f"service.{action}",
            target=f"{server_id}:{name}",
            ip=request.client.host if request.client else "unknown",
            detail=result["data"].get("output", ""),
        )
        return {"ok": True, "action": action, "service": name, "output": result["data"].get("output", "")}
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


@router.post("/{name}/enable")
async def do_enable(name: str, request: Request, user=Depends(require_role("admin"))):
    """启用服务自启动"""
    try:
        result = await service_enable_disable(name, "enable")
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    await log_audit(
        username=user["username"], action="service.enable", target=name,
        ip=request.client.host if request.client else "unknown",
    )
    return {"ok": True, "service": name, "output": result}


@router.post("/{name}/disable")
async def do_disable(name: str, request: Request, user=Depends(require_role("admin"))):
    """禁用服务自启动"""
    try:
        result = await service_enable_disable(name, "disable")
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    await log_audit(
        username=user["username"], action="service.disable", target=name,
        ip=request.client.host if request.client else "unknown",
    )
    return {"ok": True, "service": name, "output": result}


@router.post("/{name}/reload")
async def do_reload(name: str, request: Request, user=Depends(require_role("admin"))):
    """重新加载服务配置"""
    try:
        result = await service_reload(name)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    await log_audit(
        username=user["username"], action="service.reload", target=name,
        ip=request.client.host if request.client else "unknown",
    )
    return {"ok": True, "service": name, "output": result}


@router.get("/{name}/resources")
async def get_resources(name: str, user=Depends(get_current_user)):
    """获取服务资源使用情况"""
    try:
        return await service_resource_usage(name)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{name}/dependencies")
async def get_deps(name: str, user=Depends(get_current_user)):
    """获取服务依赖关系"""
    try:
        return await service_dependencies(name)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{name}/journal")
async def get_service_journal(
    name: str,
    lines: int = Query(default=100, ge=1, le=5000),
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    """获取服务的 journal 日志"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.service_journal(name, lines=lines)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        return {"name": name, "journal": result["data"].get("output", "")}
    try:
        output = await service_journal(name, lines=lines)
        return {"name": name, "journal": output}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

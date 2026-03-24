"""
Docker 管理 API 路由
提供容器、镜像、Compose 堆栈的查询与管理接口
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth.dependencies import get_current_user, require_role
from modules.docker.services import (
    list_containers,
    container_logs,
    container_stats,
    container_inspect,
    container_action,
    list_images,
    remove_image,
    list_compose_stacks,
    compose_action,
)
from modules.audit.middleware import log_audit

router = APIRouter(prefix="/api/docker", tags=["Docker"])


@router.get("/containers")
async def get_containers(
    all: bool = Query(default=True, description="包含已停止的容器"),
    user=Depends(get_current_user),
):
    """列出所有 Docker 容器"""
    try:
        return await list_containers(all=all)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/containers/{name}/logs")
async def get_container_logs(
    name: str,
    tail: int = Query(default=100, ge=1, le=5000),
    user=Depends(get_current_user),
):
    """获取容器日志"""
    try:
        logs = await container_logs(name, tail=tail)
        return {"name": name, "logs": logs}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/containers/{name}/stats")
async def get_container_stats(
    name: str,
    user=Depends(get_current_user),
):
    """获取容器资源使用统计"""
    try:
        return await container_stats(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/containers/{name}/inspect")
async def get_container_inspect(
    name: str,
    user=Depends(require_role("admin")),
):
    """获取容器完整 inspect 信息（仅管理员）"""
    try:
        return await container_inspect(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/containers/{name}/{action}")
async def do_container_action(
    name: str,
    action: str,
    request: Request,
    user=Depends(require_role("admin")),
):
    """对容器执行 start / stop / restart（仅管理员）"""
    try:
        result = await container_action(name, action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action=f"docker.container.{action}",
        target=name,
        ip=request.client.host if request.client else "unknown",
        detail=result,
    )

    return {"ok": True, "action": action, "container": name, "output": result}


@router.get("/images")
async def get_images(user=Depends(get_current_user)):
    """列出本地 Docker 镜像"""
    try:
        return await list_images()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/images/{image_id:path}")
async def delete_image(
    image_id: str,
    request: Request,
    user=Depends(require_role("admin")),
):
    """删除 Docker 镜像（仅管理员）"""
    try:
        result = await remove_image(image_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action="docker.image.remove",
        target=image_id,
        ip=request.client.host if request.client else "unknown",
        detail=result,
    )

    return {"ok": True, "image_id": image_id, "output": result}


@router.get("/stacks")
async def get_stacks(user=Depends(get_current_user)):
    """列出 Docker Compose 堆栈"""
    try:
        return await list_compose_stacks()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stacks/{name}/{action}")
async def do_stack_action(
    name: str,
    action: str,
    request: Request,
    user=Depends(require_role("admin")),
):
    """管理 Compose 堆栈: up / down / restart / pull（仅管理员）"""
    try:
        result = await compose_action(name, action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action=f"docker.stack.{action}",
        target=name,
        ip=request.client.host if request.client else "unknown",
        detail=result,
    )

    return {"ok": True, "action": action, "stack": name, "output": result}

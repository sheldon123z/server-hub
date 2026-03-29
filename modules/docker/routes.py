"""
Docker 管理 API 路由
提供容器、镜像、Compose 堆栈的查询与管理接口
"""

import contextlib

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user, require_role
from modules.audit.middleware import log_audit
from modules.docker.services import (
    compose_action,
    container_action,
    container_exec,
    container_inspect,
    container_logs,
    container_stats,
    get_container_env,
    list_compose_stacks,
    list_containers,
    list_images,
    list_networks,
    list_volumes,
    prune_resources,
    pull_image,
    remove_image,
)

router = APIRouter(prefix="/api/docker", tags=["Docker"])


@router.get("/containers")
async def get_containers(
    all: bool = Query(default=True, description="包含已停止的容器"),
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    """列出所有 Docker 容器"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client

        client = await get_agent_client(server_id)
        result = await client.get_docker_containers()
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        # Agent 返回 {"containers": [...], "total": N}，前端期望数组
        data = result.get("data", {})
        return data.get("containers", []) if isinstance(data, dict) else data
    try:
        return await list_containers(all=all)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/containers/{name}/logs")
async def get_container_logs(
    name: str,
    tail: int = Query(default=100, ge=1, le=5000),
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    """获取容器日志"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client

        client = await get_agent_client(server_id)
        result = await client.docker_action(name, "logs", tail=tail)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        return {"name": name, "logs": result["data"].get("output", "")}
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
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(require_role("admin")),
):
    """对容器执行 start / stop / restart（仅管理员）"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client

        if action not in ("start", "stop", "restart"):
            raise HTTPException(status_code=400, detail=f"不支持的操作: {action}")
        client = await get_agent_client(server_id)
        result = await client.docker_action(name, action)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        await log_audit(
            username=user["username"],
            action=f"docker.container.{action}",
            target=f"{server_id}:{name}",
            ip=request.client.host if request.client else "unknown",
            detail=result["data"].get("output", ""),
        )
        return {"ok": True, "action": action, "container": name, "output": result["data"].get("output", "")}
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
async def get_images(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    """列出本地 Docker 镜像"""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client

        client = await get_agent_client(server_id)
        result = await client.docker_images()
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        import json

        images = []
        for line in result["data"].get("output", "").strip().splitlines():
            line = line.strip()
            if line:
                with contextlib.suppress(json.JSONDecodeError):
                    images.append(json.loads(line))
        return images
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
async def get_stacks(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(get_current_user),
):
    """列出 Docker Compose 堆栈"""
    if server_id != "local":
        import json

        from modules.servers.agent_client import get_agent_client

        client = await get_agent_client(server_id)
        result = await client.docker_stacks()
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        output = result["data"].get("output", "").strip()
        try:
            return json.loads(output) if output else []
        except json.JSONDecodeError:
            return []
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


# ─── 网络 ───


@router.get("/networks")
async def get_networks(user=Depends(get_current_user)):
    """列出 Docker 网络"""
    try:
        return {"networks": await list_networks()}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 卷 ───


@router.get("/volumes")
async def get_volumes(user=Depends(get_current_user)):
    """列出 Docker 卷"""
    try:
        return {"volumes": await list_volumes()}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── 镜像拉取 ───


class PullImageRequest(BaseModel):
    image: str = Field(..., min_length=1, max_length=200)


@router.post("/images/pull")
async def do_pull_image(body: PullImageRequest, request: Request, user=Depends(require_role("admin"))):
    """拉取 Docker 镜像"""
    try:
        result = await pull_image(body.image)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    await log_audit(
        username=user["username"],
        action="docker.image.pull",
        target=body.image,
        ip=request.client.host if request.client else "unknown",
    )
    return {"ok": True, "output": result}


# ─── 容器 Exec ───


class ExecRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=500)


@router.post("/containers/{name}/exec")
async def do_container_exec(name: str, body: ExecRequest, request: Request, user=Depends(require_role("admin"))):
    """在容器内执行命令"""
    try:
        output = await container_exec(name, body.command)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

    await log_audit(
        username=user["username"],
        action="docker.container.exec",
        target=name,
        ip=request.client.host if request.client else "unknown",
        detail=body.command[:100],
    )
    return {"ok": True, "output": output}


# ─── 资源清理 ───


@router.post("/prune/{resource_type}")
async def do_prune(resource_type: str, request: Request, user=Depends(require_role("admin"))):
    """清理未使用的 Docker 资源"""
    try:
        result = await prune_resources(resource_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    await log_audit(
        username=user["username"],
        action=f"docker.prune.{resource_type}",
        target=resource_type,
        ip=request.client.host if request.client else "unknown",
        detail=result[:200],
    )
    return {"ok": True, "output": result}


# ─── 容器环境变量 ───


@router.get("/containers/{name}/env")
async def get_env(name: str, user=Depends(require_role("admin"))):
    """获取容器环境变量（敏感值已脱敏）"""
    try:
        envs = await get_container_env(name)
        return {"envs": envs}
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))

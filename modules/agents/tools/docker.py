"""Docker 容器管理工具"""

from langchain_core.tools import tool
from config import settings


@tool
async def list_docker_containers(server_id: str = "local") -> str:
    """列出所有 Docker 容器及其运行状态。

    Args:
        server_id: 目标服务器ID。'local' 表示本机。
    """
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.get_docker_containers()
        if not result.get("ok"):
            return f"远程获取失败: {result.get('error', '未知')}"
        import json
        return json.dumps(result["data"], ensure_ascii=False, indent=2)

    from modules.docker.services import list_containers
    containers = await list_containers(all=True)
    if not containers:
        return "当前没有 Docker 容器。"
    lines = ["## Docker 容器\n| 容器 | 状态 | 镜像 |", "|---|---|---|"]
    for c in containers:
        name = c.get("Names") or c.get("name", "?")
        status = c.get("Status") or c.get("status", "?")
        image = c.get("Image") or c.get("image", "?")
        lines.append(f"| {name} | {status} | {image[:40]} |")
    return "\n".join(lines)


@tool
async def get_container_logs(name: str, tail: int = 50, server_id: str = "local") -> str:
    """获取指定 Docker 容器的最近日志。

    Args:
        name: 容器名称
        tail: 获取最后多少行，默认50
        server_id: 目标服务器ID。'local' 表示本机。
    """
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.docker_action(name, "logs", tail=min(tail, 200))
        if not result.get("ok"):
            return f"远程获取失败: {result.get('error', '未知')}"
        output = result["data"].get("output", "")
        if not output.strip():
            return f"容器 {name} 没有日志输出。"
        return f"## {name} 日志 (最后{tail}行)\n```\n{output[-3000:]}\n```"

    from modules.docker.services import container_logs
    logs = await container_logs(name, tail=min(tail, 200))
    if not logs:
        return f"容器 {name} 没有日志输出。"
    return f"## {name} 日志 (最后{tail}行)\n```\n{logs[-3000:]}\n```"


@tool
async def docker_container_action(name: str, action: str, server_id: str = "local") -> str:
    """对 Docker 容器执行操作。

    Args:
        name: 容器名称
        action: 操作类型，可选 start, stop, restart
        server_id: 目标服务器ID。'local' 表示本机。
    """
    if action not in ("start", "stop", "restart"):
        return f"不支持的操作: {action}。可选: start, stop, restart"

    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.docker_action(name, action)
        if not result.get("ok"):
            return f"远程执行失败: {result.get('error', '未知')}"
        return f"容器 {name} 已在远程服务器 {server_id} 上执行 {action}。"

    from modules.docker.services import container_action
    result = await container_action(name, action)
    return f"容器 {name} 已执行 {action}。{result}"


@tool
async def docker_compose_action(stack_name: str, action: str) -> str:
    """对 Docker Compose 堆栈执行操作。

    Args:
        stack_name: 堆栈名称 (dify, lobe, grid-autopilot)
        action: 操作类型，可选 up, down, restart, pull
    """
    if stack_name not in settings.compose_stacks:
        return f"未知堆栈: {stack_name}。可选: {', '.join(settings.compose_stacks.keys())}"
    if action not in ("up", "down", "restart", "pull"):
        return f"不支持的操作: {action}。可选: up, down, restart, pull"
    from modules.docker.services import compose_action
    result = await compose_action(stack_name, action)
    return f"堆栈 {stack_name} 已执行 {action}。{result}"


@tool
async def list_docker_networks() -> str:
    """列出 Docker 网络，包含名称、驱动和范围。"""
    from modules.docker.services import list_networks
    networks = await list_networks()
    if not networks:
        return "没有 Docker 网络"
    lines = [f"## Docker 网络 ({len(networks)} 个)\n"]
    for n in networks:
        lines.append(f"- **{n['name']}** — 驱动: {n['driver']}, 范围: {n['scope']}")
    return "\n".join(lines)


@tool
async def docker_container_exec(container_name: str, command: str) -> str:
    """在运行中的 Docker 容器内执行命令。"""
    from modules.docker.services import container_exec
    try:
        output = await container_exec(container_name, command)
        return f"容器 {container_name} 执行结果:\n```\n{output[:5000]}\n```"
    except (ValueError, RuntimeError) as e:
        return f"执行失败: {e}"


@tool
async def docker_prune(resource_type: str = "all") -> str:
    """清理未使用的 Docker 资源。此操作不可逆。"""
    from modules.docker.services import prune_resources
    try:
        result = await prune_resources(resource_type)
        return f"清理完成 ({resource_type}):\n{result[:2000]}"
    except (ValueError, RuntimeError) as e:
        return f"清理失败: {e}"

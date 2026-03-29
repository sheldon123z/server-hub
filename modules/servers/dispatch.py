"""多服务器调度层 — 根据 server_id 路由到本机或远程"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)


async def dispatch(server_id: str, local_fn: Callable[..., Awaitable[Any]], agent_endpoint: str = "", **kwargs) -> Any:
    """根据 server_id 调度到本地或远程执行

    Args:
        server_id: 'local' 为本机，其他为远程服务器 ID
        local_fn: 本地执行函数 (async callable)
        agent_endpoint: 远程 Agent API 端点 (如 '/metrics', '/docker/containers')
        **kwargs: 传递给 local_fn 或远程请求的参数
    """
    if server_id == "local":
        return await local_fn(**kwargs)

    from modules.servers.agent_client import get_agent_client

    client = await get_agent_client(server_id)

    if agent_endpoint:
        result = await client._request("GET", agent_endpoint)
        if result.get("ok"):
            return result["data"]
        raise RuntimeError(f"远程执行失败: {result.get('error', '未知错误')}")

    raise ValueError("远程执行需要指定 agent_endpoint")


async def dispatch_command(server_id: str, command: str, timeout: int = 30) -> dict:  # noqa: ASYNC109 — timeout 传给 asyncio.wait_for
    """在指定服务器上执行命令

    ⚠️ 已废弃: 此函数使用 create_subprocess_shell，存在 shell 注入风险。
    请使用 AgentClient 的结构化方法 (service_action, docker_action 等) 替代。
    保留仅为向后兼容，不应在新代码中使用。
    """
    import warnings

    warnings.warn(
        "dispatch_command 使用 shell 执行，存在注入风险，请迁移到结构化 action 方法",
        DeprecationWarning,
        stacklevel=2,
    )
    if server_id == "local":
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "exit_code": proc.returncode,
        }

    from modules.servers.agent_client import get_agent_client

    client = await get_agent_client(server_id)
    return await client.execute_command(command, timeout=timeout)

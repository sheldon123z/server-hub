"""服务器舰队管理工具 — 列出/查询/测试已注册的服务器"""

import json
from langchain_core.tools import tool


@tool
async def server_list() -> str:
    """列出所有已注册的服务器，包括状态和基本信息。

    Returns:
        JSON 格式的服务器列表，包含 id/名称/IP/状态/标签/最后心跳。
    """
    from modules.servers.services import list_servers
    servers = await list_servers()
    if not servers:
        return "当前没有已注册的服务器。"

    lines = [f"已注册 {len(servers)} 台服务器:\n"]
    for s in servers:
        status_icon = {"online": "🟢", "offline": "🔴", "degraded": "🟡"}.get(s["status"], "⚪")
        local_tag = " (本机)" if s.get("is_local") else ""
        tags = json.loads(s.get("tags", "[]")) if isinstance(s.get("tags"), str) else s.get("tags", [])
        tag_str = f" [{', '.join(tags)}]" if tags else ""
        lines.append(
            f"- {status_icon} **{s['name']}**{local_tag} — {s['ip_address']} | "
            f"状态: {s['status']}{tag_str}"
        )
    return "\n".join(lines)


@tool
async def server_test_connectivity(server_id: str) -> str:
    """测试指定服务器的连通性（Ping + SSH + Agent API）。

    Args:
        server_id: 服务器 ID（可通过 server_list 工具获取）

    Returns:
        连通性测试结果，包含 Ping 延迟、SSH 连接状态、Agent API 状态。
    """
    from modules.servers.services import get_server, test_connectivity

    server = await get_server(server_id)
    if not server:
        return f"服务器 {server_id} 不存在。请使用 server_list 查看已注册的服务器。"

    result = await test_connectivity(server_id)

    lines = [f"**{server['name']}** ({server['ip_address']}) 连通性测试结果:\n"]

    # Ping
    if result.get("ping_ok"):
        lines.append(f"- ✅ Ping: {result.get('ping_ms', '?')}ms")
    else:
        lines.append("- ❌ Ping: 不可达")

    # SSH
    if result.get("ssh_ok"):
        lines.append(f"- ✅ SSH: 连接成功 (端口 {server.get('ssh_port', 22)})")
    else:
        err = result.get("ssh_error", "未知错误")
        lines.append(f"- ❌ SSH: {err}")

    # Agent
    if result.get("agent_ok"):
        ver = result.get("agent_version", "unknown")
        lines.append(f"- ✅ Agent: 在线 (版本 {ver})")
    else:
        lines.append(f"- ⚠️ Agent: 未检测到 (端口 {server.get('agent_port', 9901)})")

    return "\n".join(lines)

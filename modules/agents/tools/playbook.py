"""运维剧本工具 — SSH 远程执行 + 剧本 CRUD"""

import asyncio
import json
import logging
import re

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# SSH 命令黑名单
SSH_COMMAND_BLACKLIST = [
    r"\brm\s+-rf\s+/",
    r"\bmkfs\b",
    r"\bdd\s+if=",
    r"\bformat\b",
    r"\berase\b",
    r">\s*/dev/sd",
    r"\breboot\b",
    r"\bshutdown\b",
    r"\binit\s+0\b",
    r"\bpoweroff\b",
]


def _check_ssh_command_safety(cmd: str) -> str | None:
    for pattern in SSH_COMMAND_BLACKLIST:
        if re.search(pattern, cmd, re.IGNORECASE):
            return f"命令被安全策略阻止: '{cmd}' 匹配黑名单规则 '{pattern}'"
    return None


@tool
async def ssh_execute_command(
    host: str,
    username: str,
    password: str = "",
    private_key_path: str = "",
    commands: list[str] = [],
    port: int = 22,
    timeout: int = 30,
) -> str:
    """SSH connect to a remote device and execute commands. Use for network device management
    (switches, routers) and remote server operations.

    Args:
        host: Target device IP or hostname
        username: SSH username
        password: SSH password (use either password or private_key_path)
        private_key_path: Path to SSH private key file
        commands: List of commands to execute sequentially
        port: SSH port, default 22
        timeout: Connection timeout in seconds
    """
    import asyncssh

    if not commands:
        return "错误: 未指定要执行的命令"

    # Safety check
    for cmd in commands:
        violation = _check_ssh_command_safety(cmd)
        if violation:
            return violation

    # Build connection options
    connect_opts = {
        "host": host,
        "port": port,
        "username": username,
        "known_hosts": None,  # Skip host key verification for managed devices
        "connect_timeout": timeout,
    }
    if password:
        connect_opts["password"] = password
    elif private_key_path:
        connect_opts["client_keys"] = [private_key_path]
    else:
        return "错误: 必须提供 password 或 private_key_path"

    results = []
    try:
        async with asyncssh.connect(**connect_opts) as conn:
            for cmd in commands:
                try:
                    result = await asyncio.wait_for(
                        conn.run(cmd, check=False),
                        timeout=timeout,
                    )
                    output = (result.stdout or "").strip()
                    stderr = (result.stderr or "").strip()
                    # Truncate long output
                    if len(output) > 10000:
                        output = output[:10000] + "\n... (输出已截断)"
                    # Strip ANSI escape codes
                    output = re.sub(r"\x1b\[[0-9;]*m", "", output)

                    entry = f"## {cmd}\n"
                    if result.exit_status != 0:
                        entry += f"退出码: {result.exit_status}\n"
                    if output:
                        entry += f"```\n{output}\n```\n"
                    if stderr:
                        entry += f"STDERR:\n```\n{stderr[:2000]}\n```\n"
                    results.append(entry)
                except TimeoutError:
                    results.append(f"## {cmd}\n命令执行超时 ({timeout}s)\n")
    except asyncssh.DisconnectError as e:
        return f"SSH 连接断开: {e}"
    except asyncssh.PermissionDenied:
        return f"SSH 认证失败: 用户名或密码错误 ({username}@{host}:{port})"
    except (OSError, asyncssh.Error) as e:
        return f"SSH 连接失败: {e} ({host}:{port})"

    return f"# SSH 执行结果 ({host})\n\n" + "\n".join(results)


@tool
async def playbook_create(
    id: str,
    name: str,
    description: str,
    category: str,
    system_prompt: str,
    parameters: str,
    tools_required: str,
    validation_rules: str = "{}",
    trigger_type: str = "manual",
) -> str:
    """Create a new ops playbook (reusable workflow template).

    Args:
        id: Unique playbook ID (snake_case, e.g. 'check_nginx_config')
        name: Display name (Chinese)
        description: What this playbook does
        category: Category (network/system/docker/security/general)
        system_prompt: Execution prompt template with {param_name} placeholders
        parameters: JSON string of parameter definitions array
        tools_required: Comma-separated tool names needed
        validation_rules: JSON string of execution constraints
        trigger_type: Trigger mode (manual/schedule/event/api)
    """
    from modules.playbooks.services import create_playbook

    try:
        json.loads(parameters)  # validate JSON
        json.loads(validation_rules)
    except json.JSONDecodeError as e:
        return f"JSON 格式错误: {e}"

    try:
        await create_playbook(
            {
                "id": id,
                "name": name,
                "description": description,
                "category": category,
                "system_prompt": system_prompt,
                "parameters": parameters,
                "tools_required": tools_required,
                "validation_rules": validation_rules,
                "trigger_config": json.dumps({"type": trigger_type}),
            },
            created_by="agent",
        )
        return f"剧本已创建: {name} (ID: {id})\n类别: {category}\n工具: {tools_required}\n触发方式: {trigger_type}"
    except Exception as e:
        return f"创建失败: {e}"


@tool
async def playbook_execute(playbook_id: str, parameters: str = "{}") -> str:
    """Execute a saved ops playbook with the given parameters.

    Args:
        playbook_id: The playbook ID to execute
        parameters: JSON string of parameter key-value pairs
    """
    from modules.playbooks.services import execute_playbook

    try:
        params = json.loads(parameters)
    except json.JSONDecodeError:
        return "参数 JSON 格式错误"
    try:
        exec_id, status, report = await execute_playbook(playbook_id, params, "agent", "chat")
        if report:
            return f"剧本执行完成 (ID: {exec_id}, 状态: {status})\n\n{report}"
        return f"剧本执行完成 (ID: {exec_id}, 状态: {status})"
    except ValueError as e:
        return f"执行失败: {e}"
    except Exception as e:
        return f"执行出错: {e}"


@tool
async def playbook_list(category: str = "") -> str:
    """List available ops playbooks, optionally filtered by category.

    Args:
        category: Filter by category (network/system/docker/security/general). Empty for all.
    """
    from modules.playbooks.services import list_playbooks

    playbooks = await list_playbooks(category or None)
    if not playbooks:
        return "没有可用的剧本。" + (f" (类别: {category})" if category else "")
    lines = ["## 可用剧本\n| ID | 名称 | 类别 | 工具 | 触发 |", "|---|---|---|---|---|"]
    for pb in playbooks:
        trigger = json.loads(pb.get("trigger_config") or "{}").get("type", "manual")
        lines.append(f"| {pb['id']} | {pb['name']} | {pb['category']} | {pb['tools_required'][:30]} | {trigger} |")
    return "\n".join(lines)


@tool
async def playbook_search(keyword: str) -> str:
    """Search playbooks by keyword in name, description, or tags.

    Args:
        keyword: Search keyword
    """
    from modules.playbooks.services import list_playbooks

    all_pbs = await list_playbooks()
    matches = [
        pb
        for pb in all_pbs
        if keyword.lower() in (pb.get("name", "") + pb.get("description", "") + pb.get("tags", "")).lower()
    ]
    if not matches:
        return f"未找到匹配 '{keyword}' 的剧本"
    lines = [f"## 搜索结果: '{keyword}' ({len(matches)} 条)\n"]
    for pb in matches:
        lines.append(f"- **{pb['name']}** (`{pb['id']}`) — {pb.get('description', '')[:80]}")
    return "\n".join(lines)

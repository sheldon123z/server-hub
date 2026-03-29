"""运维脚本桥接工具"""

from langchain_core.tools import tool


@tool
async def execute_ops_script(script_key: str, args: list[str] | None = None) -> str:
    """执行注册的运维管理脚本。

    Args:
        script_key: 脚本标识（如 dify_manage, health_check, block_baidupan 等）
        args: 脚本参数列表
    """
    if args is None:
        args = []
    from scripts_bridge.registry import SCRIPT_REGISTRY

    if script_key not in SCRIPT_REGISTRY:
        available = ", ".join(SCRIPT_REGISTRY.keys())
        return f"未知脚本: {script_key}。可用: {available}"
    from scripts_bridge.executor import execute_script

    result = await execute_script(script_key, args, username="agent", ip="127.0.0.1")
    output = result.get("stdout", "")
    if result.get("exit_code", 1) != 0:
        output += f"\n[ERROR] {result.get('stderr', '')}"
    return f"脚本 {script_key} 执行结果:\n```\n{output[:3000]}\n```"

"""Systemd 服务管理工具"""

from langchain_core.tools import tool
from config import settings


@tool
async def list_systemd_services() -> str:
    """列出所有管理的 systemd 服务及其状态。"""
    from modules.services.services import list_services
    services = await list_services()
    if not services:
        return "没有管理的服务。"
    lines = ["## Systemd 服务\n| 服务 | 状态 | 启用 |", "|---|---|---|"]
    for s in services:
        status = "运行中" if s.get("active") else "已停止"
        enabled = "是" if s.get("enabled") else "否"
        lines.append(f"| {s['name']} | {status} | {enabled} |")
    return "\n".join(lines)


@tool
async def get_service_logs(name: str, lines: int = 50) -> str:
    """获取指定 systemd 服务的日志。

    Args:
        name: 服务名称（必须在管理列表中）
        lines: 获取最后多少行，默认50
    """
    if name not in settings.managed_services:
        return f"服务 {name} 不在管理列表中。可管理的服务: {', '.join(settings.managed_services)}"
    from modules.services.services import service_journal
    journal = await service_journal(name, lines=min(lines, 200))
    return f"## {name} 日志\n```\n{journal[-3000:]}\n```"


@tool
async def service_control(name: str, action: str) -> str:
    """管理 systemd 服务。

    Args:
        name: 服务名称（必须在管理列表中）
        action: 操作类型，可选 start, stop, restart
    """
    if name not in settings.managed_services:
        return f"服务 {name} 不在管理列表中。可管理: {', '.join(settings.managed_services)}"
    if action not in ("start", "stop", "restart"):
        return f"不支持的操作: {action}。可选: start, stop, restart"
    from modules.services.services import service_action
    result = await service_action(name, action)
    return f"服务 {name} 已执行 {action}。{result}"


@tool
async def service_enable_disable_tool(name: str, action: str) -> str:
    """启用或禁用 systemd 服务的自启动。"""
    from modules.services.services import service_enable_disable
    try:
        await service_enable_disable(name, action)
        action_cn = "启用" if action == "enable" else "禁用"
        return f"已{action_cn}服务 {name} 的自启动"
    except (ValueError, RuntimeError) as e:
        return f"操作失败: {e}"


@tool
async def get_service_dependencies_tool(name: str) -> str:
    """获取 systemd 服务的依赖关系树。"""
    from modules.services.services import service_dependencies
    try:
        result = await service_dependencies(name)
        deps = result["dependencies"]
        if not deps:
            return f"服务 {name} 没有依赖项"
        lines = [f"## {name} 的依赖关系 ({len(deps)} 项)\n"]
        for d in deps[:30]:
            lines.append(f"- {d}")
        return "\n".join(lines)
    except (ValueError, RuntimeError) as e:
        return f"查询失败: {e}"

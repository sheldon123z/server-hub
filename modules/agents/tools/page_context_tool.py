"""页面上下文数据查询工具"""

from langchain_core.tools import tool


@tool
async def get_page_data(page_name: str) -> str:
    """获取指定页面的实时数据摘要。当用户从页面内气泡对话框提问时，用此工具获取该页面的最新数据。

    Args:
        page_name: 页面标识，可选值: dashboard, monitoring, docker, users, services, cron, network, proxy, logs, notifications, settings, assets, audit, panel_users
    """
    from modules.agents.page_context import get_page_context

    result = await get_page_context(page_name)
    if not result:
        return f"未找到页面 '{page_name}' 的数据提供器。可用页面: dashboard, docker, users, services, cron, monitoring, network, proxy"
    return result

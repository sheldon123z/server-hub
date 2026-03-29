"""通知工具"""

from langchain_core.tools import tool


@tool
async def send_notification(message: str) -> str:
    """发送通知到所有启用的通知渠道（Telegram、企业微信、钉钉等）。

    Args:
        message: 消息内容
    """
    from modules.notifications.services import send_notification as broadcast_notification

    results = await broadcast_notification(message)
    success = sum(1 for r in results if r.get("success"))
    failed = len(results) - success
    if failed == 0:
        return f"通知已发送成功，共 {success} 个渠道。"
    return f"通知发送完成: {success} 个渠道成功, {failed} 个渠道失败。"

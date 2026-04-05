"""通知分发器 — 将通知路由到所有已启用渠道并写入站内通知"""

import logging

logger = logging.getLogger(__name__)


async def dispatch(
    title: str,
    content: str,
    severity: str = "info",
    user_id: str | None = None,
    type: str = "system",
    related_alert_id: str | None = None,
    channel_ids: list[str] | None = None,
) -> dict:
    """分发通知：写入站内通知表 + 广播到外部渠道。

    Returns:
        {"inapp_id": int, "channel_results": [...]}
    """
    # 延迟导入避免循环依赖
    from modules.notifications.services import (
        create_inapp_notification,
        send_notification,
    )

    message = f"[{severity.upper()}] {title}\n{content}" if content else f"[{severity.upper()}] {title}"

    # 并发执行：写站内通知 + 发外部渠道
    import asyncio

    inapp_task = asyncio.create_task(
        create_inapp_notification(
            title=title,
            content=content,
            severity=severity,
            user_id=user_id,
            type=type,
            related_alert_id=related_alert_id,
        )
    )
    channel_task = asyncio.create_task(send_notification(message, channel_ids=channel_ids))

    inapp_record, channel_results = await asyncio.gather(inapp_task, channel_task, return_exceptions=True)

    if isinstance(inapp_record, Exception):
        logger.error("站内通知写入失败: %s", inapp_record)
        inapp_record = None
    if isinstance(channel_results, Exception):
        logger.error("渠道发送失败: %s", channel_results)
        channel_results = []

    return {
        "inapp_id": inapp_record.get("id") if inapp_record else None,
        "channel_results": channel_results,
    }

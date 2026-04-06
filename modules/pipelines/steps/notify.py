"""Notify Step 执行器 — 调用已有通知系统发送消息"""

import logging

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("notify")
class NotifyStepExecutor:
    """通过已有三渠道通知系统发送消息"""

    async def execute(self, config: dict, state: dict) -> dict:
        from modules.notifications.services import send_notification

        message = config.get("message", "")
        channel = config.get("channel")

        if not message:
            return {"output": "", "error": "缺少 message 参数"}

        try:
            channel_ids = None
            if channel:
                # 如果指定了渠道名，通过数据库查找对应 channel_id
                from database import get_db

                db = await get_db()
                row = await (
                    await db.execute(
                        "SELECT id FROM notification_channels WHERE channel_type = ? AND enabled = 1 LIMIT 1",
                        (channel,),
                    )
                ).fetchone()
                if row:
                    channel_ids = [row[0]]

            results = await send_notification(message, channel_ids)
            success_count = sum(1 for r in results if r.get("success"))
            return {
                "output": f"通知已发送到 {success_count}/{len(results)} 个渠道",
                "results": results,
            }
        except Exception as e:
            logger.exception("Notify step 执行失败")
            return {"output": "", "error": str(e)}

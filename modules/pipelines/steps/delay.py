"""Delay Step 执行器 — asyncio.sleep 延时等待"""

import asyncio
import logging

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)

# 最大延时 1 小时，防止误配置
MAX_DELAY_SECONDS = 3600


@register_step("delay")
class DelayStepExecutor:
    """延时等待指定秒数"""

    async def execute(self, config: dict, state: dict) -> dict:
        seconds = config.get("seconds", config.get("duration", 0))
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            return {"output": "", "error": f"无效的延时值: {seconds}"}

        if seconds <= 0:
            return {"output": "跳过延时（秒数 <= 0）"}

        if seconds > MAX_DELAY_SECONDS:
            logger.warning("延时 %ds 超过上限 %ds，截断为上限", seconds, MAX_DELAY_SECONDS)
            seconds = MAX_DELAY_SECONDS

        logger.info("Delay step 等待 %d 秒", seconds)
        await asyncio.sleep(seconds)
        return {"output": f"已等待 {seconds} 秒"}

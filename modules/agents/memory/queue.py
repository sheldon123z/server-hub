"""防抖记忆更新队列 — 对话结束后异步更新记忆，避免频繁 LLM 调用"""

import asyncio
import logging
from collections import OrderedDict

logger = logging.getLogger(__name__)


class MemoryUpdateQueue:
    """防抖队列: 对话结束后入队，debounce_seconds 内只处理最新的"""

    def __init__(self, debounce_seconds: float = 30.0):
        self._debounce = debounce_seconds
        self._pending: OrderedDict[str, dict] = OrderedDict()
        self._timer_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def enqueue(self, conversation_id: str, storage, messages: list) -> None:
        """入队一次记忆更新请求"""
        async with self._lock:
            self._pending[conversation_id] = {
                "storage": storage,
                "messages": messages,
                "conversation_id": conversation_id,
            }
            # Per-conversation deduplication: newer replaces older
            self._pending.move_to_end(conversation_id)

        # Reset debounce timer
        if self._timer_task and not self._timer_task.done():
            self._timer_task.cancel()
        self._timer_task = asyncio.create_task(self._debounce_flush())

    async def _debounce_flush(self) -> None:
        """等待防抖时间后批量处理"""
        try:
            await asyncio.sleep(self._debounce)
            await self._flush()
        except asyncio.CancelledError:
            pass  # Timer reset, will be restarted
        except Exception as e:
            logger.error("记忆更新队列异常: %s", e)

    async def _flush(self) -> None:
        """处理所有待更新的对话"""
        async with self._lock:
            items = list(self._pending.values())
            self._pending.clear()

        if not items:
            return

        from modules.agents.memory.updater import update_memory

        for item in items:
            try:
                await update_memory(
                    storage=item["storage"],
                    conversation_messages=item["messages"],
                    conversation_id=item["conversation_id"],
                )
            except Exception as e:
                logger.warning(
                    "记忆更新失败 conv=%s: %s",
                    item["conversation_id"],
                    e,
                )


# Global singleton
_queue: MemoryUpdateQueue | None = None


def get_memory_queue() -> MemoryUpdateQueue:
    global _queue
    if _queue is None:
        _queue = MemoryUpdateQueue(debounce_seconds=30.0)
    return _queue

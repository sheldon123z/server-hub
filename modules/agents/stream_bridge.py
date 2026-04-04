"""StreamBridge — Agent 执行与 SSE 消费解耦

将 agent.astream() 的事件发布到内存队列，SSE endpoint 从队列消费。
客户端断连时 agent 继续执行，重连后可从队列恢复未消费事件。

参考 DeerFlow MemoryStreamBridge:
- 每个 run_id 一个 asyncio.Queue
- publish 超时时丢弃旧事件（END sentinel 永不丢弃）
- subscribe 超时时发送 heartbeat
- cleanup 延迟后清理队列
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# 哨兵对象
END_SENTINEL = object()
HEARTBEAT_SENTINEL = object()


@dataclass
class StreamEvent:
    """队列中的事件条目"""

    event: str
    data: str  # 已 JSON 序列化的 payload
    timestamp: float = field(default_factory=time.time)


class StreamBridge:
    """内存队列 StreamBridge — per-run 事件发布/订阅

    Args:
        max_queue_size: 每个 run 的最大队列容量
        heartbeat_interval: subscribe 无事件时的心跳间隔 (秒)
        cleanup_delay: publish_end 后延迟清理队列 (秒)
    """

    def __init__(
        self,
        max_queue_size: int = 256,
        heartbeat_interval: float = 15.0,
        cleanup_delay: float = 60.0,
    ):
        self._max_size = max_queue_size
        self._heartbeat_interval = heartbeat_interval
        self._cleanup_delay = cleanup_delay
        self._queues: dict[str, asyncio.Queue] = {}
        self._cleanup_tasks: dict[str, asyncio.Task] = {}

    def _get_or_create_queue(self, run_id: str) -> asyncio.Queue:
        """获取或创建 run 的事件队列"""
        if run_id not in self._queues:
            self._queues[run_id] = asyncio.Queue(maxsize=self._max_size)
        return self._queues[run_id]

    async def publish(self, run_id: str, event: str, data: str) -> None:
        """发布事件到队列

        队列满时丢弃最旧的非 END 事件腾出空间。
        """
        queue = self._get_or_create_queue(run_id)
        entry = StreamEvent(event=event, data=data)

        try:
            queue.put_nowait(entry)
        except asyncio.QueueFull:
            # 队列满 — 丢弃最旧事件腾出空间
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            try:
                queue.put_nowait(entry)
            except asyncio.QueueFull:
                logger.warning("StreamBridge: 队列已满且无法腾出空间, run=%s event=%s", run_id, event)

    async def publish_end(self, run_id: str) -> None:
        """发布结束哨兵 — END sentinel 永不丢弃"""
        queue = self._get_or_create_queue(run_id)

        # 确保 END 能入队：满时驱逐旧事件
        while queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        try:
            queue.put_nowait(END_SENTINEL)
        except asyncio.QueueFull:
            logger.error("StreamBridge: 无法发布 END sentinel, run=%s", run_id)

        # 延迟清理（给重连窗口）
        self._schedule_cleanup(run_id)

    async def subscribe(self, run_id: str) -> AsyncIterator[StreamEvent | object]:
        """订阅 run 的事件流

        Yields:
            StreamEvent — 正常事件
            HEARTBEAT_SENTINEL — 心跳（无事件超过 heartbeat_interval 时）
            END_SENTINEL — 流结束

        收到 END_SENTINEL 后调用方应停止迭代。
        """
        queue = self._get_or_create_queue(run_id)

        while True:
            try:
                entry = await asyncio.wait_for(queue.get(), timeout=self._heartbeat_interval)
            except TimeoutError:
                yield HEARTBEAT_SENTINEL
                continue

            if entry is END_SENTINEL:
                yield END_SENTINEL
                return

            yield entry

    def _schedule_cleanup(self, run_id: str) -> None:
        """延迟清理队列，给客户端重连窗口"""
        # 取消之前的清理任务（如果有）
        old_task = self._cleanup_tasks.pop(run_id, None)
        if old_task and not old_task.done():
            old_task.cancel()

        async def _delayed_cleanup():
            await asyncio.sleep(self._cleanup_delay)
            self._queues.pop(run_id, None)
            self._cleanup_tasks.pop(run_id, None)
            logger.debug("StreamBridge: 已清理 run=%s 的队列", run_id)

        self._cleanup_tasks[run_id] = asyncio.create_task(_delayed_cleanup())

    def has_queue(self, run_id: str) -> bool:
        """检查 run 是否有活跃队列（用于重连判断）"""
        return run_id in self._queues

    @property
    def active_runs(self) -> int:
        return len(self._queues)


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_bridge: StreamBridge | None = None


def get_stream_bridge() -> StreamBridge:
    """获取全局 StreamBridge 单例"""
    global _bridge
    if _bridge is None:
        _bridge = StreamBridge(
            max_queue_size=256,
            heartbeat_interval=15.0,
            cleanup_delay=60.0,
        )
    return _bridge

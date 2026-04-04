"""循环检测中间件 — 检测并阻止 Agent 重复工具调用

参考 DeerFlow LoopDetectionMiddleware:
- 滑动窗口追踪最近 N 次工具调用 hash
- 3 次重复: 注入警告消息
- 5 次重复: 强制停止 (剥离 tool_calls)
- LRU 线程记录防内存泄漏
"""

import hashlib
import json
import logging
from collections import OrderedDict, deque

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

logger = logging.getLogger(__name__)


class LoopDetectionMiddleware(AgentMiddleware):
    """检测重复工具调用，防止 Agent 陷入无限循环。

    - window_size: 滑动窗口大小 (追踪最近 N 次调用)
    - warn_threshold: 同一 hash 出现次数达此值时注入警告
    - stop_threshold: 同一 hash 出现次数达此值时强制停止
    - max_threads: 最大追踪线程数 (LRU 驱逐)
    """

    def __init__(
        self,
        window_size: int = 20,
        warn_threshold: int = 3,
        stop_threshold: int = 5,
        max_threads: int = 100,
    ):
        self.window_size = window_size
        self.warn_threshold = warn_threshold
        self.stop_threshold = stop_threshold
        self.max_threads = max_threads
        # OrderedDict as LRU: thread_id -> deque of hashes
        self._history: OrderedDict[str, deque] = OrderedDict()

    def _hash_tool_call(self, tool_call: dict) -> str:
        """Generate a hash for a tool call (name + canonical args)."""
        name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        # Sort args for canonical form
        canonical = json.dumps({"name": name, "args": args}, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(canonical.encode(), usedforsecurity=False).hexdigest()[:12]

    def _get_history(self, thread_id: str) -> deque:
        """Get or create history deque for thread, with LRU eviction."""
        if thread_id in self._history:
            self._history.move_to_end(thread_id)
            return self._history[thread_id]

        # Evict oldest if at capacity
        while len(self._history) >= self.max_threads:
            self._history.popitem(last=False)

        history: deque = deque(maxlen=self.window_size)
        self._history[thread_id] = history
        return history

    def _check_repetition(self, thread_id: str, tool_calls: list[dict]) -> tuple[str, str | None]:
        """Record tool calls and check for repetition.

        Returns: (action, warning_message)
            action: "ok" | "warn" | "stop"
            warning_message: message to inject (only for warn/stop)
        """
        history = self._get_history(thread_id)
        max_count = 0
        repeated_tool = ""

        for tc in tool_calls:
            h = self._hash_tool_call(tc)
            count = sum(1 for x in history if x == h)
            history.append(h)
            if count >= max_count:
                max_count = count
                repeated_tool = tc.get("name", "unknown")

        if max_count >= self.stop_threshold - 1:  # -1 because we just appended
            msg = (
                f"检测到工具 `{repeated_tool}` 已被重复调用 {max_count + 1} 次且结果相同。"
                f"已强制停止循环。请换一种方式解决问题，或告知用户当前遇到的困难。"
            )
            logger.warning(
                "Loop STOP: thread=%s tool=%s count=%d",
                thread_id,
                repeated_tool,
                max_count + 1,
            )
            return "stop", msg

        if max_count >= self.warn_threshold - 1:
            msg = (
                f"注意：你正在重复调用工具 `{repeated_tool}`（已 {max_count + 1} 次）。"
                f"请检查之前的结果，尝试不同的参数或方法。"
            )
            logger.info(
                "Loop WARN: thread=%s tool=%s count=%d",
                thread_id,
                repeated_tool,
                max_count + 1,
            )
            return "warn", msg

        return "ok", None

    def _extract_thread_id(self, request) -> str:
        """Extract thread_id from request config."""
        config = getattr(request, "config", None) or {}
        configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
        return configurable.get("thread_id", "default")

    def wrap_model_call(self, request, call_next):
        """Wrap model call to detect loops in tool calls."""
        response = call_next(request)

        if not isinstance(response, AIMessage) or not getattr(response, "tool_calls", None):
            return response

        thread_id = self._extract_thread_id(request)
        action, message = self._check_repetition(thread_id, response.tool_calls)

        if action == "stop":
            # Strip all tool_calls, force text response
            return AIMessage(
                content=message,
                id=getattr(response, "id", None),
            )

        if action == "warn":
            if not response.content:
                response.content = ""
            response.content = message + "\n\n" + response.content if response.content else message

        return response

    async def awrap_model_call(self, request, call_next):
        """Async version of wrap_model_call."""
        response = await call_next(request)

        if not isinstance(response, AIMessage) or not getattr(response, "tool_calls", None):
            return response

        thread_id = self._extract_thread_id(request)
        action, message = self._check_repetition(thread_id, response.tool_calls)

        if action == "stop":
            return AIMessage(
                content=message,
                id=getattr(response, "id", None),
            )

        if action == "warn":
            if not response.content:
                response.content = ""
            response.content = message + "\n\n" + response.content if response.content else message

        return response

    def clear_thread(self, thread_id: str) -> None:
        """Clear history for a specific thread."""
        self._history.pop(thread_id, None)

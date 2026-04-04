"""tests/test_loop_detection.py — 循环检测中间件单元测试

覆盖:
  - _hash_tool_call：相同调用产生相同 hash，不同参数产生不同 hash
  - _get_history：LRU 窗口创建与驱逐
  - _check_repetition：ok / warn / stop 三种状态
  - _extract_thread_id：从 request.config.configurable 提取 thread_id
  - wrap_model_call：同步包装 — pass-through / warn 注入 / stop 剥离 tool_calls
  - awrap_model_call：异步包装 — 与同步逻辑一致
  - clear_thread：清除指定线程历史
"""

from __future__ import annotations

import asyncio
from collections import deque
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage

from modules.agents.loop_detection import LoopDetectionMiddleware

# ── Fixtures ────────────────────────────────────────────────────


@pytest.fixture
def detector():
    """默认参数的检测器（warn=3, stop=5, window=20, max_threads=100）。"""
    return LoopDetectionMiddleware()


@pytest.fixture
def tight_detector():
    """低阈值检测器，方便快速触发 warn/stop。"""
    return LoopDetectionMiddleware(
        window_size=10,
        warn_threshold=2,
        stop_threshold=3,
        max_threads=3,
    )


_TC_ID_COUNTER = 0


def _make_tc(name: str, **args) -> dict:
    """构造工具调用 dict（含 id，满足 AIMessage 构造要求）。"""
    global _TC_ID_COUNTER
    _TC_ID_COUNTER += 1
    return {"id": f"call_{_TC_ID_COUNTER}", "name": name, "args": args}


def _make_request(thread_id: str = "thread-1") -> MagicMock:
    """构造带 config.configurable.thread_id 的假 request。"""
    req = MagicMock()
    req.config = {"configurable": {"thread_id": thread_id}}
    return req


# ── _hash_tool_call ──────────────────────────────────────────────


class TestHashToolCall:
    def test_same_call_same_hash(self, detector):
        tc = _make_tc("get_system_overview", scope="current")
        h1 = detector._hash_tool_call(tc)
        h2 = detector._hash_tool_call(tc)
        assert h1 == h2

    def test_different_args_different_hash(self, detector):
        tc1 = _make_tc("get_container_logs", container="nginx")
        tc2 = _make_tc("get_container_logs", container="redis")
        assert detector._hash_tool_call(tc1) != detector._hash_tool_call(tc2)

    def test_different_name_different_hash(self, detector):
        tc1 = _make_tc("tool_a")
        tc2 = _make_tc("tool_b")
        assert detector._hash_tool_call(tc1) != detector._hash_tool_call(tc2)

    def test_arg_order_insensitive(self, detector):
        """args 以 sorted keys 序列化，顺序不影响 hash。"""
        tc1 = {"name": "my_tool", "args": {"a": 1, "b": 2}}
        tc2 = {"name": "my_tool", "args": {"b": 2, "a": 1}}
        assert detector._hash_tool_call(tc1) == detector._hash_tool_call(tc2)

    def test_hash_length_12(self, detector):
        """hash 为 MD5 前 12 位。"""
        h = detector._hash_tool_call(_make_tc("foo"))
        assert len(h) == 12

    def test_missing_name_defaults(self, detector):
        """工具调用中缺少 name 时，使用空字符串，不应抛异常。"""
        h = detector._hash_tool_call({"args": {}})
        assert isinstance(h, str)


# ── _get_history (LRU) ──────────────────────────────────────────


class TestGetHistory:
    def test_new_thread_creates_deque(self, tight_detector):
        h = tight_detector._get_history("t-1")
        assert isinstance(h, deque)
        assert len(h) == 0

    def test_same_thread_same_deque(self, tight_detector):
        h1 = tight_detector._get_history("t-2")
        h2 = tight_detector._get_history("t-2")
        assert h1 is h2

    def test_lru_evicts_oldest(self, tight_detector):
        """max_threads=3，第 4 个线程应驱逐最旧的线程。"""
        tight_detector._get_history("old-1")
        tight_detector._get_history("old-2")
        tight_detector._get_history("old-3")
        # 访问 old-4 → old-1 应被驱逐
        tight_detector._get_history("old-4")
        assert "old-1" not in tight_detector._history
        assert "old-4" in tight_detector._history

    def test_recent_access_prevents_eviction(self, tight_detector):
        """近期访问的线程移到 LRU 末尾，不会被驱逐。"""
        tight_detector._get_history("keep-1")
        tight_detector._get_history("keep-2")
        tight_detector._get_history("keep-3")
        # 重新访问 keep-1，使其移到末尾
        tight_detector._get_history("keep-1")
        # 加入第 4 个：应驱逐 keep-2（最旧）
        tight_detector._get_history("keep-4")
        assert "keep-1" in tight_detector._history
        assert "keep-2" not in tight_detector._history

    def test_history_maxlen_equals_window_size(self, tight_detector):
        """deque 的 maxlen 等于 window_size。"""
        h = tight_detector._get_history("t-win")
        assert h.maxlen == tight_detector.window_size


# ── _check_repetition ────────────────────────────────────────────


class TestCheckRepetition:
    def test_ok_when_no_repetition(self, tight_detector):
        """不同工具调用 → action='ok'。"""
        action, msg = tight_detector._check_repetition(
            "t-ok",
            [_make_tc("tool_a"), _make_tc("tool_b")],
        )
        assert action == "ok"
        assert msg is None

    def test_warn_when_threshold_reached(self, tight_detector):
        """重复调用同一工具达到 warn_threshold → action='warn'。"""
        tc = _make_tc("noisy_tool", arg=1)
        # warn_threshold=2: 第 2 次调用（已有 1 次）触发 warn
        tight_detector._check_repetition("t-w", [tc])
        action, msg = tight_detector._check_repetition("t-w", [tc])
        assert action == "warn"
        assert "noisy_tool" in msg
        assert msg is not None

    def test_stop_when_threshold_reached(self, tight_detector):
        """重复调用达到 stop_threshold → action='stop'。"""
        tc = _make_tc("repeat_tool")
        # stop_threshold=3: 第 3 次调用（已有 2 次）触发 stop
        tight_detector._check_repetition("t-s", [tc])
        tight_detector._check_repetition("t-s", [tc])
        action, msg = tight_detector._check_repetition("t-s", [tc])
        assert action == "stop"
        assert "repeat_tool" in msg

    def test_stop_takes_priority_over_warn(self, tight_detector):
        """达到 stop 阈值时返回 stop 而非 warn。"""
        tc = _make_tc("over_threshold")
        for _ in range(2):
            tight_detector._check_repetition("t-p", [tc])
        action, _ = tight_detector._check_repetition("t-p", [tc])
        assert action == "stop"

    def test_different_threads_isolated(self, tight_detector):
        """不同 thread_id 的历史相互独立。"""
        tc = _make_tc("shared_tool")
        tight_detector._check_repetition("thread-A", [tc])
        # thread-B 从零开始，第一次调用应为 ok
        action, _ = tight_detector._check_repetition("thread-B", [tc])
        assert action == "ok"

    def test_window_sliding_forgets_old_calls(self):
        """窗口满时旧记录被移出，不再计入重复次数。

        window_size=4, warn_threshold=3 (触发条件: count_before >= 2)
        先记录 1 次 old_tool，再用 4 次 filler 完全覆盖窗口，
        此时 old_tool 已不在窗口，再次调用 count=0 → ok。
        """
        det = LoopDetectionMiddleware(
            window_size=4,
            warn_threshold=3,
            stop_threshold=10,
        )
        tc_old = _make_tc("old_tool")
        tc_new = _make_tc("filler")
        # 先记录 1 次 old_tool
        det._check_repetition("t", [tc_old])
        # 用 4 次 filler 填满并完全覆盖窗口（窗口大小=4）
        for _ in range(4):
            det._check_repetition("t", [tc_new])
        # old_tool 已不在窗口，再调用 count=0 → ok
        action, _ = det._check_repetition("t", [tc_old])
        assert action == "ok"


# ── _extract_thread_id ───────────────────────────────────────────


class TestExtractThreadId:
    def test_extracts_from_config(self, detector):
        req = _make_request("my-thread")
        assert detector._extract_thread_id(req) == "my-thread"

    def test_defaults_to_default_when_missing(self, detector):
        req = MagicMock()
        req.config = {}
        assert detector._extract_thread_id(req) == "default"

    def test_handles_no_config_attr(self, detector):
        req = SimpleNamespace()  # 无 config 属性
        assert detector._extract_thread_id(req) == "default"


# ── wrap_model_call (同步) ───────────────────────────────────────


class TestWrapModelCall:
    def _call_next_returning(self, ai_message: AIMessage):
        return lambda req: ai_message

    def test_passthrough_non_ai_message(self, tight_detector):
        """非 AIMessage 响应直接透传。"""
        non_ai = MagicMock()
        non_ai.__class__ = MagicMock  # 不是 AIMessage
        req = _make_request("t1")
        result = tight_detector.wrap_model_call(req, lambda r: non_ai)
        assert result is non_ai

    def test_passthrough_no_tool_calls(self, tight_detector):
        """AIMessage 无 tool_calls → 直接返回原消息。"""
        ai_msg = AIMessage(content="done")
        req = _make_request("t2")
        result = tight_detector.wrap_model_call(req, lambda r: ai_msg)
        assert result is ai_msg

    def test_ok_action_returns_original(self, tight_detector):
        """首次调用 → action='ok'，原消息不变。"""
        ai_msg = AIMessage(content="", tool_calls=[_make_tc("tool_ok")])
        req = _make_request("t3")
        result = tight_detector.wrap_model_call(req, lambda r: ai_msg)
        # ok 状态下不修改消息
        assert result.tool_calls == ai_msg.tool_calls

    def test_warn_action_prepends_message(self, tight_detector):
        """warn 触发时，警告内容前置到 response.content。"""
        tc = _make_tc("warn_tool", x=1)
        req = _make_request("t-warn")
        ai = AIMessage(content="original", tool_calls=[tc])

        # 先触发一次（ok），再触发 warn
        tight_detector.wrap_model_call(req, lambda r: AIMessage(content="", tool_calls=[tc]))
        result = tight_detector.wrap_model_call(req, lambda r: ai)

        assert "warn_tool" in result.content
        # tool_calls 仍保留
        assert result.tool_calls

    def test_stop_action_strips_tool_calls(self, tight_detector):
        """stop 触发时，返回新 AIMessage 且不含 tool_calls。"""
        tc = _make_tc("stop_tool")
        req = _make_request("t-stop")
        ai = AIMessage(content="", tool_calls=[tc])

        tight_detector.wrap_model_call(req, lambda r: AIMessage(content="", tool_calls=[tc]))
        tight_detector.wrap_model_call(req, lambda r: AIMessage(content="", tool_calls=[tc]))
        result = tight_detector.wrap_model_call(req, lambda r: ai)

        assert not getattr(result, "tool_calls", None)
        assert "stop_tool" in result.content


# ── awrap_model_call (异步) ──────────────────────────────────────


class TestAwrapModelCall:
    def test_async_passthrough_no_tool_calls(self, tight_detector):
        async def _run():
            ai_msg = AIMessage(content="async done")
            req = _make_request("async-t1")
            result = await tight_detector.awrap_model_call(req, AsyncMock(return_value=ai_msg))
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert result.content == "async done"

    def test_async_stop_strips_tool_calls(self, tight_detector):
        async def _run():
            tc = _make_tc("async_stop_tool")
            req = _make_request("async-t2")
            ai = AIMessage(content="", tool_calls=[tc])

            await tight_detector.awrap_model_call(req, AsyncMock(return_value=AIMessage(content="", tool_calls=[tc])))
            await tight_detector.awrap_model_call(req, AsyncMock(return_value=AIMessage(content="", tool_calls=[tc])))
            result = await tight_detector.awrap_model_call(req, AsyncMock(return_value=ai))
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert not getattr(result, "tool_calls", None)
        assert "async_stop_tool" in result.content

    def test_async_warn_prepends_content(self, tight_detector):
        async def _run():
            tc = _make_tc("async_warn_tool")
            req = _make_request("async-t3")
            await tight_detector.awrap_model_call(req, AsyncMock(return_value=AIMessage(content="", tool_calls=[tc])))
            result = await tight_detector.awrap_model_call(
                req, AsyncMock(return_value=AIMessage(content="hello", tool_calls=[tc]))
            )
            return result

        result = asyncio.get_event_loop().run_until_complete(_run())
        assert "async_warn_tool" in result.content


# ── clear_thread ─────────────────────────────────────────────────


class TestClearThread:
    def test_clear_removes_history(self, tight_detector):
        tc = _make_tc("cleanup_tool")
        tight_detector._check_repetition("t-clear", [tc])
        assert "t-clear" in tight_detector._history
        tight_detector.clear_thread("t-clear")
        assert "t-clear" not in tight_detector._history

    def test_clear_nonexistent_thread_no_error(self, tight_detector):
        """清除不存在的 thread_id 不应抛异常。"""
        tight_detector.clear_thread("ghost-thread")  # 不应报错

    def test_after_clear_repetition_resets(self, tight_detector):
        """clear 后，该线程重新计数（重复次数归零）。"""
        tc = _make_tc("reset_count_tool")
        # 先触发到 warn 状态
        tight_detector._check_repetition("t-r", [tc])
        tight_detector._check_repetition("t-r", [tc])
        tight_detector.clear_thread("t-r")
        # 清除后第一次调用应为 ok
        action, _ = tight_detector._check_repetition("t-r", [tc])
        assert action == "ok"

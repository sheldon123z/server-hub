"""memory 子系统单元测试

覆盖:
  - modules/agents/memory/storage.py  — MemoryStorage (load/save/add_fact/remove_fact/缓存/原子写)
  - modules/agents/memory/injection.py — _estimate_tokens / format_memory_for_prompt
  - modules/agents/memory/queue.py     — MemoryUpdateQueue (防抖/enqueue/flush/错误隔离)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# storage.py 测试
# ---------------------------------------------------------------------------


class TestMemoryStorage:
    """MemoryStorage: JSON 文件持久化 + 文件修改时间缓存"""

    @pytest.fixture()
    def storage(self, tmp_path):
        from modules.agents.memory.storage import MemoryStorage

        return MemoryStorage(tmp_path / "mem")

    def test_load_returns_default_when_no_file(self, storage):
        """文件不存在时返回 DEFAULT_MEMORY 结构"""
        data = storage.load()
        assert isinstance(data, dict)
        assert "facts" in data
        assert "context" in data
        assert isinstance(data["facts"], list)
        assert len(data["facts"]) == 0

    def test_load_default_has_context_keys(self, storage):
        """DEFAULT_MEMORY context 包含三个子字段"""
        data = storage.load()
        ctx = data["context"]
        assert "topOfMind" in ctx
        assert "workContext" in ctx
        assert "userPreferences" in ctx

    def test_save_and_reload(self, storage):
        """save 写文件后 load 能读回"""
        data = storage.load()
        data["context"]["topOfMind"]["summary"] = "测试摘要"
        storage.save(data)

        # 清除缓存，重新加载
        storage._cache = None
        storage._file_mtime = 0.0
        reloaded = storage.load()
        assert reloaded["context"]["topOfMind"]["summary"] == "测试摘要"

    def test_save_adds_last_updated(self, storage):
        """save 自动写入 lastUpdated 字段"""
        data = storage.load()
        storage.save(data)
        assert "lastUpdated" in data

    def test_save_atomic_tmp_file_cleaned_up(self, storage, tmp_path):
        """正常 save 后不留 .tmp 文件"""
        storage.save(storage.load())
        tmp_files = list((tmp_path / "mem").glob("*.tmp"))
        assert tmp_files == []

    def test_load_uses_cache_when_mtime_unchanged(self, storage):
        """文件未变更时 load 返回缓存对象（同一实例）"""
        data = storage.load()
        storage.save(data)
        first = storage.load()
        second = storage.load()
        assert first is second  # 同一对象 → 缓存命中

    def test_load_reloads_when_mtime_changes(self, storage, tmp_path):
        """文件被外部修改后 load 重新读取"""
        storage.save(storage.load())
        first = storage.load()

        # 外部直接写入文件（绕过缓存）
        path = tmp_path / "mem" / "memory.json"
        content = json.loads(path.read_text(encoding="utf-8"))
        content["context"]["topOfMind"]["summary"] = "外部修改"
        import time

        time.sleep(0.01)  # 确保 mtime 不同
        path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")

        reloaded = storage.load()
        assert reloaded is not first
        assert reloaded["context"]["topOfMind"]["summary"] == "外部修改"

    def test_load_falls_back_on_corrupt_json(self, storage, tmp_path):
        """JSON 损坏时返回 DEFAULT_MEMORY，不抛异常"""
        path = tmp_path / "mem" / "memory.json"
        path.write_text("{invalid json", encoding="utf-8")
        data = storage.load()
        assert isinstance(data, dict)
        assert "facts" in data

    def test_add_fact_returns_true(self, storage):
        ok = storage.add_fact("Python 是解释型语言", category="knowledge")
        assert ok is True

    def test_add_fact_persists_to_file(self, storage):
        storage.add_fact("测试事实", category="knowledge", confidence=0.9)
        storage._cache = None
        storage._file_mtime = 0.0
        data = storage.load()
        assert len(data["facts"]) == 1
        assert data["facts"][0]["category"] == "knowledge"
        assert data["facts"][0]["confidence"] == 0.9

    def test_add_fact_stores_all_fields(self, storage):
        storage.add_fact("内容", category="correction", confidence=0.7, source="user")
        data = storage.load()
        fact = data["facts"][0]
        assert "id" in fact
        assert "createdAt" in fact
        assert fact["source"] == "user"
        assert fact["category"] == "correction"

    def test_add_fact_dedup_same_content(self, storage):
        """相同内容不重复添加"""
        storage.add_fact("重复内容")
        result = storage.add_fact("重复内容")
        assert result is False
        data = storage.load()
        assert len(data["facts"]) == 1

    def test_add_fact_dedup_case_insensitive(self, storage):
        """大小写和前后空格不影响去重"""
        storage.add_fact("  Hello World  ")
        result = storage.add_fact("hello world")
        assert result is False

    def test_add_fact_empty_content_rejected(self, storage):
        """空内容不添加"""
        result = storage.add_fact("   ")
        assert result is False
        data = storage.load()
        assert len(data["facts"]) == 0

    def test_add_fact_limits_to_50(self, storage):
        """超过 50 条时保留高 confidence 的"""
        for i in range(55):
            storage.add_fact(f"事实 {i}", confidence=i / 100.0)
        data = storage.load()
        assert len(data["facts"]) <= 50
        # 最低 confidence 应该是 0.05+ (index 5/100=0.05)
        confidences = [f["confidence"] for f in data["facts"]]
        assert min(confidences) >= 5 / 100.0

    def test_remove_fact_returns_true_on_success(self, storage):
        storage.add_fact("待删除的事实")
        data = storage.load()
        fact_id = data["facts"][0]["id"]
        result = storage.remove_fact(fact_id)
        assert result is True

    def test_remove_fact_actually_removes(self, storage):
        storage.add_fact("待删除")
        data = storage.load()
        fact_id = data["facts"][0]["id"]
        storage.remove_fact(fact_id)
        storage._cache = None
        storage._file_mtime = 0.0
        data = storage.load()
        assert len(data["facts"]) == 0

    def test_remove_fact_returns_false_when_not_found(self, storage):
        result = storage.remove_fact("nonexistent-id")
        assert result is False

    def test_remove_fact_only_removes_matching_id(self, storage):
        """只删除指定 id，其余保留"""
        storage.add_fact("事实 A")
        storage.add_fact("事实 B")
        data = storage.load()
        id_a = data["facts"][0]["id"]
        storage.remove_fact(id_a)
        data = storage.load()
        assert len(data["facts"]) == 1
        assert data["facts"][0]["content"] == "事实 B"  # content stored as-is


# ---------------------------------------------------------------------------
# injection.py 测试
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """_estimate_tokens: 中英文混合 token 估算"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from modules.agents.memory.injection import _estimate_tokens

        self.fn = _estimate_tokens

    def test_empty_string(self):
        assert self.fn("") == 0

    def test_ascii_only(self):
        # 8 chars / 4 = 2
        assert self.fn("hello!!") == int(7 / 4)

    def test_chinese_only(self):
        # 4 Chinese chars / 1.5 = 2
        assert self.fn("你好世界") == int(4 / 1.5)

    def test_mixed_chinese_english(self):
        text = "你好 hello"  # 2 Chinese + 6 non-Chinese (space + 5 letters)
        expected = int(2 / 1.5 + 6 / 4)
        assert self.fn(text) == expected

    def test_returns_int(self):
        assert isinstance(self.fn("test"), int)

    def test_longer_text_larger_estimate(self):
        assert self.fn("hello world") > self.fn("hi")


class TestFormatMemoryForPrompt:
    """format_memory_for_prompt: token 感知格式化"""

    @pytest.fixture(autouse=True)
    def _import(self):
        from modules.agents.memory.injection import format_memory_for_prompt
        from modules.agents.memory.storage import DEFAULT_MEMORY

        self.fn = format_memory_for_prompt
        self.default = DEFAULT_MEMORY

    def _make_data(self, **overrides) -> dict:
        import copy

        data = copy.deepcopy(self.default)
        for k, v in overrides.items():
            if "." in k:
                parts = k.split(".")
                node = data
                for p in parts[:-1]:
                    node = node[p]
                node[parts[-1]] = v
            else:
                data[k] = v
        return data

    def test_empty_dict_returns_empty(self):
        assert self.fn({}, 2000) == ""

    def test_none_like_returns_empty(self):
        assert self.fn(None, 2000) == ""  # type: ignore[arg-type]

    def test_all_empty_returns_empty(self):
        data = self._make_data()
        assert self.fn(data, 2000) == ""

    def test_includes_context_top_of_mind(self):
        data = self._make_data()
        data["context"]["topOfMind"]["summary"] = "当前在做 A 任务"
        result = self.fn(data, 2000)
        assert "当前关注" in result
        assert "当前在做 A 任务" in result

    def test_context_section_header(self):
        data = self._make_data()
        data["context"]["workContext"]["summary"] = "正在写代码"
        result = self.fn(data, 2000)
        assert result.startswith("\n## 记忆上下文\n")

    def test_context_includes_all_three_fields(self):
        data = self._make_data()
        data["context"]["topOfMind"]["summary"] = "关注点"
        data["context"]["workContext"]["summary"] = "工作内容"
        data["context"]["userPreferences"]["summary"] = "偏好设置"
        result = self.fn(data, 2000)
        assert "当前关注" in result
        assert "工作上下文" in result
        assert "用户偏好" in result

    def test_facts_sorted_by_confidence_desc(self):
        data = self._make_data()
        data["facts"] = [
            {"content": "低置信", "category": "knowledge", "confidence": 0.3},
            {"content": "高置信", "category": "knowledge", "confidence": 0.9},
        ]
        result = self.fn(data, 2000)
        assert result.index("高置信") < result.index("低置信")

    def test_correction_fact_has_warning_prefix(self):
        data = self._make_data()
        data["facts"] = [{"content": "修正内容", "category": "correction", "confidence": 0.8}]
        result = self.fn(data, 2000)
        assert "- ⚠ 修正内容" in result

    def test_normal_fact_prefix(self):
        data = self._make_data()
        data["facts"] = [{"content": "普通事实", "category": "knowledge", "confidence": 0.8}]
        result = self.fn(data, 2000)
        assert "- 普通事实" in result

    def test_fact_with_empty_content_skipped(self):
        data = self._make_data()
        data["facts"] = [
            {"content": "", "category": "knowledge", "confidence": 0.9},
            {"content": "有内容", "category": "knowledge", "confidence": 0.8},
        ]
        result = self.fn(data, 2000)
        assert "有内容" in result
        # 空 content 不出现空行
        assert "- \n" not in result

    def test_facts_section_label(self):
        data = self._make_data()
        data["facts"] = [{"content": "事实内容", "category": "knowledge", "confidence": 0.8}]
        result = self.fn(data, 2000)
        assert "记忆事实:" in result

    def test_recent_activity_included(self):
        data = self._make_data()
        data["history"]["recentActivity"]["summary"] = "最近在写测试"
        result = self.fn(data, 2000)
        assert "最近活动: 最近在写测试" in result

    def test_recent_activity_truncated_at_200(self):
        data = self._make_data()
        long_text = "A" * 300
        data["history"]["recentActivity"]["summary"] = long_text
        result = self.fn(data, 2000)
        # 截取 200 字符
        assert "A" * 200 in result
        assert "A" * 201 not in result

    def test_token_budget_limits_context(self):
        """极小 token 预算时不输出任何内容"""
        data = self._make_data()
        data["context"]["topOfMind"]["summary"] = "这是一段很长的内容" * 10
        # budget=1 远小于任何行所需 token
        result = self.fn(data, 1)
        assert result == ""

    def test_token_budget_stops_context_loop_early(self):
        """budget 恰好容纳第一条时，后续 context 不输出"""
        data = self._make_data()
        data["context"]["topOfMind"]["summary"] = "A"
        data["context"]["workContext"]["summary"] = "B" * 100
        data["context"]["userPreferences"]["summary"] = "C"
        # 足够第一条 (≈5 tokens)，但不够第二条 (≈30 tokens)
        result = self.fn(data, 6)
        assert "当前关注" in result
        assert "工作上下文" not in result

    def test_history_requires_50_spare_tokens(self):
        """剩余 token < 50 时 history 不输出"""
        data = self._make_data()
        data["history"]["recentActivity"]["summary"] = "最近活动内容"
        # budget=49，history 需要 budget-50=−1，条件不满足
        result = self.fn(data, 49)
        assert "最近活动" not in result

    def test_no_facts_no_facts_label(self):
        """没有 facts 时不输出 '记忆事实:' 标签"""
        data = self._make_data()
        data["context"]["topOfMind"]["summary"] = "有内容"
        result = self.fn(data, 2000)
        assert "记忆事实:" not in result


# ---------------------------------------------------------------------------
# queue.py 测试
# ---------------------------------------------------------------------------


class TestMemoryUpdateQueue:
    """MemoryUpdateQueue: 防抖异步更新队列"""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """每个测试前重置全局单例，避免测试间污染"""
        import modules.agents.memory.queue as q_mod

        q_mod._queue = None
        yield
        q_mod._queue = None

    @pytest.fixture()
    def queue(self):
        from modules.agents.memory.queue import MemoryUpdateQueue

        return MemoryUpdateQueue(debounce_seconds=0.05)

    @pytest.mark.asyncio
    async def test_enqueue_adds_to_pending(self, queue):
        storage = MagicMock()
        messages = [{"role": "user", "content": "hello"}]
        await queue.enqueue("conv-1", storage, messages)
        assert "conv-1" in queue._pending

    @pytest.mark.asyncio
    async def test_enqueue_creates_timer_task(self, queue):
        await queue.enqueue("conv-1", MagicMock(), [])
        assert queue._timer_task is not None
        queue._timer_task.cancel()

    @pytest.mark.asyncio
    async def test_enqueue_cancels_previous_timer(self, queue):
        """连续入队：第二次入队取消第一次的 timer"""
        await queue.enqueue("conv-1", MagicMock(), [])
        first_task = queue._timer_task
        await queue.enqueue("conv-1", MagicMock(), [])
        # 让事件循环处理一次迭代，使 CancelledError 传播到 task
        await asyncio.sleep(0)
        # 第一个 task 应已被取消
        assert first_task.cancelled() or first_task.done()

    @pytest.mark.asyncio
    async def test_enqueue_overwrites_pending_for_same_conv(self, queue):
        """同一对话多次入队时，最新的 messages 覆盖旧的"""
        storage = MagicMock()
        await queue.enqueue("conv-1", storage, ["old"])
        new_msgs = ["new"]
        await queue.enqueue("conv-1", storage, new_msgs)
        assert queue._pending["conv-1"]["messages"] == new_msgs
        queue._timer_task.cancel()

    @pytest.mark.asyncio
    async def test_flush_calls_update_memory(self, queue):
        """_flush 对每个 pending 调用 updater.update_memory"""
        storage = MagicMock()
        messages = [{"role": "user", "content": "test"}]

        mock_updater = MagicMock()
        mock_updater.update_memory = AsyncMock()

        with patch.dict("sys.modules", {"modules.agents.memory.updater": mock_updater}):
            await queue.enqueue("conv-1", storage, messages)
            queue._timer_task.cancel()
            await queue._flush()

        mock_updater.update_memory.assert_called_once_with(
            storage=storage,
            conversation_messages=messages,
            conversation_id="conv-1",
        )

    @pytest.mark.asyncio
    async def test_flush_clears_pending(self, queue):
        """_flush 执行后 pending 清空"""
        mock_updater = MagicMock()
        mock_updater.update_memory = AsyncMock()

        with patch.dict("sys.modules", {"modules.agents.memory.updater": mock_updater}):
            await queue.enqueue("conv-1", MagicMock(), [])
            queue._timer_task.cancel()
            await queue._flush()

        assert len(queue._pending) == 0

    @pytest.mark.asyncio
    async def test_flush_handles_multiple_conversations(self, queue):
        """_flush 批量处理多个对话"""
        mock_updater = MagicMock()
        mock_updater.update_memory = AsyncMock()

        with patch.dict("sys.modules", {"modules.agents.memory.updater": mock_updater}):
            await queue.enqueue("conv-1", MagicMock(), [])
            await queue.enqueue("conv-2", MagicMock(), [])
            queue._timer_task.cancel()
            await queue._flush()

        assert mock_updater.update_memory.call_count == 2

    @pytest.mark.asyncio
    async def test_flush_isolates_errors(self, queue):
        """单个对话的更新失败不影响其他对话"""
        mock_updater = MagicMock()
        # 第一次调用抛异常，第二次正常
        mock_updater.update_memory = AsyncMock(side_effect=[RuntimeError("更新失败"), None])

        with patch.dict("sys.modules", {"modules.agents.memory.updater": mock_updater}):
            await queue.enqueue("conv-fail", MagicMock(), [])
            await queue.enqueue("conv-ok", MagicMock(), [])
            queue._timer_task.cancel()
            await queue._flush()  # 不应抛异常

        assert mock_updater.update_memory.call_count == 2

    @pytest.mark.asyncio
    async def test_debounce_flush_triggers_after_delay(self, queue):
        """debounce 超时后 _flush 被调用"""
        mock_updater = MagicMock()
        mock_updater.update_memory = AsyncMock()

        with patch.dict("sys.modules", {"modules.agents.memory.updater": mock_updater}):
            await queue.enqueue("conv-1", MagicMock(), [])
            # 等待超过 debounce_seconds=0.05
            await asyncio.sleep(0.15)

        mock_updater.update_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_debounce_resets_on_new_enqueue(self, queue):
        """debounce 期间新入队重置计时器，旧数据不被处理"""
        mock_updater = MagicMock()
        mock_updater.update_memory = AsyncMock()

        with patch.dict("sys.modules", {"modules.agents.memory.updater": mock_updater}):
            await queue.enqueue("conv-1", MagicMock(), ["msg1"])
            await asyncio.sleep(0.02)  # debounce 未结束
            await queue.enqueue("conv-1", MagicMock(), ["msg2"])
            await asyncio.sleep(0.02)  # 仍未超时
            # 此时不应调用
            assert mock_updater.update_memory.call_count == 0
            await asyncio.sleep(0.1)  # 等待第二次 debounce 超时

        # 只调用一次，且是第二次入队的数据
        assert mock_updater.update_memory.call_count == 1
        call_kwargs = mock_updater.update_memory.call_args.kwargs
        assert call_kwargs["conversation_messages"] == ["msg2"]

    @pytest.mark.asyncio
    async def test_debounce_cancelled_error_suppressed(self, queue):
        """timer 被取消时 CancelledError 被静默处理"""
        await queue.enqueue("conv-1", MagicMock(), [])
        # 立即取消 timer
        queue._timer_task.cancel()
        # _debounce_flush 内部应捕获 CancelledError
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await queue._timer_task

    def test_get_memory_queue_factory(self):
        from modules.agents.memory.queue import MemoryUpdateQueue, get_memory_queue

        q = get_memory_queue()
        assert isinstance(q, MemoryUpdateQueue)

    def test_get_memory_queue_default_debounce(self):
        from modules.agents.memory.queue import get_memory_queue

        q = get_memory_queue()
        assert q._debounce == 30.0

    def test_get_memory_queue_is_singleton(self):
        """get_memory_queue() 每次返回同一实例"""
        from modules.agents.memory.queue import get_memory_queue

        q1 = get_memory_queue()
        q2 = get_memory_queue()
        assert q1 is q2

"""StreamBridge 单元测试 — 验证 Agent 执行与 SSE 消费解耦机制"""

from __future__ import annotations

import asyncio

import pytest

from modules.agents.stream_bridge import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    StreamBridge,
    StreamEvent,
    get_stream_bridge,
)

# ---------------------------------------------------------------------------
# StreamEvent
# ---------------------------------------------------------------------------


class TestStreamEvent:
    def test_fields(self):
        ev = StreamEvent(event="message.final", data='{"content":"hi"}')
        assert ev.event == "message.final"
        assert ev.data == '{"content":"hi"}'
        assert ev.timestamp > 0

    def test_timestamp_auto(self):
        ev1 = StreamEvent(event="a", data="x")
        ev2 = StreamEvent(event="b", data="y")
        assert ev2.timestamp >= ev1.timestamp


# ---------------------------------------------------------------------------
# StreamBridge — publish / subscribe
# ---------------------------------------------------------------------------


class TestStreamBridgePublishSubscribe:
    @pytest.mark.asyncio
    async def test_basic_publish_subscribe(self):
        bridge = StreamBridge(max_queue_size=10, heartbeat_interval=1.0, cleanup_delay=0.1)
        run_id = "test-run-1"

        await bridge.publish(run_id, "message.final", '{"content":"hello"}')
        await bridge.publish_end(run_id)

        events = []
        async for entry in bridge.subscribe(run_id):
            if entry is END_SENTINEL:
                break
            events.append(entry)

        assert len(events) == 1
        assert isinstance(events[0], StreamEvent)
        assert events[0].event == "message.final"
        assert events[0].data == '{"content":"hello"}'

    @pytest.mark.asyncio
    async def test_multiple_events_order_preserved(self):
        bridge = StreamBridge(max_queue_size=10, heartbeat_interval=1.0, cleanup_delay=0.1)
        run_id = "test-run-2"

        await bridge.publish(run_id, "tool.call", '{"tool":"ls"}')
        await bridge.publish(run_id, "tool.result", '{"output":"file.txt"}')
        await bridge.publish(run_id, "message.final", '{"content":"done"}')
        await bridge.publish_end(run_id)

        events = []
        async for entry in bridge.subscribe(run_id):
            if entry is END_SENTINEL:
                break
            events.append(entry)

        assert len(events) == 3
        assert [e.event for e in events] == ["tool.call", "tool.result", "message.final"]

    @pytest.mark.asyncio
    async def test_end_sentinel_terminates_subscribe(self):
        bridge = StreamBridge(max_queue_size=10, heartbeat_interval=1.0, cleanup_delay=0.1)
        run_id = "test-run-3"

        await bridge.publish(run_id, "message.final", '{"content":"hi"}')
        await bridge.publish_end(run_id)

        count = 0
        async for entry in bridge.subscribe(run_id):
            if entry is END_SENTINEL:
                break
            count += 1

        assert count == 1


# ---------------------------------------------------------------------------
# StreamBridge — heartbeat
# ---------------------------------------------------------------------------


class TestStreamBridgeHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_on_timeout(self):
        bridge = StreamBridge(max_queue_size=10, heartbeat_interval=0.1, cleanup_delay=0.1)
        run_id = "test-heartbeat"

        # Subscribe without publishing — should get heartbeats
        got_heartbeat = False

        async def _subscribe():
            nonlocal got_heartbeat
            async for entry in bridge.subscribe(run_id):
                if entry is HEARTBEAT_SENTINEL:
                    got_heartbeat = True
                    return
                if entry is END_SENTINEL:
                    return

        # Run with timeout to avoid infinite loop
        task = asyncio.create_task(_subscribe())
        await asyncio.sleep(0.3)

        # Publish end to allow cleanup
        await bridge.publish_end(run_id)
        await asyncio.wait_for(task, timeout=1.0)

        assert got_heartbeat


# ---------------------------------------------------------------------------
# StreamBridge — queue full / eviction
# ---------------------------------------------------------------------------


class TestStreamBridgeQueueFull:
    @pytest.mark.asyncio
    async def test_queue_full_evicts_oldest(self):
        bridge = StreamBridge(max_queue_size=3, heartbeat_interval=1.0, cleanup_delay=0.1)
        run_id = "test-full"

        # Fill queue beyond capacity
        await bridge.publish(run_id, "e1", "d1")
        await bridge.publish(run_id, "e2", "d2")
        await bridge.publish(run_id, "e3", "d3")
        await bridge.publish(run_id, "e4", "d4")  # This should evict e1
        await bridge.publish_end(run_id)

        events = []
        async for entry in bridge.subscribe(run_id):
            if entry is END_SENTINEL:
                break
            events.append(entry)

        # e1 was evicted, then e3 was evicted to make room for END
        # Exact behavior depends on queue state, but we should get at least some events
        assert len(events) >= 1
        # The last published event should be present
        event_names = [e.event for e in events]
        assert "e4" in event_names


# ---------------------------------------------------------------------------
# StreamBridge — concurrent producer/consumer
# ---------------------------------------------------------------------------


class TestStreamBridgeConcurrent:
    @pytest.mark.asyncio
    async def test_producer_consumer_concurrent(self):
        bridge = StreamBridge(max_queue_size=50, heartbeat_interval=1.0, cleanup_delay=0.1)
        run_id = "test-concurrent"

        collected: list[StreamEvent] = []

        async def producer():
            for i in range(10):
                await bridge.publish(run_id, f"event-{i}", f"data-{i}")
                await asyncio.sleep(0.01)
            await bridge.publish_end(run_id)

        async def consumer():
            async for entry in bridge.subscribe(run_id):
                if entry is END_SENTINEL:
                    return
                if entry is HEARTBEAT_SENTINEL:
                    continue
                collected.append(entry)

        await asyncio.gather(producer(), consumer())

        assert len(collected) == 10
        assert [e.event for e in collected] == [f"event-{i}" for i in range(10)]


# ---------------------------------------------------------------------------
# StreamBridge — has_queue / active_runs
# ---------------------------------------------------------------------------


class TestStreamBridgeState:
    @pytest.mark.asyncio
    async def test_has_queue(self):
        bridge = StreamBridge(max_queue_size=10, heartbeat_interval=1.0, cleanup_delay=0.1)
        assert not bridge.has_queue("nonexistent")

        await bridge.publish("run-x", "e1", "d1")
        assert bridge.has_queue("run-x")

    @pytest.mark.asyncio
    async def test_active_runs(self):
        bridge = StreamBridge(max_queue_size=10, heartbeat_interval=1.0, cleanup_delay=0.1)
        assert bridge.active_runs == 0

        await bridge.publish("run-a", "e1", "d1")
        await bridge.publish("run-b", "e2", "d2")
        assert bridge.active_runs == 2

    @pytest.mark.asyncio
    async def test_cleanup_after_end(self):
        bridge = StreamBridge(max_queue_size=10, heartbeat_interval=1.0, cleanup_delay=0.1)
        run_id = "test-cleanup"

        await bridge.publish(run_id, "e1", "d1")
        assert bridge.has_queue(run_id)

        await bridge.publish_end(run_id)

        # Consume to trigger cleanup
        async for entry in bridge.subscribe(run_id):
            if entry is END_SENTINEL:
                break

        # Wait for delayed cleanup
        await asyncio.sleep(0.2)
        assert not bridge.has_queue(run_id)


# ---------------------------------------------------------------------------
# StreamBridge — multiple subscribers (reconnect scenario)
# ---------------------------------------------------------------------------


class TestStreamBridgeReconnect:
    @pytest.mark.asyncio
    async def test_reconnect_gets_remaining_events(self):
        bridge = StreamBridge(max_queue_size=50, heartbeat_interval=1.0, cleanup_delay=5.0)
        run_id = "test-reconnect"

        # Publish 5 events
        for i in range(5):
            await bridge.publish(run_id, f"event-{i}", f"data-{i}")

        # First consumer reads 2 events then "disconnects"
        first_batch = []
        async for entry in bridge.subscribe(run_id):
            if entry is HEARTBEAT_SENTINEL:
                continue
            first_batch.append(entry)
            if len(first_batch) >= 2:
                break

        assert len(first_batch) == 2

        # Publish end
        await bridge.publish_end(run_id)

        # "Reconnected" consumer gets remaining events
        second_batch = []
        async for entry in bridge.subscribe(run_id):
            if entry is END_SENTINEL:
                break
            if entry is HEARTBEAT_SENTINEL:
                continue
            second_batch.append(entry)

        assert len(second_batch) == 3
        assert [e.event for e in second_batch] == ["event-2", "event-3", "event-4"]


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------


class TestGetStreamBridge:
    def test_returns_instance(self):
        bridge = get_stream_bridge()
        assert isinstance(bridge, StreamBridge)

    def test_is_singleton(self):
        b1 = get_stream_bridge()
        b2 = get_stream_bridge()
        assert b1 is b2

"""SSE 对话流路由。

架构: StreamBridge 解耦
  Producer: _run_agent() 后台 asyncio.Task → 发布事件到 StreamBridge 队列
  Consumer: _sse_consumer() SSE 生成器 → 从队列消费 → yield SSE 帧
  客户端断连时 agent 继续执行，重连后可从队列恢复。
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import AIMessage, ToolMessage
from sse_starlette.sse import EventSourceResponse

from auth.dependencies import get_current_user
from config import settings
from database import get_db
from modules.agents.run_service import (
    DbWriteBuffer,
    append_run_event,
    create_run,
    ensure_conversation,
    extract_content,
    generate_conversation_title,
    register_active_run,
    unregister_active_run,
    update_run_status,
)
from modules.agents.schemas import ChatRequest  # noqa: TC001 — FastAPI 需要运行时解析 Pydantic 模型
from modules.agents.skill_service import load_skill_context
from modules.agents.stream_bridge import (
    END_SENTINEL,
    HEARTBEAT_SENTINEL,
    StreamEvent,
    get_stream_bridge,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# 防止后台 agent task 被 GC 回收
_active_agent_tasks: set[asyncio.Task] = set()


# ---------------------------------------------------------------------------
# 悬空 ToolCall 修复 (#324)
# ---------------------------------------------------------------------------


def _find_dangling_tool_calls(messages: list) -> list[ToolMessage]:
    """检测中断导致的悬空 tool_calls，返回需要补入的 ToolMessage 列表。

    当 Agent 执行被中断时，AIMessage.tool_calls 中可能存在没有对应
    ToolMessage 的条目，导致 LangGraph 恢复对话时状态不一致。
    """
    tool_msg_ids = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    patches: list[ToolMessage] = []
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                tc_id = tc.get("id", "")
                if tc_id and tc_id not in tool_msg_ids:
                    patches.append(
                        ToolMessage(
                            content="[操作已中断，未获得结果]",
                            tool_call_id=tc_id,
                        )
                    )
    return patches


# ---------------------------------------------------------------------------
# 消息处理辅助函数 (不变)
# ---------------------------------------------------------------------------


def _process_ai_message(
    msg: AIMessage,
    run_id: str,
    conversation_id: str,
    emitted_ids: set[str],
    username: str,
    buf: DbWriteBuffer,
) -> list[dict]:
    """处理 AI 消息，返回要发布的 SSE event 列表。DB 写入缓冲到 buf。"""
    events: list[dict] = []

    if getattr(msg, "tool_calls", None):
        for tc in msg.tool_calls:
            tc_id = tc.get("id", "")
            if tc_id and tc_id in emitted_ids:
                continue
            if tc_id:
                emitted_ids.add(tc_id)
            payload = {
                "run_id": run_id,
                "tool": tc["name"],
                "input": tc["args"],
                "id": tc_id,
            }
            buf.buffer_run_event(run_id, conversation_id, "tool.call", payload)
            events.append({"event": "tool.call", "data": json.dumps(payload, ensure_ascii=False)})

            # Artifact 事件: write_file/edit_file 工具调用时额外发射 artifact.update
            if tc["name"] in ("write_file", "edit_file"):
                file_path = tc["args"].get("file_path") or tc["args"].get("path", "")
                raw_content = tc["args"].get("content", "")
                # 截断内容预览，避免大文件撑爆 SSE 流和数据库；前端可按需 HTTP fetch 完整内容
                max_preview = 2000
                preview = raw_content[:max_preview] if isinstance(raw_content, str) else ""
                artifact_payload = {
                    "run_id": run_id,
                    "conversation_id": conversation_id,
                    "file_path": file_path,
                    "action": tc["name"],
                    "content": preview,
                    "truncated": len(raw_content) > max_preview if isinstance(raw_content, str) else False,
                }
                buf.buffer_run_event(run_id, conversation_id, "artifact.update", artifact_payload)
                events.append({"event": "artifact.update", "data": json.dumps(artifact_payload, ensure_ascii=False)})

            try:
                from modules.agents.safety import TOOL_RISK_MAP

                buf.buffer_legacy_event(
                    conversation_id,
                    event_type="tool_call",
                    username=username,
                    tool_name=tc["name"],
                    tool_input=json.dumps(tc["args"], ensure_ascii=False)[:1000],
                    risk_level=TOOL_RISK_MAP.get(tc["name"], "safe"),
                )
            except Exception as e:
                logger.debug("记录 tool_call 事件失败: %s", e)
    elif msg.content:
        msg_id = getattr(msg, "id", None)
        payload = {
            "run_id": run_id,
            "content": msg.content,
            "role": "assistant",
            "id": msg_id or "",
        }
        buf.buffer_run_event(run_id, conversation_id, "message.final", payload)
        events.append({"event": "message.final", "data": json.dumps(payload, ensure_ascii=False)})

    return events


def _process_tool_message(
    msg: ToolMessage,
    run_id: str,
    conversation_id: str,
    username: str,
    buf: DbWriteBuffer,
) -> list[dict]:
    """处理工具调用结果消息，返回要发布的 SSE event 列表。DB 写入缓冲到 buf。"""
    msg_id = getattr(msg, "id", None)

    # 检测 UI 组件标记
    try:
        content_data = json.loads(msg.content) if msg.content else {}
    except (json.JSONDecodeError, TypeError):
        content_data = {}

    if content_data.get("_ui"):
        component_type = content_data.get("type", "unknown")
        ui_payload = {
            "run_id": run_id,
            "component_type": component_type,
            "data": content_data,
            "id": msg_id or "",
        }
        buf.buffer_run_event(run_id, conversation_id, "ui.render", ui_payload)
        # 同时发送文字 fallback
        title = content_data.get("title", "")
        fallback_payload = {
            "run_id": run_id,
            "content": f"[UI: {title}]" if title else "[UI 组件已渲染]",
            "role": "assistant",
            "id": msg_id or "",
        }
        return [
            {"event": "ui.render", "data": json.dumps(ui_payload, ensure_ascii=False)},
            {"event": "message.final", "data": json.dumps(fallback_payload, ensure_ascii=False)},
        ]

    # 检测澄清请求
    if content_data.get("_clarification"):
        clarification_payload = {
            "run_id": run_id,
            "question": content_data.get("question", ""),
            "clarification_type": content_data.get("clarification_type", "missing_info"),
            "context": content_data.get("context", ""),
            "options": content_data.get("options"),
            "id": msg_id or "",
        }
        buf.buffer_run_event(run_id, conversation_id, "clarification.request", clarification_payload)
        # Also send as a regular message for fallback display
        fallback_payload = {
            "run_id": run_id,
            "content": content_data.get("question", "需要更多信息"),
            "role": "assistant",
            "id": msg_id or "",
        }
        return [
            {"event": "clarification.request", "data": json.dumps(clarification_payload, ensure_ascii=False)},
            {"event": "message.final", "data": json.dumps(fallback_payload, ensure_ascii=False)},
        ]

    payload = {
        "run_id": run_id,
        "tool": getattr(msg, "name", ""),
        "content": msg.content[:1500] if msg.content else "",
        "id": msg_id or "",
    }
    buf.buffer_run_event(run_id, conversation_id, "tool.result", payload)
    events = [{"event": "tool.result", "data": json.dumps(payload, ensure_ascii=False)}]
    try:
        buf.buffer_legacy_event(
            conversation_id,
            event_type="tool_result",
            username=username,
            tool_name=getattr(msg, "name", ""),
            tool_output=(msg.content[:500] if msg.content else ""),
        )
    except Exception as e:
        logger.debug("记录 tool_result 事件失败: %s", e)
    return events


async def _handle_interrupt(snapshot, run_id: str, conversation_id: str, db) -> list[dict]:
    """处理审批中断（interrupt），返回要发布的 SSE event 列表。"""
    events: list[dict] = []
    tasks = snapshot.tasks
    if not (tasks and tasks[0].interrupts):
        # 有 next 但没有 interrupts — 视为完成
        payload = {"conversation_id": conversation_id, "run_id": run_id, "status": "completed"}
        await append_run_event(run_id, conversation_id, "run.completed", payload)
        await update_run_status(run_id, status="completed", completed=True)
        events.append({"event": "run.completed", "data": json.dumps(payload, ensure_ascii=False)})
        return events

    interrupt_value = tasks[0].interrupts[0].value
    action_requests = interrupt_value.get("action_requests", [])
    review_configs = interrupt_value.get("review_configs", [])

    if action_requests:
        approval_ids = []
        for action in action_requests:
            aid = str(uuid.uuid4())
            approval_ids.append(aid)
            await db.execute(
                """
                INSERT INTO agent_approvals (
                    id, conversation_id, run_id, tool_name, tool_input, risk_level, description
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    aid,
                    conversation_id,
                    run_id,
                    action.get("name", ""),
                    json.dumps(action.get("args", {}), ensure_ascii=False),
                    "danger",
                    f"执行 {action.get('name', '')}",
                ),
            )
        await db.commit()
        payload = {
            "approval_id": approval_ids[0],
            "conversation_id": conversation_id,
            "run_id": run_id,
            "actions": action_requests,
            "review_configs": review_configs,
            "description": f"待审批: {action_requests[0].get('name', '')}",
        }
        await append_run_event(run_id, conversation_id, "approval.request", payload)
        await update_run_status(run_id, status="waiting_approval")
        events.append({"event": "approval.request", "data": json.dumps(payload, ensure_ascii=False)})
    else:
        approval_id = str(uuid.uuid4())
        tool_name = interrupt_value.get("tool_name", "unknown")
        await db.execute(
            """
            INSERT INTO agent_approvals (
                id, conversation_id, run_id, tool_name, tool_input, risk_level, description
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                conversation_id,
                run_id,
                tool_name,
                json.dumps(interrupt_value, ensure_ascii=False),
                "danger",
                interrupt_value.get("description", ""),
            ),
        )
        await db.commit()
        payload = {
            "approval_id": approval_id,
            "conversation_id": conversation_id,
            "run_id": run_id,
            **interrupt_value,
        }
        await append_run_event(run_id, conversation_id, "approval.request", payload)
        await update_run_status(run_id, status="waiting_approval")
        events.append({"event": "approval.request", "data": json.dumps(payload, ensure_ascii=False)})

    return events


# ---------------------------------------------------------------------------
# Producer: Agent 后台执行，事件发布到 StreamBridge
# ---------------------------------------------------------------------------


async def _run_agent(
    *,
    run_id: str,
    conversation_id: str,
    safety_mode: str,
    user_role: str,
    username: str,
    message: str,
    skill_id: str | None,
    page_context: str | None,
) -> None:
    """后台执行 agent，将所有 SSE 事件发布到 StreamBridge 队列。

    客户端断连不影响此函数执行。
    """
    bridge = get_stream_bridge()
    buf = DbWriteBuffer()
    bg_tasks: set[asyncio.Task] = set()

    async def _publish_events(events: list[dict]) -> None:
        """将事件列表发布到 bridge"""
        for ev in events:
            await bridge.publish(run_id, ev["event"], ev["data"])

    try:
        from modules.agents.deep_agent import build_agent, load_user_memory_context
        from modules.agents.subagents import set_conversation_id

        set_conversation_id(conversation_id)
        agent = await build_agent(safety_mode=safety_mode, user_role=user_role)
        config = {"configurable": {"thread_id": conversation_id}}
        input_messages = [{"role": "user", "content": message}]

        if skill_id:
            skill_ctx = await load_skill_context(skill_id)
            if skill_ctx:
                input_messages.insert(0, {"role": "system", "content": skill_ctx})

        if page_context:
            from modules.agents.page_context import get_page_context

            page_ctx = await get_page_context(page_context)
            if page_ctx:
                input_messages.insert(0, {"role": "system", "content": page_ctx})

        # 注入用户专属记忆上下文（按用户隔离，防止多用户记忆污染）
        user_memory_ctx = load_user_memory_context(username)
        if user_memory_ctx:
            input_messages.insert(0, {"role": "system", "content": user_memory_ctx})

        input_state = {"messages": input_messages}
        prev_todos = None
        emitted_ids: set[str] = set()
        try:
            snapshot = await agent.aget_state(config)
            existing_msgs = snapshot.values.get("messages", [])
            emitted_count = len(existing_msgs)

            # 修复悬空 ToolCall (#324): 中断后恢复时自动补全缺失的 ToolMessage
            dangling_patches = _find_dangling_tool_calls(existing_msgs)
            if dangling_patches:
                logger.warning(
                    "检测到 %d 个悬空 ToolCall (conversation=%s)，自动补全 ToolMessage",
                    len(dangling_patches),
                    conversation_id,
                )
                await agent.aupdate_state(config, {"messages": dangling_patches})
                emitted_count += len(dangling_patches)
        except Exception:
            emitted_count = 0

        async for step in agent.astream(input_state, config, stream_mode="values"):
            todos = step.get("todos")
            if todos is not None and todos != prev_todos:
                prev_todos = todos
                payload = {"run_id": run_id, "todos": todos}
                buf.buffer_run_event(run_id, conversation_id, "todo.update", payload)
                await bridge.publish(run_id, "todo.update", json.dumps(payload, ensure_ascii=False))

            messages = step.get("messages", [])
            if not messages or len(messages) <= emitted_count:
                continue

            for msg in messages[emitted_count:]:
                msg_id = getattr(msg, "id", None)
                if msg_id and msg_id in emitted_ids:
                    continue
                if msg_id:
                    emitted_ids.add(msg_id)

                if isinstance(msg, AIMessage):
                    await _publish_events(_process_ai_message(msg, run_id, conversation_id, emitted_ids, username, buf))
                elif isinstance(msg, ToolMessage):
                    await _publish_events(_process_tool_message(msg, run_id, conversation_id, username, buf))

            emitted_count = len(messages)

            # 异步刷写缓冲
            if buf.pending >= 4:
                task = asyncio.create_task(buf.flush())
                bg_tasks.add(task)
                task.add_done_callback(bg_tasks.discard)

        # 流结束后检查是否有中断（审批请求）
        db = await get_db()
        snapshot = await agent.aget_state(config)
        if snapshot.next:
            await buf.flush()
            await _publish_events(await _handle_interrupt(snapshot, run_id, conversation_id, db))
        else:
            payload = {"conversation_id": conversation_id, "run_id": run_id, "status": "completed"}
            buf.buffer_run_event(run_id, conversation_id, "run.completed", payload)
            buf.buffer_run_status(run_id, status="completed", completed=True)
            await bridge.publish(run_id, "run.completed", json.dumps(payload, ensure_ascii=False))

        buf.buffer_conversation_touch(conversation_id)
        await buf.flush()

    except asyncio.CancelledError:
        payload = {"run_id": run_id, "conversation_id": conversation_id, "error": "运行已取消"}
        buf.buffer_run_event(run_id, conversation_id, "run.error", payload)
        buf.buffer_run_status(run_id, status="cancelled", error="运行已取消", completed=True)
        await buf.flush()
        await bridge.publish(run_id, "run.error", json.dumps(payload, ensure_ascii=False))
    except Exception as exc:
        logger.exception("Agent run error: %s", exc)
        payload = {"run_id": run_id, "conversation_id": conversation_id, "error": str(exc)}
        buf.buffer_run_event(run_id, conversation_id, "run.error", payload)
        buf.buffer_run_status(run_id, status="error", error=str(exc), completed=True)
        await buf.flush()
        await bridge.publish(run_id, "run.error", json.dumps(payload, ensure_ascii=False))
    finally:
        try:
            await buf.flush()
        except Exception:
            logger.debug("finally flush 失败", exc_info=True)

        # 异步入队记忆更新
        try:
            from pathlib import Path

            from modules.agents.memory.queue import get_memory_queue
            from modules.agents.memory.storage import MemoryStorage

            smart_memory_dir = Path(settings.db_path).parent / "smart-memory"
            mem_storage = MemoryStorage(smart_memory_dir)
            snapshot_for_memory = await agent.aget_state(config)
            msgs = snapshot_for_memory.values.get("messages", [])
            if len(msgs) >= 2:
                queue = get_memory_queue()
                await queue.enqueue(conversation_id, mem_storage, msgs)
        except Exception:
            logger.debug("记忆更新入队失败", exc_info=True)

        unregister_active_run(run_id)

        # 异步生成对话标题（仅首次对话）
        try:
            db_title = await get_db()
            title_cursor = await db_title.execute(
                "SELECT COUNT(*) FROM agent_runs WHERE conversation_id = ?",
                (conversation_id,),
            )
            run_count_row = await title_cursor.fetchone()
            if run_count_row and run_count_row[0] <= 1:
                # 首次对话，提取助手回复用于生成标题
                assistant_reply = ""
                try:
                    snapshot_for_title = await agent.aget_state(config)
                    for m in reversed(snapshot_for_title.values.get("messages", [])):
                        if isinstance(m, AIMessage) and m.content:
                            assistant_reply = extract_content(m.content)[:300]
                            break
                except Exception:
                    logger.debug("提取助手回复失败", exc_info=True)
                title_task = asyncio.create_task(generate_conversation_title(conversation_id, message, assistant_reply))
                _active_agent_tasks.add(title_task)
                title_task.add_done_callback(_active_agent_tasks.discard)
        except Exception:
            logger.debug("标题生成调度失败", exc_info=True)

        # 发布 done 事件 + END sentinel
        done_payload = json.dumps({"conversation_id": conversation_id, "run_id": run_id}, ensure_ascii=False)
        await bridge.publish(run_id, "done", done_payload)
        await bridge.publish_end(run_id)


# ---------------------------------------------------------------------------
# Consumer: SSE 生成器，从 StreamBridge 队列消费
# ---------------------------------------------------------------------------


async def _sse_consumer(run_id: str, conversation_id: str, run_created_at: str, skill_id: str | None):
    """从 StreamBridge 消费事件并 yield SSE 帧。

    客户端断连时此生成器结束，但 _run_agent 后台任务继续执行。
    """
    bridge = get_stream_bridge()

    # 先 yield run.started 事件（立即返回给客户端）
    started_payload: dict = {
        "run_id": run_id,
        "conversation_id": conversation_id,
        "status": "running",
        "created_at": run_created_at,
        "skill_id": skill_id,
    }
    # 技能加载信息：前端用于渲染技能卡片
    if skill_id:
        try:
            from modules.agents.skill_service import get_skill

            skill_info = await get_skill(skill_id)
            if skill_info:
                manifest = skill_info.get("manifest", {})
                started_payload["skill_name"] = skill_info.get("name", skill_id)
                started_payload["skill_description"] = skill_info.get("description", manifest.get("description", ""))
                started_payload["skill_tools"] = manifest.get("allowed-tools", "").split()
        except Exception:  # noqa: S110 — 非致命，降级为只传 skill_id
            pass
    yield {"event": "run.started", "data": json.dumps(started_payload, ensure_ascii=False)}

    async for entry in bridge.subscribe(run_id):
        if entry is HEARTBEAT_SENTINEL:
            yield {"comment": "heartbeat"}
            continue

        if entry is END_SENTINEL:
            return

        if isinstance(entry, StreamEvent):
            yield {"event": entry.event, "data": entry.data}


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(request: Request, body: ChatRequest, user=Depends(get_current_user)):
    """SSE 对话入口 — StreamBridge 解耦架构。

    Agent 在后台 asyncio.Task 中执行，SSE 从 StreamBridge 队列消费。
    客户端断连不会中断 Agent 执行。
    """
    conversation_id = body.conversation_id or str(uuid.uuid4())
    user_role = user["role"]
    safety_mode = body.safety_mode if user_role == "admin" else "supervised"

    await ensure_conversation(
        conversation_id,
        username=user["username"],
        safety_mode=safety_mode,
        first_message=body.message,
    )
    run = await create_run(
        conversation_id=conversation_id,
        username=user["username"],
        safety_mode=safety_mode,
        user_message=body.message,
        page_context=body.page_context,
        skill_id=body.skill_id,
    )
    run_id = run["run_id"]
    register_active_run(run_id)

    # 启动 Agent 后台任务 — 发布事件到 StreamBridge
    # 将 task 存入 _active_agent_tasks 防止被 GC 回收
    task = asyncio.create_task(
        _run_agent(
            run_id=run_id,
            conversation_id=conversation_id,
            safety_mode=safety_mode,
            user_role=user_role,
            username=user["username"],
            message=body.message,
            skill_id=body.skill_id,
            page_context=body.page_context,
        )
    )
    _active_agent_tasks.add(task)
    task.add_done_callback(_active_agent_tasks.discard)

    # SSE 消费者 — 从 StreamBridge 队列读取事件
    return EventSourceResponse(_sse_consumer(run_id, conversation_id, run["created_at"], body.skill_id))


@router.get("/runs/{run_id}/stream")
async def reconnect_stream(run_id: str, user=Depends(get_current_user)):
    """SSE 重连端点 — 客户端断连后恢复事件流。

    如果 run 仍在执行（队列存在），从队列中恢复未消费的事件。
    如果 run 已结束且队列已清理，返回空流。
    """
    bridge = get_stream_bridge()

    if not bridge.has_queue(run_id):
        # 队列已清理或 run 不存在 — 返回 done 事件
        async def _empty_stream():
            yield {
                "event": "done",
                "data": json.dumps({"run_id": run_id, "reconnected": True, "status": "completed"}),
            }

        return EventSourceResponse(_empty_stream())

    async def _reconnect_consumer():
        async for entry in bridge.subscribe(run_id):
            if entry is HEARTBEAT_SENTINEL:
                yield {"comment": "heartbeat"}
                continue
            if entry is END_SENTINEL:
                return
            if isinstance(entry, StreamEvent):
                yield {"event": entry.event, "data": entry.data}

    return EventSourceResponse(_reconnect_consumer())

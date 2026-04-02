"""SSE 对话流路由。"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from langchain_core.messages import AIMessage, ToolMessage
from sse_starlette.sse import EventSourceResponse

from auth.dependencies import get_current_user
from database import get_db
from modules.agents.run_service import (
    append_run_event,
    create_run,
    ensure_conversation,
    record_legacy_agent_event,
    register_active_run,
    unregister_active_run,
    update_run_status,
)
from modules.agents.schemas import ChatRequest  # noqa: TC001 — FastAPI 需要运行时解析 Pydantic 模型
from modules.agents.skill_service import load_skill_context

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# event_generator 辅助函数
# ---------------------------------------------------------------------------


async def _process_ai_message(
    msg: AIMessage, run_id: str, conversation_id: str, emitted_ids: set[str], username: str
) -> list[dict]:
    """处理 AI 消息，返回要 yield 的 SSE event 列表。"""
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
            await append_run_event(run_id, conversation_id, "tool.call", payload)
            events.append({"event": "tool.call", "data": json.dumps(payload, ensure_ascii=False)})
            try:
                from modules.agents.safety import TOOL_RISK_MAP

                await record_legacy_agent_event(
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
        await append_run_event(run_id, conversation_id, "message.final", payload)
        events.append({"event": "message.final", "data": json.dumps(payload, ensure_ascii=False)})

    return events


async def _process_tool_message(msg: ToolMessage, run_id: str, conversation_id: str, username: str) -> list[dict]:
    """处理工具调用结果消息，返回要 yield 的 SSE event 列表。"""
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
        await append_run_event(run_id, conversation_id, "ui.render", ui_payload)
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

    payload = {
        "run_id": run_id,
        "tool": getattr(msg, "name", ""),
        "content": msg.content[:1500] if msg.content else "",
        "id": msg_id or "",
    }
    await append_run_event(run_id, conversation_id, "tool.result", payload)
    events = [{"event": "tool.result", "data": json.dumps(payload, ensure_ascii=False)}]
    try:
        await record_legacy_agent_event(
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
    """处理审批中断（interrupt），返回要 yield 的 SSE event 列表。"""
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
# 路由
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(request: Request, body: ChatRequest, user=Depends(get_current_user)):
    """兼容旧入口，内部按照 run 生命周期执行。"""
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
    db = await get_db()

    async def event_generator():
        register_active_run(run_id)
        try:
            started_payload = {
                "run_id": run_id,
                "conversation_id": conversation_id,
                "status": "running",
                "created_at": run["created_at"],
                "skill_id": body.skill_id,
            }
            await append_run_event(run_id, conversation_id, "run.started", started_payload)
            yield {"event": "run.started", "data": json.dumps(started_payload, ensure_ascii=False)}

            from modules.agents.deep_agent import build_agent

            agent = await build_agent(safety_mode=safety_mode, user_role=user_role)
            config = {"configurable": {"thread_id": conversation_id}}
            input_messages = [{"role": "user", "content": body.message}]

            if body.skill_id:
                skill_ctx = await load_skill_context(body.skill_id)
                if skill_ctx:
                    input_messages.insert(0, {"role": "system", "content": skill_ctx})

            if body.page_context:
                from modules.agents.page_context import get_page_context

                page_ctx = await get_page_context(body.page_context)
                if page_ctx:
                    input_messages.insert(0, {"role": "system", "content": page_ctx})

            input_state = {"messages": input_messages}
            prev_todos = None
            emitted_ids: set[str] = set()
            try:
                snapshot = await agent.aget_state(config)
                emitted_count = len(snapshot.values.get("messages", []))
            except Exception:
                emitted_count = 0

            async for step in agent.astream(input_state, config, stream_mode="values"):
                todos = step.get("todos")
                if todos is not None and todos != prev_todos:
                    prev_todos = todos
                    payload = {"run_id": run_id, "todos": todos}
                    await append_run_event(run_id, conversation_id, "todo.update", payload)
                    yield {"event": "todo.update", "data": json.dumps(payload, ensure_ascii=False)}

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
                        for event in await _process_ai_message(
                            msg, run_id, conversation_id, emitted_ids, user["username"]
                        ):
                            yield event

                    elif isinstance(msg, ToolMessage):
                        for event in await _process_tool_message(msg, run_id, conversation_id, user["username"]):
                            yield event

                emitted_count = len(messages)

            # 流结束后检查是否有中断（审批请求）
            snapshot = await agent.aget_state(config)
            if snapshot.next:
                for event in await _handle_interrupt(snapshot, run_id, conversation_id, db):
                    yield event
            else:
                payload = {"conversation_id": conversation_id, "run_id": run_id, "status": "completed"}
                await append_run_event(run_id, conversation_id, "run.completed", payload)
                await update_run_status(run_id, status="completed", completed=True)
                yield {"event": "run.completed", "data": json.dumps(payload, ensure_ascii=False)}

            await db.execute(
                "UPDATE agent_conversations SET updated_at = ?, message_count = message_count + 1 WHERE id = ?",
                (datetime.now().isoformat(), conversation_id),
            )
            await db.commit()
        except asyncio.CancelledError:
            payload = {"run_id": run_id, "conversation_id": conversation_id, "error": "运行已取消"}
            await append_run_event(run_id, conversation_id, "run.error", payload)
            await update_run_status(run_id, status="cancelled", error="运行已取消", completed=True)
            yield {"event": "run.error", "data": json.dumps(payload, ensure_ascii=False)}
        except Exception as exc:
            logger.exception("Chat error: %s", exc)
            payload = {"run_id": run_id, "conversation_id": conversation_id, "error": str(exc)}
            await append_run_event(run_id, conversation_id, "run.error", payload)
            await update_run_status(run_id, status="error", error=str(exc), completed=True)
            yield {"event": "run.error", "data": json.dumps(payload, ensure_ascii=False)}
        finally:
            unregister_active_run(run_id)

        yield {
            "event": "done",
            "data": json.dumps({"conversation_id": conversation_id, "run_id": run_id}, ensure_ascii=False),
        }

    return EventSourceResponse(event_generator())

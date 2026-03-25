"""SSE 对话流路由"""

import uuid
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request, Depends
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import AIMessage, ToolMessage

from auth.dependencies import get_current_user
from database import get_db
from modules.agents.schemas import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/chat")
async def chat(request: Request, body: ChatRequest, user=Depends(get_current_user)):
    """发送消息并通过 SSE 流式返回 Deep Agent 响应"""
    conversation_id = body.conversation_id or str(uuid.uuid4())
    user_role = user["role"]
    # 非管理员强制 supervised 模式
    safety_mode = body.safety_mode if user_role == "admin" else "supervised"
    db = await get_db()

    # 创建或更新对话记录
    existing = await db.execute(
        "SELECT id FROM agent_conversations WHERE id = ?", (conversation_id,)
    )
    if not await existing.fetchone():
        title = body.message[:30] + ("..." if len(body.message) > 30 else "")
        await db.execute(
            "INSERT INTO agent_conversations (id, title, username, safety_mode) VALUES (?, ?, ?, ?)",
            (conversation_id, title, user["username"], safety_mode),
        )
        await db.commit()

    async def event_generator():
        try:
            from modules.agents.deep_agent import build_agent
            agent = await build_agent(safety_mode=safety_mode, user_role=user_role)
            config = {"configurable": {"thread_id": conversation_id}}

            # 页面上下文注入（气泡对话框传入当前页面标识）
            input_messages = [{"role": "user", "content": body.message}]
            if body.page_context:
                from modules.agents.page_context import get_page_context
                page_ctx = await get_page_context(body.page_context)
                if page_ctx:
                    input_messages.insert(0, {"role": "system", "content": page_ctx})

            input_state = {"messages": input_messages}

            # 流式获取状态更新（跟踪已发送消息数，避免重复）
            _prev_todos = None
            _emitted_count = 0
            async for step in agent.astream(input_state, config, stream_mode="values"):
                messages = step.get("messages", [])

                # 检测 todos 变化
                todos = step.get("todos")
                if todos is not None and todos != _prev_todos:
                    _prev_todos = todos
                    yield {
                        "event": "todo_update",
                        "data": json.dumps(todos, ensure_ascii=False),
                    }

                if not messages or len(messages) <= _emitted_count:
                    continue

                # 只处理本步骤新增的消息
                for msg in messages[_emitted_count:]:
                    if isinstance(msg, AIMessage):
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                yield {
                                    "event": "tool_call",
                                    "data": json.dumps({
                                        "tool": tc["name"],
                                        "input": tc["args"],
                                    }, ensure_ascii=False),
                                }
                                # 记录工具调用事件
                                try:
                                    from modules.agents.safety import TOOL_RISK_MAP
                                    await db.execute(
                                        "INSERT INTO agent_events (conversation_id, event_type, tool_name, tool_input, risk_level, username) "
                                        "VALUES (?, 'tool_call', ?, ?, ?, ?)",
                                        (conversation_id, tc["name"], json.dumps(tc["args"], ensure_ascii=False)[:1000],
                                         TOOL_RISK_MAP.get(tc["name"], "safe"), user["username"]),
                                    )
                                except Exception:
                                    pass
                        elif msg.content:
                            yield {
                                "event": "message",
                                "data": json.dumps({
                                    "content": msg.content,
                                    "role": "assistant",
                                }, ensure_ascii=False),
                            }

                    elif isinstance(msg, ToolMessage):
                        yield {
                            "event": "tool_result",
                            "data": json.dumps({
                                "tool": getattr(msg, "name", ""),
                                "content": msg.content[:1500] if msg.content else "",
                            }, ensure_ascii=False),
                        }
                        # 记录工具结果事件
                        try:
                            await db.execute(
                                "INSERT INTO agent_events (conversation_id, event_type, tool_name, tool_output, username) "
                                "VALUES (?, 'tool_result', ?, ?, ?)",
                                (conversation_id, getattr(msg, "name", ""),
                                 (msg.content[:500] if msg.content else ""), user["username"]),
                            )
                        except Exception:
                            pass

                _emitted_count = len(messages)

            # 检查 interrupt（审批请求）
            snapshot = await agent.aget_state(config)
            if snapshot.next:
                tasks = snapshot.tasks
                if tasks and tasks[0].interrupts:
                    interrupt_value = tasks[0].interrupts[0].value

                    # Deep Agents 格式: {action_requests, review_configs}
                    action_requests = interrupt_value.get("action_requests", [])
                    review_configs = interrupt_value.get("review_configs", [])

                    if action_requests:
                        approval_ids = []
                        for action in action_requests:
                            aid = str(uuid.uuid4())
                            approval_ids.append(aid)
                            await db.execute(
                                "INSERT INTO agent_approvals (id, conversation_id, tool_name, tool_input, risk_level, description) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                (
                                    aid, conversation_id,
                                    action.get("name", ""),
                                    json.dumps(action.get("args", {}), ensure_ascii=False),
                                    "danger",
                                    f"执行 {action.get('name', '')}",
                                ),
                            )
                        await db.commit()

                        yield {
                            "event": "approval_request",
                            "data": json.dumps({
                                "approval_id": approval_ids[0],
                                "conversation_id": conversation_id,
                                "actions": action_requests,
                                "review_configs": review_configs,
                            }, ensure_ascii=False),
                        }
                    else:
                        # 兼容旧格式 interrupt
                        approval_id = str(uuid.uuid4())
                        tool_name = interrupt_value.get("tool_name", "unknown")
                        await db.execute(
                            "INSERT INTO agent_approvals (id, conversation_id, tool_name, tool_input, risk_level, description) "
                            "VALUES (?, ?, ?, ?, ?, ?)",
                            (approval_id, conversation_id, tool_name,
                             json.dumps(interrupt_value, ensure_ascii=False), "danger",
                             interrupt_value.get("description", "")),
                        )
                        await db.commit()
                        yield {
                            "event": "approval_request",
                            "data": json.dumps({
                                "approval_id": approval_id,
                                "conversation_id": conversation_id,
                                **interrupt_value,
                            }, ensure_ascii=False),
                        }

            # 更新对话
            await db.execute(
                "UPDATE agent_conversations SET updated_at = ?, message_count = message_count + 1 WHERE id = ?",
                (datetime.now().isoformat(), conversation_id),
            )
            await db.commit()

        except Exception as e:
            logger.error(f"Chat error: {e}", exc_info=True)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False),
            }

        yield {
            "event": "done",
            "data": json.dumps({"conversation_id": conversation_id}, ensure_ascii=False),
        }

    return EventSourceResponse(event_generator())

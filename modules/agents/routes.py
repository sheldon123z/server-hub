"""智能体 API 路由 — Deep Agent 对话 SSE + 审批 + 巡检 + WebSocket 终端"""

import uuid
import json
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Request, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from langgraph.types import Command

from auth.dependencies import require_role
from database import get_db
from modules.agents.schemas import ChatRequest, ApprovalAction, PatrolUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["AI Agent"])


# ─── 对话 ───

@router.post("/chat")
async def chat(request: Request, body: ChatRequest, user=Depends(require_role("admin"))):
    """发送消息并通过 SSE 流式返回 Deep Agent 响应"""
    conversation_id = body.conversation_id or str(uuid.uuid4())
    db = await get_db()

    # 创建或更新对话记录
    existing = await db.execute(
        "SELECT id FROM agent_conversations WHERE id = ?", (conversation_id,)
    )
    if not await existing.fetchone():
        title = body.message[:30] + ("..." if len(body.message) > 30 else "")
        await db.execute(
            "INSERT INTO agent_conversations (id, title, username, safety_mode) VALUES (?, ?, ?, ?)",
            (conversation_id, title, user["username"], body.safety_mode),
        )
        await db.commit()

    async def event_generator():
        try:
            from modules.agents.deep_agent import build_agent
            agent = await build_agent(safety_mode=body.safety_mode)
            config = {"configurable": {"thread_id": conversation_id}}

            input_state = {
                "messages": [{"role": "user", "content": body.message}],
            }

            # 流式获取状态更新
            _prev_todos = None
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

                if not messages:
                    continue

                last = messages[-1]

                if isinstance(last, AIMessage):
                    if hasattr(last, "tool_calls") and last.tool_calls:
                        for tc in last.tool_calls:
                            yield {
                                "event": "tool_call",
                                "data": json.dumps({
                                    "tool": tc["name"],
                                    "input": tc["args"],
                                }, ensure_ascii=False),
                            }
                    elif last.content:
                        yield {
                            "event": "message",
                            "data": json.dumps({
                                "content": last.content,
                                "role": "assistant",
                            }, ensure_ascii=False),
                        }

                elif isinstance(last, ToolMessage):
                    yield {
                        "event": "tool_result",
                        "data": json.dumps({
                            "tool": getattr(last, "name", ""),
                            "content": last.content[:1500] if last.content else "",
                        }, ensure_ascii=False),
                    }

            # 检查 interrupt（审批请求）
            snapshot = await agent.aget_state(config)
            if snapshot.next:
                tasks = snapshot.tasks
                if tasks and tasks[0].interrupts:
                    interrupt_value = tasks[0].interrupts[0].value
                    approval_id = str(uuid.uuid4())

                    # Deep Agents 格式: {action_requests, review_configs}
                    action_requests = interrupt_value.get("action_requests", [])
                    review_configs = interrupt_value.get("review_configs", [])

                    if action_requests:
                        for action in action_requests:
                            await db.execute(
                                "INSERT INTO agent_approvals (id, conversation_id, tool_name, tool_input, risk_level, description) "
                                "VALUES (?, ?, ?, ?, ?, ?)",
                                (
                                    approval_id, conversation_id,
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
                                "approval_id": approval_id,
                                "conversation_id": conversation_id,
                                "actions": action_requests,
                                "review_configs": review_configs,
                            }, ensure_ascii=False),
                        }
                    else:
                        # 兼容旧格式 interrupt
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


# ─── 审批 ───

@router.get("/approvals")
async def list_approvals(user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, conversation_id, created_at, tool_name, tool_input, risk_level, description, status "
        "FROM agent_approvals WHERE status = 'pending' ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "conversation_id": r[1], "created_at": r[2], "tool_name": r[3],
         "tool_input": r[4], "risk_level": r[5], "description": r[6], "status": r[7]}
        for r in rows
    ]


@router.post("/approvals/{approval_id}")
async def resolve_approval(approval_id: str, body: ApprovalAction, user=Depends(require_role("admin"))):
    """批准或拒绝待审批操作"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT conversation_id, status FROM agent_approvals WHERE id = ?", (approval_id,)
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "审批记录不存在")
    if row[1] != "pending":
        raise HTTPException(400, "该审批已处理")

    conversation_id = row[0]
    await db.execute(
        "UPDATE agent_approvals SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
        (body.action + "d", datetime.now().isoformat(), user["username"], approval_id),
    )
    await db.commit()

    try:
        from modules.agents.deep_agent import build_agent
        agent = await build_agent(safety_mode="supervised")
        config = {"configurable": {"thread_id": conversation_id}}

        # Deep Agents 使用 decisions 列表恢复
        decision = {"type": body.action}  # "approve" or "reject"
        result = await agent.ainvoke(
            Command(resume={"decisions": [decision]}),
            config=config,
        )

        final_content = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                final_content = msg.content
                break

        return {"ok": True, "action": body.action + "d", "result": final_content[:1000]}
    except Exception as e:
        logger.error(f"Resume failed: {e}")
        return {"ok": False, "error": str(e)}


# ─── 对话历史 ───

@router.get("/conversations")
async def list_conversations(user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, title, username, safety_mode, created_at, updated_at, message_count "
        "FROM agent_conversations WHERE is_archived = 0 ORDER BY updated_at DESC LIMIT 50"
    )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "title": r[1], "username": r[2], "safety_mode": r[3],
         "created_at": r[4], "updated_at": r[5], "message_count": r[6]}
        for r in rows
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user=Depends(require_role("admin"))):
    try:
        from modules.agents.deep_agent import build_agent
        agent = await build_agent()
        config = {"configurable": {"thread_id": conversation_id}}
        snapshot = await agent.aget_state(config)

        messages = []
        for msg in snapshot.values.get("messages", []):
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                if msg.content:
                    messages.append({"role": "assistant", "content": msg.content})
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        messages.append({"role": "tool_call", "tool": tc["name"], "args": tc["args"]})
            elif isinstance(msg, ToolMessage):
                messages.append({"role": "tool_result", "content": msg.content[:500] if msg.content else ""})

        todos = snapshot.values.get("todos", [])
        return {"conversation_id": conversation_id, "messages": messages, "todos": todos}
    except Exception as e:
        return {"conversation_id": conversation_id, "messages": [], "todos": [], "error": str(e)}


@router.delete("/conversations/{conversation_id}")
async def archive_conversation(conversation_id: str, user=Depends(require_role("admin"))):
    db = await get_db()
    await db.execute("UPDATE agent_conversations SET is_archived = 1 WHERE id = ?", (conversation_id,))
    await db.commit()
    return {"ok": True}


# ─── 巡检 ───

@router.get("/patrols")
async def list_patrols(user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, display_name, description, interval_minutes, enabled, last_run, last_status, last_report, check_tools, prompt "
        "FROM agent_patrol_tasks ORDER BY id"
    )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "display_name": r[1], "description": r[2], "interval_minutes": r[3],
         "enabled": bool(r[4]), "last_run": r[5], "last_status": r[6],
         "last_report": (r[7] or "")[:500], "check_tools": r[8] or "", "prompt": r[9] or ""}
        for r in rows
    ]


@router.put("/patrols/{patrol_id}")
async def update_patrol(patrol_id: str, body: PatrolUpdate, user=Depends(require_role("admin"))):
    db = await get_db()
    sets, vals = [], []
    if body.enabled is not None:
        sets.append("enabled = ?")
        vals.append(1 if body.enabled else 0)
    if body.interval_minutes is not None:
        sets.append("interval_minutes = ?")
        vals.append(body.interval_minutes)
    if body.prompt is not None:
        sets.append("prompt = ?")
        vals.append(body.prompt)
    if body.check_tools is not None:
        sets.append("check_tools = ?")
        vals.append(body.check_tools)
    if not sets:
        raise HTTPException(400, "没有要更新的字段")
    vals.append(patrol_id)
    await db.execute(f"UPDATE agent_patrol_tasks SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()
    return {"ok": True}


@router.post("/patrols/{patrol_id}/run")
async def trigger_patrol(patrol_id: str, user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute("SELECT * FROM agent_patrol_tasks WHERE id = ?", (patrol_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "巡检任务不存在")

    task_dict = {"id": row[0], "display_name": row[1], "description": row[2], "prompt": row[5]}
    from modules.agents.patrol import execute_patrol
    asyncio.create_task(execute_patrol(task_dict))
    return {"ok": True, "message": f"巡检 {row[1]} 已触发"}


@router.get("/patrols/{patrol_id}/history")
async def get_patrol_history(patrol_id: str, limit: int = 20, user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, status, report, duration_seconds "
        "FROM agent_patrol_history WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
        (patrol_id, limit),
    )
    rows = await cursor.fetchall()
    return [{"timestamp": r[0], "status": r[1], "report": (r[2] or "")[:1000], "duration": r[3]} for r in rows]


# ─── 事件 ───

@router.get("/events")
async def list_events(limit: int = 50, user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, event_type, tool_name, tool_input, risk_level, username, details "
        "FROM agent_events ORDER BY timestamp DESC LIMIT ?", (limit,),
    )
    rows = await cursor.fetchall()
    return [
        {"timestamp": r[0], "event_type": r[1], "tool_name": r[2], "tool_input": r[3],
         "risk_level": r[4], "username": r[5], "details": r[6]}
        for r in rows
    ]


# ─── 配置 ───

@router.get("/settings")
async def get_agent_settings(user=Depends(require_role("admin"))):
    from config import settings
    from modules.agents.llm import get_provider_status
    return {
        "default_model": settings.agent_default_model,
        "patrol_model": settings.agent_patrol_model,
        "shell_timeout": settings.agent_shell_timeout,
        "shell_max_output": settings.agent_shell_max_output,
        "providers": get_provider_status(),
    }


@router.put("/settings")
async def update_agent_settings(request: Request, user=Depends(require_role("admin"))):
    from config import settings, BASE_DIR
    body = await request.json()

    changed = []
    if "default_model" in body:
        settings.agent_default_model = body["default_model"]
        changed.append(f"SERVERHUB_AGENT_MODEL={body['default_model']}")
    if "patrol_model" in body:
        settings.agent_patrol_model = body["patrol_model"]
        changed.append(f"SERVERHUB_PATROL_MODEL={body['patrol_model']}")

    if changed:
        env_path = BASE_DIR / ".env"
        try:
            lines = env_path.read_text().splitlines() if env_path.exists() else []
            for kv in changed:
                key = kv.split("=", 1)[0]
                found = False
                for i, line in enumerate(lines):
                    if line.startswith(key + "="):
                        lines[i] = kv
                        found = True
                        break
                if not found:
                    lines.append(kv)
            env_path.write_text("\n".join(lines) + "\n")
        except Exception:
            pass

        from modules.agents.deep_agent import reset_agent_cache
        reset_agent_cache()

    return {"ok": True, "default_model": settings.agent_default_model, "patrol_model": settings.agent_patrol_model}


@router.post("/settings/refresh-models/{provider_id}")
async def refresh_provider_models(provider_id: str, user=Depends(require_role("admin"))):
    import os, httpx
    from modules.agents.llm import PROVIDERS

    if provider_id not in PROVIDERS:
        raise HTTPException(404, f"未知服务商: {provider_id}")

    provider = PROVIDERS[provider_id]

    if provider_id == "openrouter":
        api_key = os.getenv(provider.get("api_key_env", ""), "")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
                resp.raise_for_status()
                data = resp.json()
            models = [{"id": m["id"], "name": m.get("name", m["id"])}
                      for m in data.get("data", []) if m.get("id") and ":free" not in m["id"]]
            models.sort(key=lambda x: x["name"])
            provider["default_models"] = models[:200]
            return {"ok": True, "count": len(models[:200]), "models": models[:20]}
        except Exception as e:
            raise HTTPException(500, f"刷新失败: {str(e)}")

    elif provider_id == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("http://localhost:11434/api/tags")
                data = resp.json()
            models = [{"id": m["name"], "name": m["name"]} for m in data.get("models", [])]
            provider["default_models"] = models
            return {"ok": True, "count": len(models), "models": models}
        except Exception as e:
            raise HTTPException(500, f"Ollama 连接失败: {str(e)}")

    return {"ok": False, "message": f"服务商 {provider_id} 不支持动态刷新"}


@router.put("/settings/api-key/{provider_id}")
async def update_provider_api_key(provider_id: str, request: Request, user=Depends(require_role("admin"))):
    import os
    from config import BASE_DIR
    from modules.agents.llm import PROVIDERS

    if provider_id not in PROVIDERS:
        raise HTTPException(404, f"未知服务商: {provider_id}")

    body = await request.json()
    api_key = body.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(400, "API Key 不能为空")

    provider = PROVIDERS[provider_id]
    env_var = provider.get("api_key_env", "")
    if not env_var:
        raise HTTPException(400, f"服务商 {provider_id} 不需要 API Key")

    os.environ[env_var] = api_key

    env_path = BASE_DIR / ".env"
    try:
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        kv = f"{env_var}={api_key}"
        found = False
        for i, line in enumerate(lines):
            if line.startswith(env_var + "="):
                lines[i] = kv
                found = True
                break
        if not found:
            lines.append(kv)
        env_path.write_text("\n".join(lines) + "\n")
    except Exception as e:
        raise HTTPException(500, f"写入 .env 失败: {str(e)}")

    from modules.agents.deep_agent import reset_agent_cache
    reset_agent_cache()
    return {"ok": True, "provider": provider_id, "env_var": env_var}


# ─── Agent 管理 API ───

@router.get("/admin/prompt")
async def get_prompt(user=Depends(require_role("admin"))):
    """获取当前系统提示词"""
    from modules.agents.prompts import SYSTEM_PROMPT
    from pathlib import Path
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_prompt.txt"
    is_custom = custom_path.exists()
    content = custom_path.read_text(encoding="utf-8") if is_custom else SYSTEM_PROMPT
    return {"content": content, "is_custom": is_custom}


@router.put("/admin/prompt")
async def update_prompt(request: Request, user=Depends(require_role("admin"))):
    """保存自定义系统提示词"""
    from pathlib import Path
    from config import settings
    body = await request.json()
    content = body.get("content", "")
    custom_path = Path(settings.db_path).parent / "custom_prompt.txt"
    if body.get("reset"):
        custom_path.unlink(missing_ok=True)
        from modules.agents.deep_agent import reset_agent_cache
        reset_agent_cache()
        return {"ok": True, "message": "已重置为默认提示词"}
    custom_path.write_text(content, encoding="utf-8")
    from modules.agents.deep_agent import reset_agent_cache
    reset_agent_cache()
    return {"ok": True, "message": "提示词已保存"}


@router.get("/admin/subagents")
async def list_subagents(user=Depends(require_role("admin"))):
    """获取所有 SubAgent 配置 + 可用工具列表"""
    from modules.agents.subagents import get_subagents_config, get_available_tools
    from modules.agents.llm import get_provider_status
    return {
        "subagents": get_subagents_config(),
        "available_tools": get_available_tools(),
        "providers": get_provider_status(),
    }


@router.put("/admin/subagents")
async def save_subagents(request: Request, user=Depends(require_role("admin"))):
    """保存全部 SubAgent 配置"""
    from modules.agents.subagents import save_subagents_config
    body = await request.json()
    configs = body.get("subagents", [])
    if body.get("reset"):
        from pathlib import Path
        from config import settings
        custom_path = Path(settings.db_path).parent / "custom_subagents.json"
        custom_path.unlink(missing_ok=True)
        from modules.agents.deep_agent import reset_agent_cache
        reset_agent_cache()
        return {"ok": True, "message": "已重置为默认 SubAgent"}
    save_subagents_config(configs)
    from modules.agents.deep_agent import reset_agent_cache
    reset_agent_cache()
    return {"ok": True, "message": f"已保存 {len(configs)} 个 SubAgent"}


@router.get("/admin/memory")
async def get_memory(user=Depends(require_role("admin"))):
    """获取 AGENTS.md 记忆文件内容"""
    from config import BASE_DIR
    memory_path = BASE_DIR / "AGENTS.md"
    content = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    return {"content": content, "path": str(memory_path)}


@router.put("/admin/memory")
async def update_memory(request: Request, user=Depends(require_role("admin"))):
    """保存 AGENTS.md 记忆文件"""
    from config import BASE_DIR
    body = await request.json()
    content = body.get("content", "")
    memory_path = BASE_DIR / "AGENTS.md"
    memory_path.write_text(content, encoding="utf-8")
    from modules.agents.deep_agent import reset_agent_cache
    reset_agent_cache()
    return {"ok": True, "message": "记忆已保存"}


# ─── WebSocket 终端 ───

@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    """WebSocket 驱动的 PTY 终端"""
    await websocket.accept()

    from modules.agents.terminal import WebTerminal
    terminal = WebTerminal()
    terminal.spawn()

    try:
        async def read_terminal():
            """持续读取终端输出并发送到 WebSocket"""
            while terminal.is_alive():
                data = terminal.read()
                if data:
                    await websocket.send_text(data)
                else:
                    await asyncio.sleep(0.05)

        async def write_terminal():
            """接收 WebSocket 输入并写入终端"""
            while True:
                data = await websocket.receive_text()
                # 支持 resize 消息
                if data.startswith("\x1b[resize:"):
                    try:
                        parts = data.split(":")[1].rstrip("]").split(",")
                        cols, rows = int(parts[0]), int(parts[1])
                        terminal.resize(cols, rows)
                    except Exception:
                        pass
                else:
                    terminal.write(data)

        await asyncio.gather(read_terminal(), write_terminal())

    except WebSocketDisconnect:
        logger.info("Terminal WebSocket disconnected")
    except Exception as e:
        logger.error(f"Terminal error: {e}")
    finally:
        terminal.close()

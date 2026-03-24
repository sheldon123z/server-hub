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

from auth.dependencies import get_current_user, require_role
from database import get_db
from modules.agents.schemas import ChatRequest, ApprovalAction, PatrolUpdate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["AI Agent"])


# ─── 对话 ───

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
                    # 记录工具结果事件
                    try:
                        await db.execute(
                            "INSERT INTO agent_events (conversation_id, event_type, tool_name, tool_output, username) "
                            "VALUES (?, 'tool_result', ?, ?, ?)",
                            (conversation_id, getattr(last, "name", ""),
                             (last.content[:500] if last.content else ""), user["username"]),
                        )
                    except Exception:
                        pass

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
async def list_conversations(user=Depends(get_current_user)):
    db = await get_db()
    if user["role"] == "admin":
        cursor = await db.execute(
            "SELECT id, title, username, safety_mode, created_at, updated_at, message_count "
            "FROM agent_conversations WHERE is_archived = 0 ORDER BY updated_at DESC LIMIT 50"
        )
    else:
        cursor = await db.execute(
            "SELECT id, title, username, safety_mode, created_at, updated_at, message_count "
            "FROM agent_conversations WHERE is_archived = 0 AND username = ? ORDER BY updated_at DESC LIMIT 50",
            (user["username"],),
        )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "title": r[1], "username": r[2], "safety_mode": r[3],
         "created_at": r[4], "updated_at": r[5], "message_count": r[6]}
        for r in rows
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user=Depends(get_current_user)):
    # 非管理员验证对话归属
    if user["role"] != "admin":
        db = await get_db()
        cursor = await db.execute(
            "SELECT username FROM agent_conversations WHERE id = ?", (conversation_id,)
        )
        row = await cursor.fetchone()
        if not row or row[0] != user["username"]:
            raise HTTPException(403, "无权查看此对话")
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
async def archive_conversation(conversation_id: str, user=Depends(get_current_user)):
    db = await get_db()
    # 非管理员验证对话归属
    if user["role"] != "admin":
        cursor = await db.execute(
            "SELECT username FROM agent_conversations WHERE id = ?", (conversation_id,)
        )
        row = await cursor.fetchone()
        if not row or row[0] != user["username"]:
            raise HTTPException(403, "无权操作此对话")
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
    asyncio.create_task(execute_patrol(task_dict, triggered_by=user["username"]))
    return {"ok": True, "message": f"巡检 {row[1]} 已触发"}


@router.get("/patrols/{patrol_id}/history")
async def get_patrol_history(patrol_id: str, limit: int = 20, user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, status, report, duration_seconds, report_json "
        "FROM agent_patrol_history WHERE task_id = ? ORDER BY timestamp DESC LIMIT ?",
        (patrol_id, limit),
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        item = {"timestamp": r[0], "status": r[1], "report": (r[2] or "")[:1000], "duration": r[3]}
        if r[4]:
            try:
                item["report_json"] = json.loads(r[4])
            except (json.JSONDecodeError, TypeError):
                pass
        results.append(item)
    return results


@router.get("/patrols/{patrol_id}/report/{history_id}")
async def get_patrol_report(patrol_id: str, history_id: int, user=Depends(require_role("admin"))):
    """获取单次巡检的完整结构化报告"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, status, report, report_json, duration_seconds "
        "FROM agent_patrol_history WHERE id = ? AND task_id = ?",
        (history_id, patrol_id),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "巡检记录不存在")
    result = {
        "timestamp": row[0], "status": row[1],
        "report": row[2], "duration": row[4],
    }
    if row[3]:
        try:
            result["report_json"] = json.loads(row[3])
        except (json.JSONDecodeError, TypeError):
            pass
    return result


# ─── 巡检模板 ───

@router.get("/templates")
async def list_templates(category: str = "", user=Depends(require_role("admin"))):
    """列出所有巡检模板"""
    db = await get_db()
    if category:
        cursor = await db.execute(
            "SELECT id, name, category, description, check_tools, prompt_template, variables, is_builtin "
            "FROM patrol_templates WHERE category = ? ORDER BY name", (category,),
        )
    else:
        cursor = await db.execute(
            "SELECT id, name, category, description, check_tools, prompt_template, variables, is_builtin "
            "FROM patrol_templates ORDER BY category, name"
        )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        item = {
            "id": r[0], "name": r[1], "category": r[2], "description": r[3],
            "check_tools": r[4], "prompt_template": r[5], "is_builtin": bool(r[7]),
        }
        try:
            item["variables"] = json.loads(r[6]) if r[6] else []
        except (json.JSONDecodeError, TypeError):
            item["variables"] = []
        results.append(item)
    return results


@router.post("/templates")
async def create_template(request: Request, user=Depends(require_role("admin"))):
    """创建自定义巡检模板"""
    body = await request.json()
    for field in ("id", "name", "check_tools", "prompt_template"):
        if field not in body:
            raise HTTPException(400, f"缺少必填字段: {field}")

    db = await get_db()
    existing = await db.execute("SELECT id FROM patrol_templates WHERE id = ?", (body["id"],))
    if await existing.fetchone():
        raise HTTPException(409, f"模板 ID 已存在: {body['id']}")

    variables = body.get("variables", [])
    if isinstance(variables, list):
        variables = json.dumps(variables, ensure_ascii=False)

    await db.execute(
        "INSERT INTO patrol_templates (id, name, category, description, check_tools, prompt_template, variables, is_builtin) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
        (body["id"], body["name"], body.get("category", "general"), body.get("description", ""),
         body["check_tools"], body["prompt_template"], variables),
    )
    await db.commit()
    return {"ok": True, "id": body["id"]}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, user=Depends(require_role("admin"))):
    """删除自定义巡检模板（内置模板不可删除）"""
    db = await get_db()
    cursor = await db.execute("SELECT is_builtin FROM patrol_templates WHERE id = ?", (template_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "模板不存在")
    if row[0]:
        raise HTTPException(403, "内置模板不可删除")
    await db.execute("DELETE FROM patrol_templates WHERE id = ?", (template_id,))
    await db.commit()
    return {"ok": True}


@router.post("/patrols/from-template")
async def create_patrol_from_template(request: Request, user=Depends(require_role("admin"))):
    """从模板创建巡检任务"""
    body = await request.json()
    template_id = body.get("template_id")
    if not template_id:
        raise HTTPException(400, "缺少 template_id")

    db = await get_db()
    cursor = await db.execute(
        "SELECT name, description, check_tools, prompt_template, variables FROM patrol_templates WHERE id = ?",
        (template_id,),
    )
    tpl = await cursor.fetchone()
    if not tpl:
        raise HTTPException(404, f"模板不存在: {template_id}")

    # 用传入的变量值替换 prompt 模板中的占位符
    prompt = tpl[3]
    variables = body.get("variables", {})
    if variables:
        try:
            prompt = prompt.format(**variables)
        except KeyError:
            pass  # 缺少变量时保留原占位符

    patrol_id = body.get("id") or f"custom_{template_id}_{int(datetime.now().timestamp())}"
    display_name = body.get("display_name") or tpl[0]
    interval = body.get("interval_minutes", 60)

    # 检查 ID 是否重复
    existing = await db.execute("SELECT id FROM agent_patrol_tasks WHERE id = ?", (patrol_id,))
    if await existing.fetchone():
        raise HTTPException(409, f"巡检任务 ID 已存在: {patrol_id}")

    await db.execute(
        "INSERT INTO agent_patrol_tasks (id, display_name, description, interval_minutes, check_tools, prompt) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (patrol_id, display_name, tpl[1] or "", interval, tpl[2], prompt),
    )
    await db.commit()
    return {"ok": True, "id": patrol_id, "display_name": display_name}


# ─── 故障报告 ───

@router.get("/fault-reports")
async def list_fault_reports(limit: int = 20, status: str = "", user=Depends(require_role("admin"))):
    """获取故障报告列表"""
    db = await get_db()
    if status:
        cursor = await db.execute(
            "SELECT id, detected_at, source, severity, root_cause, status FROM fault_reports "
            "WHERE status = ? ORDER BY detected_at DESC LIMIT ?", (status, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT id, detected_at, source, severity, root_cause, status FROM fault_reports "
            "ORDER BY detected_at DESC LIMIT ?", (limit,),
        )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "detected_at": r[1], "source": r[2], "severity": r[3],
         "root_cause": (r[4] or "")[:200], "status": r[5]}
        for r in rows
    ]


@router.get("/fault-reports/{report_id}")
async def get_fault_report(report_id: str, user=Depends(require_role("admin"))):
    """获取故障报告详情"""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM fault_reports WHERE id = ?", (report_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "报告不存在")
    cols = [d[0] for d in cursor.description]
    result = dict(zip(cols, row))
    # 解析 JSON 字段
    for field in ("affected_components", "symptoms", "evidence", "immediate_actions", "long_term_solutions", "similar_cases"):
        if result.get(field):
            try:
                result[field] = json.loads(result[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return result


@router.put("/fault-reports/{report_id}/resolve")
async def resolve_fault_report(report_id: str, user=Depends(require_role("admin"))):
    """标记故障报告为已解决"""
    db = await get_db()
    await db.execute(
        "UPDATE fault_reports SET status = 'resolved', resolved_at = ? WHERE id = ?",
        (datetime.now().isoformat(), report_id),
    )
    await db.commit()
    return {"ok": True}


# ─── 告警规则 ───

@router.get("/alerts/rules")
async def list_alert_rules(user=Depends(require_role("admin"))):
    """获取所有告警规则"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, metric, operator, warning_threshold, critical_threshold, "
        "cooldown_minutes, notify, enabled FROM alert_rules ORDER BY id"
    )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "name": r[1], "metric": r[2], "operator": r[3],
         "warning_threshold": r[4], "critical_threshold": r[5],
         "cooldown_minutes": r[6], "notify": bool(r[7]), "enabled": bool(r[8])}
        for r in rows
    ]


@router.put("/alerts/rules/{rule_id}")
async def update_alert_rule(rule_id: str, request: Request, user=Depends(require_role("admin"))):
    """更新告警规则"""
    db = await get_db()
    body = await request.json()
    sets, vals = [], []
    for field in ("name", "metric", "operator", "warning_threshold", "critical_threshold", "cooldown_minutes"):
        if field in body:
            sets.append(f"{field} = ?")
            vals.append(body[field])
    if "notify" in body:
        sets.append("notify = ?")
        vals.append(1 if body["notify"] else 0)
    if "enabled" in body:
        sets.append("enabled = ?")
        vals.append(1 if body["enabled"] else 0)
    if not sets:
        raise HTTPException(400, "没有要更新的字段")
    vals.append(rule_id)
    await db.execute(f"UPDATE alert_rules SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()
    return {"ok": True}


@router.post("/alerts/rules")
async def create_alert_rule(request: Request, user=Depends(require_role("admin"))):
    """创建自定义告警规则"""
    body = await request.json()
    required = ("id", "name", "metric")
    for field in required:
        if field not in body:
            raise HTTPException(400, f"缺少必填字段: {field}")
    db = await get_db()
    existing = await db.execute("SELECT id FROM alert_rules WHERE id = ?", (body["id"],))
    if await existing.fetchone():
        raise HTTPException(409, f"规则 ID 已存在: {body['id']}")
    await db.execute(
        "INSERT INTO alert_rules (id, name, metric, operator, warning_threshold, critical_threshold, cooldown_minutes, notify) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (body["id"], body["name"], body["metric"], body.get("operator", ">"),
         body.get("warning_threshold"), body.get("critical_threshold"),
         body.get("cooldown_minutes", 60), 1 if body.get("notify", True) else 0),
    )
    await db.commit()
    return {"ok": True, "id": body["id"]}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str, user=Depends(require_role("admin"))):
    """删除告警规则"""
    db = await get_db()
    await db.execute("DELETE FROM alert_rules WHERE id = ?", (rule_id,))
    await db.commit()
    return {"ok": True}


@router.get("/alerts/history")
async def list_alert_history(limit: int = 50, user=Depends(require_role("admin"))):
    """获取告警历史"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT ah.id, ah.rule_id, ar.name, ah.severity, ah.current_value, ah.message, ah.notified, ah.created_at "
        "FROM alert_history ah LEFT JOIN alert_rules ar ON ah.rule_id = ar.id "
        "ORDER BY ah.created_at DESC LIMIT ?", (limit,),
    )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "rule_id": r[1], "rule_name": r[2] or r[1], "severity": r[3],
         "current_value": r[4], "message": r[5], "notified": bool(r[6]), "created_at": r[7]}
        for r in rows
    ]


# ─── 案例库 ───

@router.get("/fault-cases")
async def list_fault_cases(q: str = "", category: str = "", limit: int = 30, user=Depends(require_role("admin"))):
    """搜索或列出故障案例"""
    db = await get_db()
    if q:
        like = f"%{q}%"
        cursor = await db.execute(
            "SELECT id, title, category, symptoms, root_cause, solution, tags, source, created_at "
            "FROM fault_cases WHERE title LIKE ? OR symptoms LIKE ? OR root_cause LIKE ? OR tags LIKE ? "
            "ORDER BY created_at DESC LIMIT ?",
            (like, like, like, like, limit),
        )
    elif category:
        cursor = await db.execute(
            "SELECT id, title, category, symptoms, root_cause, solution, tags, source, created_at "
            "FROM fault_cases WHERE category = ? ORDER BY created_at DESC LIMIT ?",
            (category, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT id, title, category, symptoms, root_cause, solution, tags, source, created_at "
            "FROM fault_cases ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "title": r[1], "category": r[2], "symptoms": (r[3] or "")[:200],
         "root_cause": (r[4] or "")[:200], "solution": (r[5] or "")[:200],
         "tags": r[6], "source": r[7], "created_at": r[8]}
        for r in rows
    ]


@router.post("/fault-cases")
async def create_fault_case(request: Request, user=Depends(require_role("admin"))):
    """手动录入故障案例"""
    body = await request.json()
    if not body.get("title"):
        raise HTTPException(400, "缺少标题")
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO fault_cases (title, category, symptoms, root_cause, solution, tags, source) "
        "VALUES (?, ?, ?, ?, ?, ?, 'manual')",
        (body["title"], body.get("category", ""), body.get("symptoms", ""),
         body.get("root_cause", ""), body.get("solution", ""), body.get("tags", "")),
    )
    case_id = cursor.lastrowid
    # 更新 FTS5
    try:
        await db.execute(
            "INSERT INTO fault_cases_fts(rowid, title, symptoms, root_cause, solution, tags) VALUES (?, ?, ?, ?, ?, ?)",
            (case_id, body["title"], body.get("symptoms", ""), body.get("root_cause", ""),
             body.get("solution", ""), body.get("tags", "")),
        )
    except Exception:
        pass
    await db.commit()
    return {"ok": True, "id": case_id}


@router.delete("/fault-cases/{case_id}")
async def delete_fault_case(case_id: int, user=Depends(require_role("admin"))):
    """删除故障案例"""
    db = await get_db()
    await db.execute("DELETE FROM fault_cases WHERE id = ?", (case_id,))
    try:
        await db.execute("DELETE FROM fault_cases_fts WHERE rowid = ?", (case_id,))
    except Exception:
        pass
    await db.commit()
    return {"ok": True}


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
        except Exception as e:
            logger.error(f".env 写入失败，设置未持久化: {e}")

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
    """WebSocket 驱动的 PTY 终端（仅管理员）"""
    # 手动验证 JWT（WebSocket 不支持 Depends）
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4001, reason="未认证")
        return
    try:
        from auth.jwt_handler import verify_token
        from auth.user_store import get_user_by_name
        payload = verify_token(token)
        if not payload or payload.get("type") != "access":
            await websocket.close(code=4001, reason="认证失败")
            return
        user = await get_user_by_name(payload["sub"])
        if not user or user.get("disabled") or user["role"] != "admin":
            await websocket.close(code=4003, reason="权限不足")
            return
    except Exception:
        await websocket.close(code=4001, reason="认证失败")
        return
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

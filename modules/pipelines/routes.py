"""Pipeline 编排引擎 API 路由"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sse_starlette.sse import EventSourceResponse

from auth.dependencies import get_current_user, require_role
from database import get_db
from modules.pipelines.executor import (
    approve_run,
    cancel_run,
    get_run_event_queue,
    publish_chat_event,
    reject_run,
    retry_from_step,
    start_run,
)
from modules.pipelines.services import (
    create_pipeline,
    delete_pipeline,
    generate_mermaid,
    get_pipeline,
    get_pipeline_run,
    get_pipeline_stats,
    get_run_step_logs,
    list_pipeline_runs,
    list_pipelines,
    update_pipeline,
    validate_pipeline_yaml,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pipelines", tags=["Pipeline 编排"])


# ---------------------------------------------------------------------------
# Pipeline 定义管理
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
async def api_list_pipelines(
    enabled: bool | None = Query(default=None),
    user=Depends(get_current_user),
):
    """获取 Pipeline 列表"""
    items = await list_pipelines(enabled=enabled)
    return items


@router.post("", status_code=201)
@router.post("/", status_code=201)
async def api_create_pipeline(
    request: Request,
    user=Depends(require_role("admin")),
):
    """创建 Pipeline（提交 YAML）"""
    body = await request.json()
    yaml_content = body.get("yaml_content")
    if not yaml_content:
        raise HTTPException(400, "缺少 yaml_content 字段")
    try:
        result = await create_pipeline(yaml_content, created_by=user["username"])
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, **result}


@router.get("/stats")
async def api_pipeline_stats(
    pipeline_id: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    user=Depends(get_current_user),
):
    """获取 Pipeline 统计数据"""
    return await get_pipeline_stats(pipeline_id=pipeline_id, days=days)


# --- runs 路由必须在 /{pipeline_id} 之前注册，避免被路径参数吞掉 ---


@router.get("/runs")
@router.get("/runs/")
async def api_list_runs(
    pipeline_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    user=Depends(get_current_user),
):
    """获取 Pipeline 运行列表"""
    return await list_pipeline_runs(pipeline_id=pipeline_id, status=status, limit=limit)


@router.get("/runs/{run_id}")
async def api_get_run(
    run_id: str,
    user=Depends(get_current_user),
):
    """获取单次运行详情"""
    run = await get_pipeline_run(run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    return run


@router.post("/runs/{run_id}/cancel")
async def api_cancel_run(
    run_id: str,
    user=Depends(require_role("admin")),
):
    """取消正在执行的 Pipeline"""
    run = await get_pipeline_run(run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    if run["status"] not in ("pending", "running", "paused"):
        raise HTTPException(400, f"当前状态 '{run['status']}' 不可取消")

    await cancel_run(run_id)
    return {"ok": True, "run_id": run_id}


@router.post("/runs/{run_id}/approve")
async def api_approve_run(
    run_id: str,
    user=Depends(require_role("admin")),
):
    """审批通过（当 Pipeline 暂停在 approval 节点时）"""
    run = await get_pipeline_run(run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    if run["status"] != "paused":
        raise HTTPException(400, f"当前状态 '{run['status']}' 不在等待审批")

    await approve_run(run_id, approved_by=user["username"])
    return {"ok": True, "run_id": run_id}


@router.post("/runs/{run_id}/reject")
async def api_reject_run(
    run_id: str,
    user=Depends(require_role("admin")),
):
    """审批拒绝"""
    run = await get_pipeline_run(run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    if run["status"] != "paused":
        raise HTTPException(400, f"当前状态 '{run['status']}' 不在等待审批")

    await reject_run(run_id, rejected_by=user["username"])
    return {"ok": True, "run_id": run_id}


@router.post("/runs/{run_id}/retry-from/{step_id}")
async def api_retry_from_step(
    run_id: str,
    step_id: str,
    user=Depends(require_role("admin")),
):
    """从失败的 step 处重试"""
    run = await get_pipeline_run(run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    if run["status"] not in ("failed", "cancelled"):
        raise HTTPException(400, f"当前状态 '{run['status']}' 不可重试")

    try:
        new_run = await retry_from_step(run_id, step_id, triggered_by=user["username"])
        return {"ok": True, **new_run}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/runs/{run_id}/logs")
async def api_get_run_logs(
    run_id: str,
    user=Depends(get_current_user),
):
    """获取运行的 step 执行日志"""
    run = await get_pipeline_run(run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    logs = await get_run_step_logs(run_id)
    return logs


@router.get("/runs/{run_id}/stream")
async def api_stream_run(
    run_id: str,
    user=Depends(get_current_user),
):
    """SSE 实时推送 Pipeline 运行进度"""
    run = await get_pipeline_run(run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")

    async def _event_generator():
        """从执行引擎的事件队列读取事件并推送。"""
        # 获取执行引擎的事件队列
        event_queue: asyncio.Queue | None = get_run_event_queue(run_id)

        if event_queue:
            # 有执行引擎 — 从队列读取实时事件
            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=30)
                    yield {
                        "event": event.get("type", "message"),
                        "data": json.dumps(event, ensure_ascii=False),
                    }
                    if event.get("type") in ("pipeline_complete", "error"):
                        break
                except TimeoutError:
                    # 发送心跳保持连接
                    yield {"event": "ping", "data": ""}
        else:
            # 执行引擎不可用 — 轮询数据库状态
            last_status = None
            last_step_count = 0
            for _ in range(600):  # 最多轮询 10 分钟
                current_run = await get_pipeline_run(run_id)
                if not current_run:
                    yield {
                        "event": "error",
                        "data": json.dumps({"error": "运行记录不存在"}, ensure_ascii=False),
                    }
                    break

                current_status = current_run["status"]
                step_logs = await get_run_step_logs(run_id)

                # 推送新增的 step 日志
                if len(step_logs) > last_step_count:
                    for log in step_logs[last_step_count:]:
                        event_type = "step_complete" if log["status"] in ("completed", "failed") else "step_start"
                        yield {
                            "event": event_type,
                            "data": json.dumps(log, ensure_ascii=False),
                        }
                    last_step_count = len(step_logs)

                # 状态变更
                if current_status != last_status:
                    last_status = current_status
                    if current_status in ("completed", "failed", "cancelled"):
                        yield {
                            "event": "pipeline_complete",
                            "data": json.dumps(
                                {
                                    "run_id": run_id,
                                    "status": current_status,
                                    "summary": current_run.get("summary"),
                                },
                                ensure_ascii=False,
                            ),
                        }
                        break
                    if current_status == "paused":
                        yield {
                            "event": "approval_required",
                            "data": json.dumps(
                                {
                                    "run_id": run_id,
                                    "step_id": current_run.get("current_step_id"),
                                },
                                ensure_ascii=False,
                            ),
                        }

                await asyncio.sleep(1)

    return EventSourceResponse(_event_generator())


# ---------------------------------------------------------------------------
# Pipeline 定义路由（含路径参数，必须在 /runs 之后注册）
# ---------------------------------------------------------------------------


@router.get("/{pipeline_id}")
async def api_get_pipeline(
    pipeline_id: str,
    user=Depends(get_current_user),
):
    """获取 Pipeline 详情"""
    pipeline = await get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline 不存在")
    return pipeline


@router.put("/{pipeline_id}")
async def api_update_pipeline(
    pipeline_id: str,
    request: Request,
    user=Depends(require_role("admin")),
):
    """更新 Pipeline YAML"""
    body = await request.json()
    yaml_content = body.get("yaml_content")
    if not yaml_content:
        raise HTTPException(400, "缺少 yaml_content 字段")
    try:
        result = await update_pipeline(pipeline_id, yaml_content)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True, **result}


@router.delete("/{pipeline_id}")
async def api_delete_pipeline(
    pipeline_id: str,
    user=Depends(require_role("admin")),
):
    """删除 Pipeline"""
    ok = await delete_pipeline(pipeline_id)
    if not ok:
        raise HTTPException(404, "Pipeline 不存在")
    return {"ok": True}


@router.post("/{pipeline_id}/validate")
async def api_validate_pipeline(
    pipeline_id: str,
    request: Request,
    user=Depends(get_current_user),
):
    """验证 Pipeline YAML（不保存）"""
    body = await request.json()
    yaml_content = body.get("yaml_content")
    if not yaml_content:
        # 如果没传 yaml_content，使用已保存的
        pipeline = await get_pipeline(pipeline_id)
        if not pipeline:
            raise HTTPException(404, "Pipeline 不存在")
        yaml_content = pipeline["yaml_content"]
    return await validate_pipeline_yaml(yaml_content)


@router.get("/{pipeline_id}/mermaid")
async def api_get_mermaid(
    pipeline_id: str,
    user=Depends(get_current_user),
):
    """返回 Mermaid 流程图代码"""
    pipeline = await get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline 不存在")
    mermaid_code = generate_mermaid(pipeline)
    return {"mermaid": mermaid_code}


@router.post("/{pipeline_id}/run")
async def api_trigger_run(
    pipeline_id: str,
    request: Request,
    user=Depends(require_role("admin")),
):
    """触发 Pipeline 执行"""
    pipeline = await get_pipeline(pipeline_id)
    if not pipeline:
        raise HTTPException(404, "Pipeline 不存在")
    if not pipeline["enabled"]:
        raise HTTPException(400, "Pipeline 未启用")

    body = await request.json() if await request.body() else {}
    params = body.get("params", {})

    # 并发检查
    running_runs = await list_pipeline_runs(pipeline_id=pipeline_id, status="running")
    max_concurrent = pipeline.get("max_concurrent_runs", 1)
    if len(running_runs) >= max_concurrent:
        raise HTTPException(
            409,
            f"已达最大并发数 ({max_concurrent})，请等待当前运行完成",
        )

    try:
        run = await start_run(
            pipeline_id=pipeline_id,
            params=params,
            triggered_by=user["username"],
            trigger_type="manual",
        )
        return {"ok": True, **run}
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------------------
# P3-A: Pipeline AI 执行面板
# ---------------------------------------------------------------------------


# Per-run chat 锁，防止并发请求破坏对话历史
_chat_locks: dict[str, asyncio.Lock] = {}


def _get_chat_lock(run_id: str) -> asyncio.Lock:
    if run_id not in _chat_locks:
        _chat_locks[run_id] = asyncio.Lock()
    return _chat_locks[run_id]


async def _build_run_context(run_id: str) -> dict:
    """构建 Pipeline 运行上下文快照（注入到 PipelineAgent 提示词）"""
    db = await get_db()

    run = await db.execute_fetchone(
        "SELECT id, pipeline_id, status, current_step_id, error, params_json FROM pipeline_runs WHERE id = ?",
        (run_id,),
    )
    if not run:
        return {}

    pipeline = await db.execute_fetchone(
        "SELECT name, display_name, description FROM pipelines WHERE id = ?",
        (run["pipeline_id"],),
    )

    rows = await db.execute_fetchall(
        "SELECT step_id, step_type, status, duration_ms, error "
        "FROM pipeline_step_logs WHERE run_id = ? ORDER BY started_at",
        (run_id,),
    )
    step_lines = []
    for r in rows:
        status_icon = {"completed": "✓", "failed": "✗", "running": "▶"}.get(r["status"], "○")
        dur = f" ({r['duration_ms']}ms)" if r["duration_ms"] else ""
        err = f" — {r['error'][:100]}" if r["error"] else ""
        step_lines.append(f"  {status_icon} [{r['step_type']}] {r['step_id']}{dur}{err}")

    step_context = "\n".join(step_lines) if step_lines else "暂无步骤执行记录"

    return {
        "pipeline_name": pipeline["display_name"] if pipeline else run["pipeline_id"],
        "task_description": pipeline["description"] if pipeline else "",
        "step_context": f"当前状态: {run['status']}\n已执行步骤:\n{step_context}",
    }


@router.post("/runs/{run_id}/chat")
async def api_pipeline_chat(
    run_id: str,
    request: Request,
    user=Depends(require_role("admin")),
):
    """用户在 Pipeline 执行面板中提问 — 启动后台 Agent 任务，事件进 /stream"""
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(400, "消息不能为空")

    db = await get_db()
    run = await db.execute_fetchone(
        "SELECT id, chat_thread_id FROM pipeline_runs WHERE id = ?",
        (run_id,),
    )
    if not run:
        raise HTTPException(404, "运行实例不存在")

    chat_thread_id = run["chat_thread_id"] or f"pipeline-chat-{run_id}"
    if not run["chat_thread_id"]:
        await db.execute(
            "UPDATE pipeline_runs SET chat_thread_id = ? WHERE id = ?",
            (chat_thread_id, run_id),
        )
        await db.commit()

    task = asyncio.ensure_future(_run_pipeline_chat(run_id, chat_thread_id, message))
    task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    return {"ok": True, "message": "已接收，AI 正在思考"}


async def _run_pipeline_chat(run_id: str, thread_id: str, message: str):
    """后台运行 PipelineAgent，产出事件 publish 到 Pipeline SSE 通道"""
    from modules.pipelines.pipeline_agent import (
        cleanup_pipeline_agent,
        create_pipeline_agent,
    )

    lock = _get_chat_lock(run_id)
    async with lock:
        checkpointer = None
        msg_id = str(uuid.uuid4())

        try:
            await publish_chat_event(
                run_id,
                "chat_message",
                {"final": True},
                message_id=msg_id,
                role="user",
                content=message,
            )

            context = await _build_run_context(run_id)
            agent, invoke_config, checkpointer = await create_pipeline_agent(
                run_id,
                context,
                thread_id,
                purpose="patrol",
            )

            ai_msg_id = str(uuid.uuid4())
            accumulated_content = ""

            async for event in agent.astream(
                {"messages": [("user", message)]},
                config=invoke_config,
            ):
                messages = event.get("messages", [])
                for msg in messages:
                    role = getattr(msg, "type", None)

                    if role == "ai":
                        content = getattr(msg, "content", "")
                        if isinstance(content, list):
                            content = "".join(item.get("text", "") for item in content if isinstance(item, dict))

                        tool_calls = getattr(msg, "tool_calls", [])
                        for tc in tool_calls:
                            tc_id = str(uuid.uuid4())
                            await publish_chat_event(
                                run_id,
                                "chat_tool_call",
                                {"tool": tc.get("name", ""), "args": tc.get("args", {})},
                                message_id=ai_msg_id,
                                tool_call_id=tc_id,
                            )

                        if content and content != accumulated_content:
                            accumulated_content = content
                            await publish_chat_event(
                                run_id,
                                "chat_message",
                                {"final": False},
                                message_id=ai_msg_id,
                                role="assistant",
                                content=content,
                            )

                    elif role == "tool":
                        tool_name = getattr(msg, "name", "")
                        tool_content = getattr(msg, "content", "")
                        await publish_chat_event(
                            run_id,
                            "chat_tool_result",
                            {"tool": tool_name},
                            tool_call_id=getattr(msg, "tool_call_id", None),
                            content=tool_content,
                        )

            if accumulated_content:
                await publish_chat_event(
                    run_id,
                    "chat_message",
                    {"final": True},
                    message_id=ai_msg_id,
                    role="assistant",
                    content=accumulated_content,
                )

        except Exception as e:
            logger.exception("Pipeline chat 执行失败: %s", e)
            await publish_chat_event(
                run_id,
                "chat_message",
                {"final": True},
                message_id=str(uuid.uuid4()),
                role="assistant",
                content=f"抱歉，处理失败: {e}",
            )
        finally:
            await cleanup_pipeline_agent(checkpointer)


@router.get("/runs/{run_id}/chat-events")
async def api_get_chat_events(
    run_id: str,
    after_seq: int = 0,
    limit: int = 100,
    user=Depends(require_role("admin")),
):
    """获取 Pipeline 运行的 AI 对话事件历史（分页 + 断线续传）"""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM pipeline_chat_events WHERE run_id = ? AND seq > ? ORDER BY seq LIMIT ?",
        (run_id, after_seq, limit),
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# P3-B/C 占位端点（返回 501）
# ---------------------------------------------------------------------------


@router.post("/runs/{run_id}/decide")
async def api_pipeline_decide(
    run_id: str,
    request: Request,
    user=Depends(require_role("admin")),
):
    """P3-B: 人类决策响应 — 原子 CAS 解析"""
    body = await request.json()
    step_id = body.get("step_id")
    decision_request_id = body.get("decision_request_id")
    option_id = body.get("option_id")

    if not all([step_id, decision_request_id, option_id]):
        raise HTTPException(400, "缺少 step_id / decision_request_id / option_id")

    db = await get_db()
    # Compare-and-swap: 只有 waiting_decision 状态才能解析
    cursor = await db.execute(
        """UPDATE pipeline_step_logs
           SET status = 'decided',
               output_json = ?,
               completed_at = datetime('now')
           WHERE run_id = ? AND step_id = ? AND status = 'waiting_decision'""",
        (
            json.dumps(
                {
                    "chosen_option_id": option_id,
                    "decided_by": user.get("username", "admin"),
                    "decision_request_id": decision_request_id,
                },
                ensure_ascii=False,
            ),
            run_id,
            step_id,
        ),
    )
    await db.commit()

    if cursor.rowcount == 0:
        # 检查是否已决策（幂等）
        existing = await db.execute_fetchone(
            "SELECT output_json FROM pipeline_step_logs WHERE run_id = ? AND step_id = ? AND status = 'decided'",
            (run_id, step_id),
        )
        if existing:
            return {"ok": True, "already_decided": True, **json.loads(existing["output_json"])}
        raise HTTPException(409, "决策请求已过期或不存在")

    # 发布 decision_resolved 事件
    await publish_chat_event(
        run_id,
        "decision_resolved",
        {"decided_by": user.get("username", "admin"), "decision_request_id": decision_request_id},
        step_id=step_id,
        content=option_id,
    )

    return {"ok": True, "option_id": option_id}


@router.post("/ai/generate")
async def api_ai_generate(request: Request, user=Depends(require_role("admin"))):
    """P3-C: AI 生成工作流 — 尚未实现"""
    raise HTTPException(501, "AI 工作流生成将在 P3-C 中实现")


@router.post("/ai/modify")
async def api_ai_modify(request: Request, user=Depends(require_role("admin"))):
    """P3-C: AI 修改工作流 — 尚未实现"""
    raise HTTPException(501, "AI 工作流修改将在 P3-C 中实现")


@router.post("/ai/review")
async def api_ai_review(request: Request, user=Depends(require_role("admin"))):
    """P3-C: AI 审查工作流 — 尚未实现"""
    raise HTTPException(501, "AI 工作流审查将在 P3-C 中实现")

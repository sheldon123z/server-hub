"""Pipeline 运行管理器 — 触发、执行、取消、审批、重试"""

import asyncio
import contextlib
import json
import logging
import time
import uuid
from datetime import datetime

from database import get_db
from modules.pipelines.security import escape_for_shell, redact_sensitive
from modules.pipelines.steps import get_step_executor, load_all_steps

logger = logging.getLogger(__name__)

# 活跃运行任务 {run_id: asyncio.Task}
_active_runs: dict[str, asyncio.Task] = {}

# SSE 事件队列 {run_id: list[asyncio.Queue]}
_sse_subscribers: dict[str, list[asyncio.Queue]] = {}


def _ensure_steps_loaded():
    """确保 step 执行器已加载"""
    from modules.pipelines.steps import _STEP_REGISTRY

    if not _STEP_REGISTRY:
        load_all_steps()


async def start_pipeline_run(
    pipeline_id: str,
    params: dict | None = None,
    trigger_type: str = "manual",
    started_by: str = "system",
) -> str:
    """创建并启动 Pipeline 运行实例

    Returns: run_id
    """
    _ensure_steps_loaded()
    db = await get_db()

    # 获取 Pipeline 定义
    row = await (
        await db.execute(
            "SELECT id, yaml_content, steps_json, params_json, version, max_concurrent_runs, timeout, enabled "
            "FROM pipelines WHERE id = ?",
            (pipeline_id,),
        )
    ).fetchone()
    if not row:
        raise ValueError(f"Pipeline 不存在: {pipeline_id}")

    _pid, _yaml_content, steps_json, _params_json, version, max_concurrent, timeout, enabled = row
    if not enabled:
        raise ValueError(f"Pipeline 未启用: {pipeline_id}")

    # 检查并发限制
    max_concurrent = max_concurrent or 1
    active_count_row = await (
        await db.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE pipeline_id = ? AND status IN ('running', 'pending', 'paused')",
            (pipeline_id,),
        )
    ).fetchone()
    active_count = active_count_row[0] if active_count_row else 0
    if active_count >= max_concurrent:
        raise ValueError(f"Pipeline 并发运行数已达上限 ({active_count}/{max_concurrent})")

    # 解析 steps
    steps = json.loads(steps_json) if steps_json else []
    if not steps:
        raise ValueError("Pipeline 没有定义任何步骤")

    # 创建 run 记录
    run_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    await db.execute(
        """INSERT INTO pipeline_runs
           (id, pipeline_id, pipeline_version, status, params_json, current_step_id,
            steps_state_json, trigger_type, started_at, started_by)
           VALUES (?, ?, ?, 'running', ?, ?, '{}', ?, ?, ?)""",
        (run_id, pipeline_id, version, json.dumps(params or {}), steps[0].get("id", ""), trigger_type, now, started_by),
    )
    await db.commit()

    # 启动异步执行任务
    task = asyncio.create_task(_execute_pipeline(run_id, pipeline_id, steps, params or {}, timeout or 3600))
    _active_runs[run_id] = task

    # 任务完成后清理
    def _cleanup(t):
        _active_runs.pop(run_id, None)
        _sse_subscribers.pop(run_id, None)

    task.add_done_callback(_cleanup)

    logger.info("Pipeline 运行已启动: run_id=%s, pipeline_id=%s, trigger=%s", run_id, pipeline_id, trigger_type)
    return run_id


async def cancel_pipeline_run(run_id: str) -> bool:
    """取消正在运行的 Pipeline"""
    task = _active_runs.get(run_id)
    if task and not task.done():
        task.cancel()
        _active_runs.pop(run_id, None)

    db = await get_db()
    await db.execute(
        "UPDATE pipeline_runs SET status = 'cancelled', completed_at = datetime('now') WHERE id = ? AND status IN ('running', 'paused', 'pending')",
        (run_id,),
    )
    await db.commit()
    await _publish_sse(run_id, "pipeline_complete", {"run_id": run_id, "status": "cancelled"})
    logger.info("Pipeline 运行已取消: %s", run_id)
    return True


async def approve_pipeline_step(run_id: str, step_id: str, approved: bool) -> dict:
    """审批操作 — 恢复被暂停的 Pipeline"""
    db = await get_db()

    # 更新审批记录
    status = "approved" if approved else "rejected"
    await db.execute(
        "UPDATE pipeline_step_logs SET status = ?, completed_at = datetime('now') WHERE run_id = ? AND step_id = ? AND status = 'waiting_approval'",
        (status, run_id, step_id),
    )
    await db.commit()

    if not approved:
        # 拒绝 → Pipeline 失败
        await db.execute(
            "UPDATE pipeline_runs SET status = 'failed', error = '审批被拒绝', completed_at = datetime('now') WHERE id = ?",
            (run_id,),
        )
        await db.commit()
        await _publish_sse(run_id, "pipeline_complete", {"run_id": run_id, "status": "failed", "error": "审批被拒绝"})
        return {"ok": True, "action": "rejected"}

    # 通过 → 通过 SSE 事件通知执行循环继续
    await _publish_sse(run_id, "approval_resolved", {"step_id": step_id, "approved": True})
    return {"ok": True, "action": "approved"}


async def retry_from_step(run_id: str, step_id: str) -> str:
    """从失败步骤重试 — 创建新 run 继承之前的状态"""
    db = await get_db()
    row = await (
        await db.execute(
            "SELECT pipeline_id, params_json, steps_state_json, started_by FROM pipeline_runs WHERE id = ?",
            (run_id,),
        )
    ).fetchone()
    if not row:
        raise ValueError(f"运行记录不存在: {run_id}")

    pipeline_id, params_json, _steps_state_json, started_by = row
    params = json.loads(params_json) if params_json else {}

    # 从原来的步骤状态开始新的运行
    new_run_id = await start_pipeline_run(
        pipeline_id=pipeline_id,
        params=params,
        trigger_type="retry",
        started_by=started_by or "system",
    )
    return new_run_id


def subscribe_sse(run_id: str) -> asyncio.Queue:
    """订阅运行的 SSE 事件"""
    if run_id not in _sse_subscribers:
        _sse_subscribers[run_id] = []
    queue: asyncio.Queue = asyncio.Queue()
    _sse_subscribers[run_id].append(queue)
    return queue


def unsubscribe_sse(run_id: str, queue: asyncio.Queue):
    """取消 SSE 订阅"""
    if run_id in _sse_subscribers:
        with contextlib.suppress(ValueError):
            _sse_subscribers[run_id].remove(queue)


# routes.py 调用的公开别名
get_run_event_queue = subscribe_sse

# Per-run 事件序列号计数器
_run_seq_counters: dict[str, int] = {}


def _next_seq(run_id: str) -> int:
    """获取 run 的下一个递增序列号"""
    seq = _run_seq_counters.get(run_id, 0) + 1
    _run_seq_counters[run_id] = seq
    return seq


async def _publish_sse(run_id: str, event_type: str, data: dict):
    """向所有订阅者发布 SSE 事件（含 event_id + seq 用于去重/回放）"""
    subscribers = _sse_subscribers.get(run_id, [])
    event = {
        "type": event_type,
        "event_id": str(uuid.uuid4()),
        "seq": _next_seq(run_id),
        "timestamp": time.time(),
        **data,
    }
    for queue in subscribers:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("SSE 队列已满，丢弃事件: %s", event_type)


async def publish_chat_event(
    run_id: str,
    event_type: str,
    data: dict,
    *,
    step_id: str | None = None,
    message_id: str | None = None,
    tool_call_id: str | None = None,
    role: str | None = None,
    content: str | None = None,
):
    """发布聊天事件：同时写入 pipeline_chat_events 表 + 广播 SSE"""
    event_id = str(uuid.uuid4())
    seq = _next_seq(run_id)

    # 持久化到数据库
    try:
        db = await get_db()
        await db.execute(
            """INSERT INTO pipeline_chat_events
               (run_id, event_id, seq, event_type, step_id, message_id, tool_call_id, role, content, metadata_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id,
                event_id,
                seq,
                event_type,
                step_id,
                message_id,
                tool_call_id,
                role,
                content,
                json.dumps(
                    {k: v for k, v in data.items() if k not in ("role", "content")}, ensure_ascii=False, default=str
                ),
            ),
        )
        await db.commit()
    except Exception:
        logger.exception("持久化 chat event 失败: %s", event_type)

    # 广播 SSE（不再走 _publish_sse 以避免 seq 重复）
    subscribers = _sse_subscribers.get(run_id, [])
    event = {
        "type": event_type,
        "event_id": event_id,
        "seq": seq,
        "timestamp": time.time(),
        "step_id": step_id,
        "message_id": message_id,
        "tool_call_id": tool_call_id,
        "role": role,
        "content": content,
        **{k: v for k, v in data.items() if k not in ("role", "content")},
    }
    for queue in subscribers:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("SSE 队列已满，丢弃 chat event: %s", event_type)


async def _execute_pipeline(
    run_id: str,
    pipeline_id: str,
    steps: list[dict],
    params: dict,
    total_timeout: int,
):
    """内部执行循环 — 按序执行所有 step"""
    db = await get_db()
    step_outputs: dict = {}
    state = {"run_id": run_id, "pipeline_id": pipeline_id, "params": params, "step_outputs": step_outputs}
    start_time = time.monotonic()

    try:
        i = 0
        while i < len(steps):
            # 检查全局超时
            elapsed = time.monotonic() - start_time
            if elapsed > total_timeout:
                raise TimeoutError(f"Pipeline 全局超时 ({total_timeout}s)")

            step = steps[i]
            step_id = step.get("id", f"step-{i}")
            step_type = step.get("type", "")
            step_name = step.get("name", step_id)

            # 更新当前步骤
            await db.execute("UPDATE pipeline_runs SET current_step_id = ? WHERE id = ?", (step_id, run_id))
            await db.commit()

            # 发布 step_start 事件
            await _publish_sse(
                run_id, "step_start", {"step_id": step_id, "step_name": step_name, "step_type": step_type}
            )

            # 记录 step 开始
            step_start = time.monotonic()
            await _log_step_execution(run_id, step_id, step_type, "running", input_data=step)

            # ── Parallel Step: 真正并行执行 branches ──
            if step_type == "parallel":
                branches = step.get("branches") or step.get("params", {}).get("branches", [])
                if not branches:
                    result = {"output": "无分支定义", "branch_count": 0}
                    duration_ms = int((time.monotonic() - step_start) * 1000)
                    step_outputs[step_id] = result
                    state["step_outputs"] = step_outputs
                    await _log_step_execution(
                        run_id, step_id, step_type, "completed", output_data=result, duration_ms=duration_ms
                    )
                    await _publish_sse(
                        run_id, "step_complete", {"step_id": step_id, "status": "completed", "duration_ms": duration_ms}
                    )
                    i += 1
                    continue

                async def _run_branch(branch: dict, branch_idx: int, _parent_id: str = step_id) -> tuple[str, dict]:
                    bid = branch.get("id", f"branch-{branch_idx}")
                    btype = branch.get("type", "shell")
                    bname = branch.get("name", bid)
                    await _publish_sse(
                        run_id,
                        "step_start",
                        {"step_id": bid, "step_name": bname, "step_type": btype, "parent": _parent_id},
                    )
                    b_start = time.monotonic()
                    await _log_step_execution(run_id, bid, btype, "running", input_data=branch)
                    try:
                        branch_executor = get_step_executor(btype)
                        resolved = _resolve_template_vars(branch, state)
                        res = await branch_executor.execute(resolved, state)
                    except Exception as exc:
                        res = {"output": "", "error": str(exc)}
                    b_dur = int((time.monotonic() - b_start) * 1000)
                    b_status = "failed" if res.get("error") else "completed"
                    await _log_step_execution(run_id, bid, btype, b_status, output_data=res, duration_ms=b_dur)
                    evt = "step_complete" if b_status == "completed" else "step_failed"
                    await _publish_sse(run_id, evt, {"step_id": bid, "status": b_status, "duration_ms": b_dur})
                    return bid, res

                branch_tasks = [_run_branch(b, idx) for idx, b in enumerate(branches)]
                branch_results = await asyncio.gather(*branch_tasks, return_exceptions=True)

                merged: dict = {}
                all_success = True
                for br in branch_results:
                    if isinstance(br, BaseException):
                        all_success = False
                        merged[f"error-{id(br)}"] = {"error": str(br)}
                    else:
                        bid, res = br
                        merged[bid] = res
                        if res.get("error"):
                            all_success = False

                result = {"output": merged, "all_success": all_success, "branch_count": len(branches)}
                duration_ms = int((time.monotonic() - step_start) * 1000)
                step_outputs[step_id] = result
                state["step_outputs"] = step_outputs
                p_status = "completed" if all_success else "failed"
                await _log_step_execution(
                    run_id, step_id, step_type, p_status, output_data=result, duration_ms=duration_ms
                )

                if not all_success and step.get("on_failure", "abort") == "abort":
                    raise RuntimeError(f"Parallel step {step_id} 中有分支失败")

                await _publish_sse(
                    run_id, "step_complete", {"step_id": step_id, "status": p_status, "duration_ms": duration_ms}
                )
                i += 1
                continue

            # ── 普通步骤执行（带重试）──
            retry_count = int(step.get("retry_count", 0))
            retry_delay = int(step.get("retry_delay", 5))

            for attempt in range(retry_count + 1):
                try:
                    executor = get_step_executor(step_type)
                    resolved_config = _resolve_template_vars(step, state)
                    result = await executor.execute(resolved_config, state)
                except Exception as e:
                    result = {"output": "", "error": str(e)}

                if not result.get("error"):
                    break  # 成功

                if attempt < retry_count:
                    logger.info(
                        "Step %s 第 %d/%d 次重试，等待 %ds",
                        step_id,
                        attempt + 1,
                        retry_count,
                        retry_delay,
                    )
                    await _publish_sse(
                        run_id,
                        "step_retry",
                        {
                            "step_id": step_id,
                            "attempt": attempt + 1,
                            "max_retries": retry_count,
                            "delay": retry_delay,
                        },
                    )
                    await asyncio.sleep(retry_delay)

            duration_ms = int((time.monotonic() - step_start) * 1000)

            # 处理审批中断
            if result.get("requires_approval"):
                await _log_step_execution(
                    run_id, step_id, step_type, "waiting_approval", output_data=result, duration_ms=duration_ms
                )
                await db.execute("UPDATE pipeline_runs SET status = 'paused' WHERE id = ?", (run_id,))
                await db.commit()
                await _publish_sse(
                    run_id,
                    "approval_required",
                    {
                        "step_id": step_id,
                        "assignee": result.get("assignee", "admin"),
                        "timeout": result.get("timeout", 3600),
                    },
                )
                # 等待审批（通过 SSE 事件队列）
                approved = await _wait_for_approval(run_id, step_id, result.get("timeout", 3600))
                if not approved:
                    raise RuntimeError(f"审批被拒绝或超时: {step_id}")
                await db.execute("UPDATE pipeline_runs SET status = 'running' WHERE id = ?", (run_id,))
                await db.commit()
                duration_ms = int((time.monotonic() - step_start) * 1000)

            # 检查执行结果
            has_error = bool(result.get("error"))
            step_status = "failed" if has_error else "completed"
            step_outputs[step_id] = result
            state["step_outputs"] = step_outputs

            await _log_step_execution(
                run_id, step_id, step_type, step_status, output_data=result, duration_ms=duration_ms
            )

            # 发布 step 完成/失败事件
            if has_error:
                on_failure = step.get("on_failure", "abort")
                await _publish_sse(
                    run_id,
                    "step_failed",
                    {"step_id": step_id, "error": result.get("error", ""), "on_failure_action": on_failure},
                )
                # 处理 on_failure 策略
                if on_failure == "abort":
                    raise RuntimeError(f"Step {step_id} 失败: {result.get('error')}")
                elif on_failure == "skip":
                    logger.warning("Step %s 失败，跳过继续", step_id)
                elif on_failure == "notify_continue":
                    logger.warning("Step %s 失败，发送通知并继续", step_id)
                    try:
                        from modules.notifications.services import send_notification

                        await send_notification(f"Pipeline step {step_name} 失败: {result.get('error', '未知错误')}")
                    except Exception:
                        logger.exception("on_failure 通知发送失败")
                elif on_failure.startswith("goto:"):
                    target = on_failure.split(":", 1)[1]
                    # 跳转到指定 step
                    target_idx = next((j for j, s in enumerate(steps) if s.get("id") == target), None)
                    if target_idx is not None:
                        i = target_idx
                        continue
                    logger.error("goto 目标 step 不存在: %s", target)
                    raise RuntimeError(f"goto 目标不存在: {target}")
            else:
                await _publish_sse(
                    run_id,
                    "step_complete",
                    {"step_id": step_id, "status": "completed", "duration_ms": duration_ms},
                )

            # 条件分支：如果是 condition step，跳转到指定分支
            if step_type == "condition" and result.get("branch"):
                target = result["branch"]
                target_idx = next((j for j, s in enumerate(steps) if s.get("id") == target), None)
                if target_idx is not None:
                    i = target_idx
                    continue
                # 分支目标不存在，继续下一步
                logger.warning("条件分支目标 %s 不存在，继续顺序执行", target)

            i += 1

        # 所有步骤完成
        total_duration = int((time.monotonic() - start_time) * 1000)
        await db.execute(
            "UPDATE pipeline_runs SET status = 'completed', completed_at = datetime('now'), steps_state_json = ? WHERE id = ?",
            (json.dumps(step_outputs, ensure_ascii=False, default=str), run_id),
        )
        await db.commit()
        await _publish_sse(
            run_id,
            "pipeline_complete",
            {"run_id": run_id, "status": "completed", "total_duration": total_duration},
        )
        logger.info("Pipeline 运行完成: %s (耗时 %dms)", run_id, total_duration)
        _run_seq_counters.pop(run_id, None)

    except asyncio.CancelledError:
        logger.info("Pipeline 运行被取消: %s", run_id)
        await db.execute(
            "UPDATE pipeline_runs SET status = 'cancelled', completed_at = datetime('now') WHERE id = ?",
            (run_id,),
        )
        await db.commit()
        _run_seq_counters.pop(run_id, None)

    except Exception as e:
        error_msg = str(e)
        logger.exception("Pipeline 运行失败: %s", run_id)
        await db.execute(
            "UPDATE pipeline_runs SET status = 'failed', error = ?, completed_at = datetime('now'), steps_state_json = ? WHERE id = ?",
            (error_msg[:1000], json.dumps(step_outputs, ensure_ascii=False, default=str), run_id),
        )
        await db.commit()
        await _publish_sse(run_id, "pipeline_complete", {"run_id": run_id, "status": "failed", "error": error_msg})
        _run_seq_counters.pop(run_id, None)


async def _wait_for_approval(run_id: str, step_id: str, approval_timeout: int) -> bool:
    """等待审批结果（通过轮询数据库状态）"""
    db = await get_db()
    deadline = time.monotonic() + approval_timeout
    while time.monotonic() < deadline:
        row = await (
            await db.execute(
                "SELECT status FROM pipeline_step_logs WHERE run_id = ? AND step_id = ? ORDER BY id DESC LIMIT 1",
                (run_id, step_id),
            )
        ).fetchone()
        if row:
            if row[0] == "approved":
                return True
            if row[0] == "rejected":
                return False
        await asyncio.sleep(2)
    # 超时
    return False


async def _log_step_execution(
    run_id: str,
    step_id: str,
    step_type: str,
    status: str,
    *,
    input_data: dict | None = None,
    output_data: dict | None = None,
    duration_ms: int | None = None,
    error: str | None = None,
):
    """写入 pipeline_step_logs"""
    db = await get_db()
    try:
        if status == "running":
            await db.execute(
                """INSERT INTO pipeline_step_logs (run_id, step_id, step_type, status, input_json, started_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (
                    run_id,
                    step_id,
                    step_type,
                    status,
                    json.dumps(redact_sensitive(input_data), ensure_ascii=False, default=str) if input_data else None,
                ),
            )
        else:
            await db.execute(
                """UPDATE pipeline_step_logs
                   SET status = ?, output_json = ?, duration_ms = ?, error = ?, completed_at = datetime('now')
                   WHERE run_id = ? AND step_id = ? AND status = 'running'""",
                (
                    status,
                    json.dumps(
                        redact_sensitive(output_data) if isinstance(output_data, dict) else output_data,
                        ensure_ascii=False,
                        default=str,
                    )
                    if output_data
                    else None,
                    duration_ms,
                    error or (output_data.get("error") if output_data else None),
                    run_id,
                    step_id,
                ),
            )
        await db.commit()
    except Exception:
        logger.debug("写入 step 日志失败", exc_info=True)


def _resolve_template_vars(step_config: dict, state: dict) -> dict:
    """解析模板变量: {{params.x}}, {{steps.y.output}}, {{run.id}}"""
    import re

    params = state.get("params", {})
    step_outputs = state.get("step_outputs", {})
    run_id = state.get("run_id", "")

    _shell_context = False

    def _replace(match):
        expr = match.group(1).strip()
        parts = expr.split(".")

        if not parts:
            return match.group(0)

        result: str | None = None

        if parts[0] == "params" and len(parts) >= 2:
            val = params
            for p in parts[1:]:
                if isinstance(val, dict):
                    val = val.get(p, "")
                else:
                    return match.group(0)
            result = str(val) if val is not None else ""

        elif parts[0] == "steps" and len(parts) >= 3:
            sid = parts[1]
            step_out = step_outputs.get(sid, {})
            val = step_out
            for p in parts[2:]:
                if isinstance(val, dict):
                    val = val.get(p, "")
                else:
                    return match.group(0)
            result = str(val) if val is not None else ""

        elif parts[0] == "run":
            if len(parts) >= 2 and parts[1] == "id":
                result = run_id
            elif len(parts) >= 2 and parts[1] == "started_at":
                result = state.get("started_at", "")

        if result is None:
            return match.group(0)

        return escape_for_shell(result) if _shell_context else result

    pattern = re.compile(r"\{\{(.*?)\}\}")

    def _resolve_value(v, *, in_shell_context: bool = False):
        nonlocal _shell_context
        if isinstance(v, str):
            old_ctx = _shell_context
            _shell_context = in_shell_context
            resolved = pattern.sub(_replace, v)
            _shell_context = old_ctx
            return resolved
        if isinstance(v, dict):
            return {k: _resolve_value(val, in_shell_context=(k == "command")) for k, val in v.items()}
        if isinstance(v, list):
            return [_resolve_value(item, in_shell_context=in_shell_context) for item in v]
        return v

    return _resolve_value(step_config)

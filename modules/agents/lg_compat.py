"""LangGraph 兼容 API Server — 为 AsyncSubAgentMiddleware 提供后端

实现 langgraph_sdk 客户端所需的 5 个 HTTP 端点，使框架原生的
AsyncSubAgentMiddleware 能在本地 FastAPI 部署中正常工作，无需
LangSmith Deployments 或 langgraph-cli。

端点:
    POST   /lg/threads                          — 创建 thread
    POST   /lg/threads/{thread_id}/runs         — 在 thread 上启动 run
    GET    /lg/threads/{thread_id}/runs/{run_id} — 查询 run 状态
    GET    /lg/threads/{thread_id}              — 获取 thread 状态(含结果)
    POST   /lg/threads/{thread_id}/runs/{run_id}/cancel — 取消 run
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)

lg_router = APIRouter(prefix="/lg", tags=["LG Compat"])

# ─── 状态存储 ───


@dataclass
class ThreadData:
    thread_id: str
    created_at: str
    updated_at: str
    metadata: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)
    status: str = "idle"
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


@dataclass
class RunData:
    run_id: str
    thread_id: str
    assistant_id: str
    status: str = "pending"
    created_at: str = ""
    updated_at: str = ""
    metadata: dict = field(default_factory=dict)
    multitask_strategy: str = "reject"
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


_threads: dict[str, ThreadData] = {}
_runs: dict[str, RunData] = {}
_graphs: dict[str, object] = {}  # graph_id → compiled LangGraph graph


def register_graph(graph_id: str, graph) -> None:
    """注册一个编译好的 graph 供异步执行"""
    _graphs[graph_id] = graph
    logger.info("LG Compat: 已注册 graph '%s'", graph_id)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _thread_to_dict(t: ThreadData) -> dict:
    """序列化 ThreadData 为 SDK 期望的 Thread JSON"""
    return {
        "thread_id": t.thread_id,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
        "metadata": t.metadata,
        "status": t.status,
        "values": t.values,
        "interrupts": {},
    }


def _run_to_dict(r: RunData) -> dict:
    """序列化 RunData 为 SDK 期望的 Run JSON"""
    d = {
        "run_id": r.run_id,
        "thread_id": r.thread_id,
        "assistant_id": r.assistant_id,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        "status": r.status,
        "metadata": r.metadata,
        "multitask_strategy": r.multitask_strategy,
    }
    if r.error:
        d["error"] = r.error
    return d


# ─── Graph 执行 ───


async def _execute_graph(run: RunData, thread: ThreadData, input_data: dict):
    """在后台执行 graph，更新 run 和 thread 状态"""
    graph = _graphs.get(run.assistant_id)
    if not graph:
        run.status = "error"
        run.error = f"Graph '{run.assistant_id}' not registered"
        run.updated_at = _now_iso()
        return

    run.status = "running"
    run.updated_at = _now_iso()

    try:
        config = {"configurable": {"thread_id": run.thread_id}}
        result = await asyncio.wait_for(
            graph.ainvoke(input_data, config),
            timeout=300,
        )

        messages = result.get("messages", [])
        async with thread.lock:
            existing = thread.values.get("messages", [])
            # 将结果消息追加到 thread 的 values 中
            for msg in messages:
                if hasattr(msg, "dict"):
                    existing.append(msg.dict())
                elif isinstance(msg, dict):
                    existing.append(msg)
                else:
                    existing.append({"role": "assistant", "content": str(msg)})
            thread.values["messages"] = existing
            thread.updated_at = _now_iso()
            thread.status = "idle"

        run.status = "success"
        run.updated_at = _now_iso()
        logger.info("LG Compat: run %s 完成 (graph=%s)", run.run_id, run.assistant_id)

    except TimeoutError:
        run.status = "error"
        run.error = "Execution timed out (300s limit)"
        run.updated_at = _now_iso()
        async with thread.lock:
            thread.status = "idle"
        logger.warning("LG Compat: run %s 超时", run.run_id)

    except asyncio.CancelledError:
        run.status = "cancelled"
        run.updated_at = _now_iso()
        async with thread.lock:
            thread.status = "idle"
        logger.info("LG Compat: run %s 已取消", run.run_id)

    except Exception as e:
        run.status = "error"
        run.error = str(e)[:2000]
        run.updated_at = _now_iso()
        async with thread.lock:
            thread.status = "idle"
        logger.error("LG Compat: run %s 失败: %s", run.run_id, e)


# ─── HTTP 端点 ───


@lg_router.post("/threads")
async def create_thread(request: Request):
    """创建 thread — SDK: client.threads.create()"""
    body = await request.json() if await request.body() else {}
    thread_id = body.get("thread_id") or str(uuid.uuid4())
    now = _now_iso()

    thread = ThreadData(
        thread_id=thread_id,
        created_at=now,
        updated_at=now,
        metadata=body.get("metadata") or {},
        values={},
        status="idle",
    )
    _threads[thread_id] = thread
    return _thread_to_dict(thread)


@lg_router.post("/threads/{thread_id}/runs")
async def create_run(thread_id: str, request: Request):
    """创建 run — SDK: client.runs.create()

    接受 assistant_id 和 input，启动后台 graph 执行，立即返回。
    """
    thread = _threads.get(thread_id)
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")

    body = await request.json()
    assistant_id = body.get("assistant_id")
    if not assistant_id:
        raise HTTPException(400, "assistant_id is required")
    if assistant_id not in _graphs:
        raise HTTPException(404, f"Graph '{assistant_id}' not registered")

    input_data = body.get("input") or {}
    multitask_strategy = body.get("multitask_strategy", "reject")

    # interrupt 策略: 取消该 thread 上正在运行的 run
    if multitask_strategy == "interrupt":
        for _rid, existing_run in list(_runs.items()):
            if existing_run.thread_id == thread_id and existing_run.status == "running":
                if existing_run.task and not existing_run.task.done():
                    existing_run.task.cancel()
                existing_run.status = "interrupted"
                existing_run.updated_at = _now_iso()

    now = _now_iso()
    run = RunData(
        run_id=str(uuid.uuid4()),
        thread_id=thread_id,
        assistant_id=assistant_id,
        status="pending",
        created_at=now,
        updated_at=now,
        metadata=body.get("metadata") or {},
        multitask_strategy=multitask_strategy,
    )
    _runs[run.run_id] = run

    # 合并 input messages 到 thread values
    input_messages = input_data.get("messages", [])
    async with thread.lock:
        existing = thread.values.get("messages", [])
        existing.extend(input_messages)
        thread.values["messages"] = existing
        thread.status = "busy"

    # 启动后台执行
    run.task = asyncio.create_task(
        _execute_graph(run, thread, input_data),
        name=f"lg-run-{run.run_id[:8]}",
    )

    return _run_to_dict(run)


@lg_router.get("/threads/{thread_id}/runs/{run_id}")
async def get_run(thread_id: str, run_id: str):
    """查询 run 状态 — SDK: client.runs.get()"""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")
    if run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not on thread '{thread_id}'")

    # 同步 asyncio.Task 状态
    if run.task and run.task.done() and run.status in ("pending", "running"):
        try:
            run.task.result()
        except asyncio.CancelledError:
            run.status = "cancelled"
        except Exception as e:
            run.status = "error"
            run.error = str(e)[:2000]
        run.updated_at = _now_iso()

    return _run_to_dict(run)


@lg_router.get("/threads/{thread_id}")
async def get_thread(thread_id: str):
    """获取 thread 状态 — SDK: client.threads.get()

    AsyncSubAgentMiddleware 的 check_async_task 用此获取最终结果:
    result 在 thread.values.messages[-1]
    """
    thread = _threads.get(thread_id)
    if not thread:
        raise HTTPException(404, f"Thread '{thread_id}' not found")
    return _thread_to_dict(thread)


@lg_router.post("/threads/{thread_id}/runs/{run_id}/cancel")
async def cancel_run(thread_id: str, run_id: str):
    """取消 run — SDK: client.runs.cancel()"""
    run = _runs.get(run_id)
    if not run:
        raise HTTPException(404, f"Run '{run_id}' not found")
    if run.thread_id != thread_id:
        raise HTTPException(404, f"Run '{run_id}' not on thread '{thread_id}'")

    if run.task and not run.task.done():
        run.task.cancel()
    run.status = "cancelled"
    run.updated_at = _now_iso()

    thread = _threads.get(thread_id)
    if thread:
        async with thread.lock:
            thread.status = "idle"

    return None


# ─── 内存清理 ───

_cleanup_task: asyncio.Task | None = None


async def _cleanup_loop():
    """定期清理超过 1 小时的已完成 thread/run"""
    while True:
        await asyncio.sleep(3600)
        try:
            now = datetime.now(UTC)
            stale_threads = []
            for tid, thread in _threads.items():
                if thread.status != "idle":
                    continue
                try:
                    updated = datetime.fromisoformat(thread.updated_at)
                    if (now - updated).total_seconds() > 3600:
                        stale_threads.append(tid)
                except (ValueError, TypeError):
                    pass

            for tid in stale_threads:
                # 清理关联的 runs
                stale_runs = [rid for rid, r in _runs.items() if r.thread_id == tid]
                for rid in stale_runs:
                    del _runs[rid]
                del _threads[tid]

            if stale_threads:
                logger.info("LG Compat: 已清理 %d 个过期 thread", len(stale_threads))
        except Exception as e:
            logger.error("LG Compat 清理失败: %s", e)


async def start_cleanup():
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_cleanup_loop())


async def stop_cleanup():
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
    _cleanup_task = None

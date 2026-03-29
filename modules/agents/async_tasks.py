"""本地异步任务管理器 — 模拟 AsyncSubAgent 行为

通过 asyncio.create_task 在后台运行 agent，提供非阻塞的子智能体委派能力。
主 agent 可以启动后台任务后继续对话，用户稍后查看结果。

工具:
- start_background_task → 启动后台任务，立即返回 task_id
- get_task_status → 查询任务状态和结果
- list_tasks → 列出所有任务
- cancel_task → 取消运行中的任务
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime

from database import get_db

logger = logging.getLogger(__name__)

# 内存中跟踪活跃的后台任务
_running_tasks: dict[str, asyncio.Task] = {}

# 已知的可委派子智能体类型
VALID_TASK_TYPES = {
    "researcher", "log-analyzer", "security-auditor",
    "correlation-analyzer", "ops-scheduler", "knowledge-retriever",
}


async def start_background_task(task_type: str, instruction: str) -> str:
    """启动后台异步任务

    Args:
        task_type: 子智能体类型名（必须在 VALID_TASK_TYPES 中）
        instruction: 要执行的任务描述

    Returns:
        task_id（8 字符短 ID）
    """
    if task_type not in VALID_TASK_TYPES:
        return f"无效的任务类型: {task_type}。可用类型: {', '.join(sorted(VALID_TASK_TYPES))}"

    task_id = uuid.uuid4().hex[:8]

    # 持久化初始状态
    db = await get_db()
    await db.execute(
        "INSERT INTO async_agent_tasks (id, task_type, instruction, status, created_at) "
        "VALUES (?, ?, ?, 'running', ?)",
        (task_id, task_type, instruction[:2000], datetime.now().isoformat()),
    )
    await db.commit()

    # 启动后台 asyncio 任务
    coro = _execute_background(task_id, task_type, instruction)
    async_task = asyncio.create_task(coro, name=f"bg-{task_type}-{task_id}")
    _running_tasks[task_id] = async_task

    logger.info("后台任务已启动: %s (%s)", task_id, task_type)
    return task_id


async def _execute_background(task_id: str, task_type: str, instruction: str):
    """后台执行：构建 patrol 模式 agent，委派指定 subagent 执行任务"""
    start_time = time.time()
    try:
        from modules.agents.deep_agent import build_agent

        agent = await build_agent(safety_mode="autonomous", purpose="patrol")
        thread_id = f"async-{task_type}-{task_id}"
        config = {"configurable": {"thread_id": thread_id}}

        prompt = (
            f"请立即使用 task() 工具委派 {task_type} 子智能体执行以下任务：\n\n"
            f"{instruction}\n\n"
            f"将子智能体返回的结果直接作为你的最终回复。不要添加额外评论。"
        )

        result = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config=config,
            ),
            timeout=300,  # 5 分钟超时
        )

        # 提取最后的 AI 消息作为结果
        report = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "content") and not hasattr(msg, "tool_call_id"):
                report = msg.content
                break

        duration = time.time() - start_time

        # 写入成功结果
        db = await get_db()
        await db.execute(
            "UPDATE async_agent_tasks SET status='success', result=?, completed_at=? WHERE id=?",
            (report[:10000], datetime.now().isoformat(), task_id),
        )
        await db.commit()
        logger.info("后台任务完成: %s (%.1fs)", task_id, duration)

    except asyncio.TimeoutError:
        db = await get_db()
        await db.execute(
            "UPDATE async_agent_tasks SET status='timeout', result=?, completed_at=? WHERE id=?",
            ("任务执行超时（5分钟限制）", datetime.now().isoformat(), task_id),
        )
        await db.commit()
        logger.warning("后台任务超时: %s", task_id)

    except asyncio.CancelledError:
        db = await get_db()
        await db.execute(
            "UPDATE async_agent_tasks SET status='cancelled', completed_at=? WHERE id=?",
            (datetime.now().isoformat(), task_id),
        )
        await db.commit()
        logger.info("后台任务已取消: %s", task_id)

    except Exception as e:
        db = await get_db()
        await db.execute(
            "UPDATE async_agent_tasks SET status='error', result=?, completed_at=? WHERE id=?",
            (str(e)[:2000], datetime.now().isoformat(), task_id),
        )
        await db.commit()
        logger.error("后台任务失败: %s — %s", task_id, e)

    finally:
        _running_tasks.pop(task_id, None)


async def get_task_status(task_id: str) -> str:
    """查询后台任务状态和结果"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT task_type, instruction, status, result, created_at, completed_at "
        "FROM async_agent_tasks WHERE id = ?",
        (task_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return f"未找到任务: {task_id}"

    task_type, instruction, status, result, created_at, completed_at = row

    lines = [
        f"## 后台任务 {task_id}",
        f"- 类型: {task_type}",
        f"- 状态: {status}",
        f"- 创建时间: {created_at}",
    ]
    if completed_at:
        lines.append(f"- 完成时间: {completed_at}")
    lines.append(f"- 任务描述: {instruction[:200]}")

    if status == "running":
        lines.append("\n任务正在执行中，请稍后再查询。")
    elif status == "success" and result:
        lines.append(f"\n### 执行结果\n{result}")
    elif result:
        lines.append(f"\n### 错误信息\n{result}")

    return "\n".join(lines)


async def list_tasks(limit: int = 20) -> str:
    """列出所有后台任务"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, task_type, status, created_at, completed_at "
        "FROM async_agent_tasks ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return "没有后台任务记录。"

    lines = [
        "## 后台任务列表",
        "| ID | 类型 | 状态 | 创建时间 | 完成时间 |",
        "|---|---|---|---|---|",
    ]
    for task_id, task_type, status, created_at, completed_at in rows:
        t_created = created_at[:16] if created_at else "-"
        t_completed = completed_at[:16] if completed_at else "-"
        lines.append(f"| {task_id} | {task_type} | {status} | {t_created} | {t_completed} |")

    running_count = sum(1 for r in rows if r[2] == "running")
    if running_count:
        lines.append(f"\n当前有 {running_count} 个任务正在运行。")
    return "\n".join(lines)


async def cancel_task(task_id: str) -> str:
    """取消运行中的后台任务"""
    if task_id in _running_tasks:
        _running_tasks[task_id].cancel()
        return f"已发送取消请求: {task_id}"

    # 检查数据库中是否存在
    db = await get_db()
    cursor = await db.execute(
        "SELECT status FROM async_agent_tasks WHERE id = ?", (task_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return f"未找到任务: {task_id}"
    if row[0] != "running":
        return f"任务 {task_id} 状态为 {row[0]}，无法取消。"
    return f"任务 {task_id} 不在当前进程的运行列表中（可能已在其他进程完成）。"


async def cleanup_stale_tasks():
    """启动时清理上次进程遗留的 running 状态任务"""
    db = await get_db()
    await db.execute(
        "UPDATE async_agent_tasks SET status='error', "
        "result='进程重启，任务中断', completed_at=? "
        "WHERE status='running'",
        (datetime.now().isoformat(),),
    )
    await db.commit()

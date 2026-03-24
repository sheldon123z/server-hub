"""巡检任务定义 + asyncio 调度器"""

import asyncio
import json
import logging
import time
from datetime import datetime

from config import settings
from database import get_db
from modules.agents.prompts import PATROL_PROMPT

logger = logging.getLogger(__name__)

# ─── 内置巡检任务 ───

DEFAULT_PATROLS = [
    {
        "id": "memory_check",
        "display_name": "内存巡检",
        "description": "检查系统内存和用户内存使用，超配额告警",
        "interval_minutes": 30,
        "check_tools": "get_system_overview,get_user_resources,get_user_quotas",
        "prompt": "检查系统内存使用率（超过85%告警）和每个用户的内存使用是否超过其配额。对超配额的用户发出告警。",
    },
    {
        "id": "docker_health",
        "display_name": "Docker 容器健康",
        "description": "检查所有容器运行状态，异常重启告警",
        "interval_minutes": 15,
        "check_tools": "list_docker_containers",
        "prompt": "检查所有Docker容器状态。报告处于restarting或exited状态的容器。",
    },
    {
        "id": "gpu_monitor",
        "display_name": "GPU 监控",
        "description": "检查 GPU 利用率、显存、温度",
        "interval_minutes": 60,
        "check_tools": "get_system_overview",
        "prompt": "检查GPU温度（超过80°C警告，超过85°C紧急告警）和显存使用率（超过95%告警）。",
    },
    {
        "id": "service_status",
        "display_name": "服务状态巡检",
        "description": "检查所有 systemd 服务是否正常运行",
        "interval_minutes": 30,
        "check_tools": "list_systemd_services",
        "prompt": "检查所有管理的systemd服务状态。报告任何意外停止的服务。",
    },
    {
        "id": "disk_usage",
        "display_name": "磁盘空间巡检",
        "description": "检查所有磁盘使用率",
        "interval_minutes": 360,
        "check_tools": "get_system_overview,get_disk_info",
        "prompt": "检查所有磁盘挂载点使用率。任何挂载点超过90%需要告警。",
    },
    {
        "id": "daily_report",
        "display_name": "每日综合报告",
        "description": "生成综合报告并发送 Telegram",
        "interval_minutes": 1440,
        "check_tools": "get_system_overview,get_disk_info,get_user_resources,list_docker_containers,list_systemd_services",
        "prompt": "生成一份全面的服务器状态报告，包括系统资源、磁盘、用户、Docker和服务状态。最后调用send_notification发送报告摘要。",
    },
]


async def seed_default_patrols():
    """初始化默认巡检任务（如果不存在）"""
    db = await get_db()
    for p in DEFAULT_PATROLS:
        existing = await db.execute("SELECT id FROM agent_patrol_tasks WHERE id = ?", (p["id"],))
        if not await existing.fetchone():
            await db.execute(
                "INSERT INTO agent_patrol_tasks (id, display_name, description, interval_minutes, check_tools, prompt) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (p["id"], p["display_name"], p["description"], p["interval_minutes"], p["check_tools"], p["prompt"]),
            )
    await db.commit()


async def execute_patrol(task: dict):
    """执行单个巡检任务（通过 agent graph）"""
    start_time = time.time()
    task_id = task["id"] if isinstance(task, dict) else task[0]
    display_name = task.get("display_name", task_id) if isinstance(task, dict) else task[1]
    description = task.get("description", "") if isinstance(task, dict) else task[2]
    prompt_text = task.get("prompt", "") if isinstance(task, dict) else task[5]

    try:
        from modules.agents.deep_agent import build_agent

        agent = await build_agent(safety_mode="autonomous", purpose="patrol")
        thread_id = f"patrol-{task_id}-{int(time.time())}"
        config = {"configurable": {"thread_id": thread_id}}

        patrol_prompt = PATROL_PROMPT.format(
            task_name=display_name,
            task_description=description,
        )

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": patrol_prompt}]},
            config=config,
        )

        # 提取最后的 AI 消息作为报告
        report = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "content") and not hasattr(msg, "tool_call_id"):
                report = msg.content
                break

        # 简单判断状态
        status = "ok"
        if any(w in report for w in ["告警", "严重", "异常", "超过", "警告"]):
            status = "warning"
        if any(w in report for w in ["严重", "紧急", "critical"]):
            status = "critical"

        duration = time.time() - start_time

        # 保存结果
        db = await get_db()
        await db.execute(
            "UPDATE agent_patrol_tasks SET last_run = ?, last_status = ?, last_report = ? WHERE id = ?",
            (datetime.now().isoformat(), status, report[:5000], task_id),
        )
        await db.execute(
            "INSERT INTO agent_patrol_history (task_id, status, report, duration_seconds) VALUES (?, ?, ?, ?)",
            (task_id, status, report[:5000], duration),
        )
        await db.commit()

        # 告警时发送通知到所有启用渠道
        if status in ("warning", "critical"):
            try:
                from modules.notifications.services import send_notification
                await send_notification(f"[巡检告警] {display_name}\n{report[:500]}")
            except Exception:
                pass

        logger.info(f"巡检 {display_name} 完成: {status} ({duration:.1f}s)")
        return status, report

    except Exception as e:
        logger.error(f"巡检 {display_name} 失败: {e}")
        duration = time.time() - start_time
        db = await get_db()
        await db.execute(
            "UPDATE agent_patrol_tasks SET last_run = ?, last_status = ? WHERE id = ?",
            (datetime.now().isoformat(), "error", task_id),
        )
        await db.execute(
            "INSERT INTO agent_patrol_history (task_id, status, report, duration_seconds) VALUES (?, ?, ?, ?)",
            (task_id, "error", str(e)[:2000], duration),
        )
        await db.commit()
        return "error", str(e)


# ─── 调度器 ───

_patrol_task: asyncio.Task | None = None


async def _patrol_loop():
    """巡检调度主循环"""
    logger.info("巡检调度器已启动")
    while True:
        try:
            db = await get_db()
            cursor = await db.execute(
                "SELECT id, display_name, description, interval_minutes, check_tools, prompt, last_run "
                "FROM agent_patrol_tasks WHERE enabled = 1"
            )
            tasks = await cursor.fetchall()

            now = datetime.now()
            for row in tasks:
                task_id, display_name, desc, interval, tools, prompt, last_run = row
                should_run = False

                if last_run is None:
                    should_run = True
                else:
                    try:
                        last = datetime.fromisoformat(last_run)
                        elapsed = (now - last).total_seconds() / 60
                        if elapsed >= interval:
                            should_run = True
                    except (ValueError, TypeError):
                        should_run = True

                if should_run:
                    task_dict = {
                        "id": task_id, "display_name": display_name,
                        "description": desc, "prompt": prompt,
                    }
                    asyncio.create_task(execute_patrol(task_dict))

        except Exception as e:
            logger.error(f"巡检调度器错误: {e}")

        await asyncio.sleep(60)  # 每分钟检查一次


async def start_patrol_scheduler():
    global _patrol_task
    if _patrol_task is not None and not _patrol_task.done():
        return
    await seed_default_patrols()
    _patrol_task = asyncio.create_task(_patrol_loop())


async def stop_patrol_scheduler():
    global _patrol_task
    if _patrol_task is not None and not _patrol_task.done():
        _patrol_task.cancel()
    _patrol_task = None

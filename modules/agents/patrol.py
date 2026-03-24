"""巡检任务定义 + asyncio 调度器"""

import asyncio
import json
import logging
import time
from datetime import datetime

from config import settings
from database import get_db
from modules.agents.prompts import PATROL_PROMPT
from modules.agents.report_schema import (
    parse_patrol_report, determine_status_from_text, report_summary_text,
)

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
    {
        "id": "security_compliance",
        "display_name": "安全合规检查",
        "description": "基于 CIS Benchmark 检查 SSH、口令、权限、网络、内核等安全基线",
        "interval_minutes": 1440,
        "check_tools": "check_compliance",
        "prompt": "执行全部安全合规基线检查（调用 check_compliance 工具，不传 category 参数）。对不合规项按严重程度分类，重点关注 high 和 critical 级别的问题，给出修复建议。",
    },
    {
        "id": "resource_trend",
        "display_name": "资源趋势周报",
        "description": "分析过去一周的系统资源使用趋势，预测未来走势",
        "interval_minutes": 10080,
        "check_tools": "analyze_resource_trend,get_system_overview",
        "prompt": "分析过去一周的资源趋势（调用 analyze_resource_trend 工具，metric='all'），结合当前系统状态，输出资源评估报告。重点关注持续上升的指标和接近阈值的资源。",
    },
]


# ─── 内置巡检模板 ───

DEFAULT_TEMPLATES = [
    {
        "id": "tpl_memory",
        "name": "内存巡检",
        "category": "performance",
        "description": "检查系统内存和用户内存使用，超配额告警",
        "check_tools": "get_system_overview,get_user_resources,get_user_quotas",
        "prompt_template": "检查系统内存使用率（超过{warning_threshold}%告警）和每个用户的内存使用是否超过其配额。对超配额的用户发出告警。",
        "variables": json.dumps([
            {"name": "warning_threshold", "type": "number", "default": 85, "description": "告警阈值(%)"},
        ]),
    },
    {
        "id": "tpl_docker",
        "name": "Docker 容器健康",
        "category": "availability",
        "description": "检查所有容器运行状态，异常重启告警",
        "check_tools": "list_docker_containers",
        "prompt_template": "检查所有Docker容器状态。报告处于restarting或exited状态的容器。",
        "variables": "[]",
    },
    {
        "id": "tpl_gpu",
        "name": "GPU 监控",
        "category": "performance",
        "description": "检查 GPU 利用率、显存、温度",
        "check_tools": "get_system_overview",
        "prompt_template": "检查GPU温度（超过{temp_warning}°C警告，超过{temp_critical}°C紧急告警）和显存使用率（超过{mem_threshold}%告警）。",
        "variables": json.dumps([
            {"name": "temp_warning", "type": "number", "default": 80, "description": "温度警告阈值(°C)"},
            {"name": "temp_critical", "type": "number", "default": 85, "description": "温度紧急阈值(°C)"},
            {"name": "mem_threshold", "type": "number", "default": 95, "description": "显存告警阈值(%)"},
        ]),
    },
    {
        "id": "tpl_service",
        "name": "服务状态巡检",
        "category": "availability",
        "description": "检查所有 systemd 服务是否正常运行",
        "check_tools": "list_systemd_services",
        "prompt_template": "检查所有管理的systemd服务状态。报告任何意外停止的服务。",
        "variables": "[]",
    },
    {
        "id": "tpl_disk",
        "name": "磁盘空间巡检",
        "category": "performance",
        "description": "检查所有磁盘使用率",
        "check_tools": "get_system_overview,get_disk_info",
        "prompt_template": "检查所有磁盘挂载点使用率。任何挂载点超过{threshold}%需要告警。",
        "variables": json.dumps([
            {"name": "threshold", "type": "number", "default": 90, "description": "磁盘告警阈值(%)"},
        ]),
    },
    {
        "id": "tpl_daily_report",
        "name": "每日综合报告",
        "category": "general",
        "description": "生成综合系统状态报告并发送 Telegram",
        "check_tools": "get_system_overview,get_disk_info,get_user_resources,list_docker_containers,list_systemd_services",
        "prompt_template": "生成一份全面的服务器状态报告，包括系统资源、磁盘、用户、Docker和服务状态。最后调用send_notification发送报告摘要。",
        "variables": "[]",
    },
    {
        "id": "tpl_security_compliance",
        "name": "安全合规检查",
        "category": "security",
        "description": "基于 CIS Benchmark 检查 SSH、口令、权限、网络、内核安全基线",
        "check_tools": "check_compliance",
        "prompt_template": "执行安全合规基线检查（调用 check_compliance 工具）。对不合规项按严重程度分类，重点关注 high 和 critical 级别的问题，给出修复建议。",
        "variables": "[]",
    },
    {
        "id": "tpl_user_audit",
        "name": "用户资源审计",
        "category": "security",
        "description": "审计用户资源使用情况，检测异常占用",
        "check_tools": "get_user_resources,get_user_quotas,get_system_overview",
        "prompt_template": "审计所有用户的资源使用：1) 检查内存和进程数是否超过配额 2) 检查是否有用户 GPU 显存占用异常 3) 识别长期占用大量资源但无活动的用户。对异常用户给出处理建议。",
        "variables": "[]",
    },
    {
        "id": "tpl_docker_deep",
        "name": "Docker 深度检查",
        "category": "availability",
        "description": "深度检查 Docker 容器日志异常和资源占用",
        "check_tools": "list_docker_containers,get_container_logs",
        "prompt_template": "深度检查所有运行中的容器：1) 检查容器状态（重启循环、异常退出）2) 查看异常容器的最近日志，分析错误原因 3) 关注 Dify worker 容器的重启问题。对发现的问题给出修复建议。",
        "variables": "[]",
    },
    {
        "id": "tpl_network_security",
        "name": "网络安全检查",
        "category": "security",
        "description": "检查端口暴露、异常连接、防火墙状态",
        "check_tools": "check_compliance,list_systemd_services",
        "prompt_template": "检查网络安全状况：1) 调用 check_compliance 检查网络安全相关基线 2) 确认 fail2ban 服务运行正常 3) 使用 execute 执行 'ss -tlnp' 查看端口暴露情况，识别不必要暴露的端口。",
        "variables": "[]",
    },
    {
        "id": "tpl_resource_trend",
        "name": "资源趋势分析",
        "category": "performance",
        "description": "分析系统资源的历史趋势，预测未来走势",
        "check_tools": "analyze_resource_trend,get_system_overview",
        "prompt_template": "分析过去{hours}小时的资源趋势（调用 analyze_resource_trend 工具），结合当前系统状态，输出资源评估报告。重点关注持续上升的指标。",
        "variables": json.dumps([
            {"name": "hours", "type": "number", "default": 168, "description": "分析时间范围(小时)"},
        ]),
    },
]


async def seed_default_patrols():
    """初始化默认巡检任务、巡检模板和告警规则"""
    db = await get_db()

    # 种子巡检任务
    for p in DEFAULT_PATROLS:
        existing = await db.execute("SELECT id FROM agent_patrol_tasks WHERE id = ?", (p["id"],))
        if not await existing.fetchone():
            await db.execute(
                "INSERT INTO agent_patrol_tasks (id, display_name, description, interval_minutes, check_tools, prompt) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (p["id"], p["display_name"], p["description"], p["interval_minutes"], p["check_tools"], p["prompt"]),
            )
    await db.commit()

    # 种子巡检模板
    for t in DEFAULT_TEMPLATES:
        existing = await db.execute("SELECT id FROM patrol_templates WHERE id = ?", (t["id"],))
        if not await existing.fetchone():
            variables = t.get("variables", "[]")
            if isinstance(variables, list):
                variables = json.dumps(variables, ensure_ascii=False)
            await db.execute(
                "INSERT INTO patrol_templates (id, name, category, description, check_tools, prompt_template, variables, is_builtin) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (t["id"], t["name"], t.get("category", "general"), t.get("description", ""),
                 t["check_tools"], t["prompt_template"], variables),
            )
    await db.commit()

    # 种子告警规则
    from modules.agents.alert_engine import seed_default_alert_rules
    await seed_default_alert_rules()


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

        # 结构化解析报告
        report_json = parse_patrol_report(report)
        if report_json:
            status = report_json["status"]
            report_json_str = json.dumps(report_json, ensure_ascii=False)
        else:
            # 回退到关键字匹配
            status = determine_status_from_text(report)
            report_json_str = None

        duration = time.time() - start_time

        # 保存结果
        db = await get_db()
        await db.execute(
            "UPDATE agent_patrol_tasks SET last_run = ?, last_status = ?, last_report = ? WHERE id = ?",
            (datetime.now().isoformat(), status, report[:5000], task_id),
        )
        await db.execute(
            "INSERT INTO agent_patrol_history (task_id, status, report, report_json, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, status, report[:5000], report_json_str, duration),
        )
        await db.commit()

        # 告警时发送 Telegram（优先用结构化摘要）
        if status in ("warning", "critical"):
            try:
                from modules.notifications.services import send_telegram
                if report_json:
                    alert_text = f"[巡检告警] {display_name}\n{report_summary_text(report_json)}"
                else:
                    alert_text = f"[巡检告警] {display_name}\n{report[:500]}"
                await send_telegram(alert_text[:1000])
            except Exception:
                pass

        # 触发告警规则引擎（从结构化报告提取指标）
        if report_json:
            try:
                from modules.agents.alert_engine import evaluate_rules, extract_metrics_from_report
                flat_metrics = extract_metrics_from_report(report_json)
                if flat_metrics:
                    await evaluate_rules(flat_metrics)
            except Exception as e:
                logger.error(f"告警规则引擎执行失败: {e}")

        # critical 状态自动触发故障诊断（异步，不阻塞巡检流程）
        if status == "critical":
            try:
                from modules.agents.diagnosis import trigger_diagnosis
                context = report_summary_text(report_json) if report_json else report[:500]
                asyncio.create_task(trigger_diagnosis(
                    source=f"patrol:{task_id}",
                    severity="critical",
                    alert_context=f"巡检任务 [{display_name}] 发现严重问题:\n{context}",
                ))
            except Exception as e:
                logger.error(f"触发故障诊断失败: {e}")

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

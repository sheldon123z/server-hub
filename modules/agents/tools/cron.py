"""Cron 定时任务管理工具"""

from langchain_core.tools import tool


@tool
async def list_cron_jobs(cron_user: str = "zhengxiaodong") -> str:
    """列出指定用户的 cron 定时任务。"""
    from modules.cron.services import get_root_crontab, get_user_crontab

    jobs = await get_root_crontab() if cron_user == "root" else await get_user_crontab(cron_user)
    if not jobs:
        return f"用户 {cron_user} 没有定时任务"
    lines = [f"## {cron_user} 的定时任务 ({len(jobs)} 条)\n"]
    for j in jobs:
        status = "启用" if j["enabled"] else "禁用"
        lines.append(f"- [{status}] `{j['schedule']}` {j['command'][:100]}")
    return "\n".join(lines)


@tool
def validate_cron_expr(expression: str) -> str:
    """验证 cron 表达式是否合法。"""
    from modules.cron.services import validate_cron_expression

    result = validate_cron_expression(expression)
    if not result["valid"]:
        return f"无效表达式: {result['error']}"
    runs = "\n".join(f"  - {r}" for r in result["next_runs"])
    return f"表达式: `{expression}` — {result['description']}\n\n未来执行:\n{runs}"


@tool
async def create_cron_job(cron_user: str, schedule: str, command: str, comment: str = "") -> str:
    """创建新的 cron 定时任务。"""
    from modules.cron.services import add_cron_job

    try:
        await add_cron_job(cron_user, schedule, command, comment)
        return f"已创建定时任务: {schedule} {command}"
    except Exception as e:
        return f"创建失败: {e}"


@tool
async def modify_cron_schedule(cron_user: str, old_schedule: str, command: str, new_schedule: str) -> str:
    """修改已有 cron 任务的执行时间。"""
    from modules.cron.services import update_cron_schedule

    try:
        await update_cron_schedule(cron_user, old_schedule, command, new_schedule)
        return f"已更新任务时间: {new_schedule}"
    except Exception as e:
        return f"更新失败: {e}"


@tool
async def toggle_cron_job_tool(cron_user: str, schedule: str, command: str, enabled: bool) -> str:
    """启用或禁用 cron 定时任务。"""
    from modules.cron.services import toggle_cron_job

    try:
        await toggle_cron_job(cron_user, schedule, command, enabled)
        return f"已{'启用' if enabled else '禁用'}任务"
    except Exception as e:
        return f"操作失败: {e}"


@tool
async def delete_cron_job_tool(cron_user: str, schedule: str, command: str) -> str:
    """删除 cron 定时任务。"""
    from modules.cron.services import delete_cron_job

    try:
        await delete_cron_job(cron_user, schedule, command)
        return "任务已删除"
    except Exception as e:
        return f"删除失败: {e}"

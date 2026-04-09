"""Cron 定时任务管理工具"""

import asyncio
import os
import stat
from pathlib import Path

from modules.agents.tools.registry import RiskLevel, register_tool


@register_tool(risk=RiskLevel.SAFE, group="cron:read", icon="Clock", label="定时任务列表")
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


@register_tool(risk=RiskLevel.SAFE, group="cron:read", icon="CheckCircle", label="表达式验证")
def validate_cron_expr(expression: str) -> str:
    """验证 cron 表达式是否合法。"""
    from modules.cron.services import validate_cron_expression

    result = validate_cron_expression(expression)
    if not result["valid"]:
        return f"无效表达式: {result['error']}"
    runs = "\n".join(f"  - {r}" for r in result["next_runs"])
    return f"表达式: `{expression}` — {result['description']}\n\n未来执行:\n{runs}"


@register_tool(risk=RiskLevel.DANGER, group="cron:write", icon="PlusCircle", label="创建定时任务")
async def create_cron_job(cron_user: str, schedule: str, command: str, comment: str = "") -> str:
    """创建新的 cron 定时任务。优先使用 setup_scheduled_task 进行一体化创建。"""
    from modules.cron.services import add_cron_job

    try:
        await add_cron_job(cron_user, schedule, command, comment)
        return f"已创建定时任务: {schedule} {command}\n[CRON_UPDATED]"
    except Exception as e:
        return f"创建失败: {e}"


@register_tool(risk=RiskLevel.MODERATE, group="cron:write", icon="Edit", label="修改任务计划")
async def modify_cron_schedule(cron_user: str, old_schedule: str, command: str, new_schedule: str) -> str:
    """修改已有 cron 任务的执行时间。"""
    from modules.cron.services import update_cron_schedule

    try:
        await update_cron_schedule(cron_user, old_schedule, command, new_schedule)
        return f"已更新任务时间: {new_schedule}\n[CRON_UPDATED]"
    except Exception as e:
        return f"更新失败: {e}"


@register_tool(risk=RiskLevel.MODERATE, group="cron:write", icon="ToggleLeft", label="启禁任务")
async def toggle_cron_job_tool(cron_user: str, schedule: str, command: str, enabled: bool) -> str:
    """启用或禁用 cron 定时任务。"""
    from modules.cron.services import toggle_cron_job

    try:
        await toggle_cron_job(cron_user, schedule, command, enabled)
        return f"已{'启用' if enabled else '禁用'}任务\n[CRON_UPDATED]"
    except Exception as e:
        return f"操作失败: {e}"


@register_tool(risk=RiskLevel.DANGER, group="cron:write", icon="Trash2", label="删除定时任务")
async def delete_cron_job_tool(cron_user: str, schedule: str, command: str) -> str:
    """删除 cron 定时任务。"""
    from modules.cron.services import delete_cron_job

    try:
        await delete_cron_job(cron_user, schedule, command)
        return "任务已删除\n[CRON_UPDATED]"
    except Exception as e:
        return f"删除失败: {e}"


@register_tool(risk=RiskLevel.DANGER, group="cron:write", icon="CalendarPlus", label="一体化创建定时任务")
async def setup_scheduled_task(
    cron_user: str,
    schedule: str,
    command: str,
    comment: str = "",
    script_path: str = "",
    script_content: str = "",
    dry_run: bool = True,
) -> str:
    """一体化创建定时任务：验证表达式 → 写脚本文件 → 设权限 → 语法检查 → 写入 crontab → 回读验证。

    当需要创建定时任务时，优先使用此工具而非分步调用多个工具。

    Args:
        cron_user: 执行用户 ("root" 或 Linux 用户名)
        schedule: cron 表达式 (5 字段，如 "0 3 * * *")
        command: crontab 中执行的命令（如脚本路径 + 重定向）
        comment: 任务备注说明
        script_path: 需要创建的脚本文件绝对路径（可选，如 /home/user/scripts/backup.sh）
        script_content: 脚本文件内容（可选，与 script_path 配合使用）
        dry_run: 是否对脚本做语法检查 (默认 True)
    """
    from modules.cron.services import (
        add_cron_job,
        get_root_crontab,
        get_user_crontab,
        validate_cron_expression,
    )

    steps: list[str] = []
    rollback_actions: list[str] = []  # 记录需要回滚的操作

    # ── Step 1: 验证 cron 表达式 ──
    validation = validate_cron_expression(schedule)
    if not validation["valid"]:
        return f"❌ 表达式验证失败: {validation['error']}"
    steps.append(f"✅ 表达式验证通过: {schedule} — {validation['description']}")
    next_run = validation["next_runs"][0] if validation["next_runs"] else "未知"

    # ── Step 2: 写入脚本文件（如果提供了内容）──
    if script_path and script_content:
        expanded_path = os.path.expanduser(script_path)  # noqa: ASYNC240
        script_file = Path(expanded_path)

        # 安全检查：不允许写入敏感路径
        sensitive_dirs = ("/etc", "/usr", "/bin", "/sbin", "/boot", "/proc", "/sys")
        if any(expanded_path.startswith(d) for d in sensitive_dirs):
            return f"❌ 安全限制: 不允许在 {expanded_path} 创建脚本"

        def _write_script() -> None:
            script_file.parent.mkdir(parents=True, exist_ok=True)
            script_file.write_text(script_content, encoding="utf-8")
            script_file.chmod(stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        try:
            await asyncio.to_thread(_write_script)
            steps.append(f"✅ 脚本已写入: {expanded_path} (权限 755)")
            rollback_actions.append(f"script:{expanded_path}")
        except Exception as e:
            return f"❌ 写入脚本失败: {e}\n\n已完成步骤:\n" + "\n".join(steps)

        # ── Step 3: 语法检查 ──
        if dry_run:
            try:
                # 检测脚本类型并选择检查命令
                first_line = script_content.split("\n", 1)[0].strip()
                if "python" in first_line:
                    check_cmd = ["python3", "-m", "py_compile", expanded_path]
                else:
                    check_cmd = ["bash", "-n", expanded_path]

                proc = await asyncio.create_subprocess_exec(
                    *check_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode != 0:
                    error_msg = stderr.decode().strip()
                    # 回滚：删除有语法错误的脚本
                    await asyncio.to_thread(script_file.unlink, True)
                    return (
                        f"❌ 脚本语法检查失败:\n```\n{error_msg}\n```\n"
                        f"已回滚脚本文件。请修正后重试。\n\n已完成步骤:\n" + "\n".join(steps)
                    )
                steps.append("✅ 脚本语法检查通过")
            except Exception as e:
                steps.append(f"⚠️ 语法检查跳过: {e}")

    # ── Step 4: 写入 crontab ──
    try:
        await add_cron_job(cron_user, schedule, command, comment)
        steps.append(f"✅ 已写入 {cron_user} 的 crontab")
    except ValueError as e:
        # 如果是重复任务，不算失败
        if "已存在" in str(e):
            steps.append("ℹ️ 任务已存在于 crontab，跳过写入")
        else:
            # 回滚脚本文件
            for action in rollback_actions:
                if action.startswith("script:"):
                    await asyncio.to_thread(Path(action[7:]).unlink, True)
                    steps.append("↩️ 已回滚脚本文件")
            return f"❌ 写入 crontab 失败: {e}\n\n已完成步骤:\n" + "\n".join(steps)
    except Exception as e:
        for action in rollback_actions:
            if action.startswith("script:"):
                await asyncio.to_thread(Path(action[7:]).unlink, True)
                steps.append("↩️ 已回滚脚本文件")
        return f"❌ 写入 crontab 失败: {e}\n\n已完成步骤:\n" + "\n".join(steps)

    # ── Step 5: 回读验证 ──
    try:
        jobs = await get_root_crontab() if cron_user == "root" else await get_user_crontab(cron_user)
        found = any(j["schedule"] == schedule and command in j["command"] for j in jobs)
        if found:
            steps.append(f"✅ 回读验证通过: 任务已出现在 {cron_user} 的 crontab 中")
        else:
            steps.append("⚠️ 回读验证异常: 写入成功但未在列表中找到，请手动检查")
    except Exception as e:
        steps.append(f"⚠️ 回读验证跳过: {e}")

    # ── 完成报告 ──
    report = "\n".join(steps)
    report += f"\n\n📅 下次执行时间: {next_run}"
    report += "\n\n[CRON_UPDATED]"  # 前端刷新信号
    return report

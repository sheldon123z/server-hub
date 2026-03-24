"""Cron 任务解析、描述和修改"""

import asyncio
import re


def describe_schedule(schedule: str) -> str:
    """将 cron 表达式转为中文描述"""
    parts = schedule.strip().split()
    if len(parts) != 5:
        return schedule

    minute, hour, dom, month, dow = parts
    weekday_names = {"0": "日", "7": "日", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六"}

    m_minute = re.match(r"^\*/(\d+)$", minute)
    if m_minute and hour == "*":
        return f"每{m_minute.group(1)}分钟"
    if minute == "0" and hour == "*" and dom == "*":
        return "每小时整点"
    m_hour = re.match(r"^\*/(\d+)$", hour)
    if minute == "0" and m_hour and dom == "*":
        return f"每{m_hour.group(1)}小时"
    if dom == "*" and month == "*" and dow != "*" and not re.match(r"^[*/]", dow):
        return f"每周{weekday_names.get(dow, dow)} {hour.zfill(2)}:{minute.zfill(2)}"
    if dom == "*" and month == "*" and dow == "*" and "," in hour:
        times = [f"{h.zfill(2)}:{minute.zfill(2)}" for h in hour.split(",")]
        return "每天 " + " 和 ".join(times)
    if dom == "*" and month == "*" and dow == "*" and hour != "*" and minute != "*":
        return f"每天 {hour.zfill(2)}:{minute.zfill(2)}"
    return schedule


def _parse_crontab_lines(output: str) -> list[dict]:
    """解析 crontab 输出，保留注释结构"""
    entries = []
    comment_buffer = ""
    for line in output.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            comment_buffer = stripped.lstrip("# ").strip()
            continue
        if not stripped:
            comment_buffer = ""
            continue

        parts = stripped.split(None, 5)
        if len(parts) < 6:
            comment_buffer = ""
            continue

        schedule = " ".join(parts[:5])
        command = parts[5]
        entries.append({
            "schedule": schedule,
            "description": describe_schedule(schedule),
            "command": command,
            "comment": comment_buffer,
            "raw_line": stripped,
        })
        comment_buffer = ""
    return entries


async def get_user_crontab(username: str = "zhengxiaodong") -> list[dict]:
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise ValueError(f"Invalid username: {username}")
    proc = await asyncio.create_subprocess_exec(
        "crontab", "-l", "-u", username,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        if "no crontab for" in stderr.decode():
            return []
        raise RuntimeError(stderr.decode().strip())
    return _parse_crontab_lines(stdout.decode())


async def get_root_crontab() -> list[dict]:
    proc = await asyncio.create_subprocess_exec(
        "sudo", "crontab", "-l",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        if "no crontab for" in stderr.decode():
            return []
        raise RuntimeError(stderr.decode().strip())
    return _parse_crontab_lines(stdout.decode())


async def update_cron_schedule(cron_user: str, old_schedule: str, old_command: str, new_schedule: str) -> bool:
    """修改某条 cron 任务的时间表达式

    Args:
        cron_user: "root" 或 Linux 用户名
        old_schedule: 原 cron 表达式 (如 "0 */6 * * *")
        old_command: 原命令 (用于精确匹配行)
        new_schedule: 新 cron 表达式
    """
    # 验证新表达式格式
    if len(new_schedule.split()) != 5:
        raise ValueError("Cron 表达式必须包含 5 个字段")

    # 读取当前 crontab
    if cron_user == "root":
        cmd = ["sudo", "crontab", "-l"]
    else:
        if not re.match(r"^[a-zA-Z0-9_-]+$", cron_user):
            raise ValueError(f"Invalid username: {cron_user}")
        cmd = ["crontab", "-l", "-u", cron_user]

    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    lines = stdout.decode().splitlines()

    # 查找并替换目标行
    old_line_prefix = old_schedule + " "
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        # 匹配：旧表达式 + 命令（命令可能有重定向等后缀）
        if stripped.startswith(old_line_prefix) and old_command in stripped:
            new_line = stripped.replace(old_schedule, new_schedule, 1)
            new_lines.append(new_line)
            found = True
        else:
            new_lines.append(line)

    if not found:
        raise ValueError(f"未找到匹配的任务: {old_schedule} {old_command[:50]}")

    # 写回 crontab
    new_content = "\n".join(new_lines) + "\n"
    if cron_user == "root":
        write_cmd = ["sudo", "crontab", "-"]
    else:
        write_cmd = ["crontab", "-u", cron_user, "-"]

    proc = await asyncio.create_subprocess_exec(
        *write_cmd,
        stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate(input=new_content.encode())
    if proc.returncode != 0:
        raise RuntimeError(f"写入 crontab 失败: {stderr.decode().strip()}")

    return True

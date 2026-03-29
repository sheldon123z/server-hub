"""Cron 任务解析、描述、CRUD 和备份管理"""

import asyncio
import re
from datetime import datetime

from config import BASE_DIR

# ─── 表达式描述 ───


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


# ─── 表达式验证 ───


def validate_cron_expression(expression: str) -> dict:
    """验证 cron 表达式并计算未来 5 次执行时间

    Returns:
        {"valid": bool, "description": str, "next_runs": list[str], "error": str|None}
    """
    parts = expression.strip().split()
    if len(parts) != 5:
        return {"valid": False, "description": "", "next_runs": [], "error": "cron 表达式必须包含 5 个字段"}

    try:
        from croniter import croniter

        cron = croniter(expression, datetime.now())
        next_runs = []
        for _ in range(5):
            next_time = cron.get_next(datetime)
            next_runs.append(next_time.strftime("%Y-%m-%d %H:%M"))
        return {
            "valid": True,
            "description": describe_schedule(expression),
            "next_runs": next_runs,
            "error": None,
        }
    except (ValueError, KeyError) as e:
        return {"valid": False, "description": "", "next_runs": [], "error": str(e)}


# ─── 用户名校验与命令构建 ───

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_DISABLED_PREFIX = "#DISABLED# "


def _validate_username(username: str):
    if not _USERNAME_RE.match(username):
        raise ValueError(f"无效的用户名: {username}")


def _crontab_read_cmd(cron_user: str) -> list[str]:
    """构建读取 crontab 的命令"""
    if cron_user == "root":
        return ["sudo", "crontab", "-l"]
    _validate_username(cron_user)
    return ["crontab", "-l", "-u", cron_user]


def _crontab_write_cmd(cron_user: str) -> list[str]:
    """构建写入 crontab 的命令"""
    if cron_user == "root":
        return ["sudo", "crontab", "-"]
    _validate_username(cron_user)
    return ["crontab", "-u", cron_user, "-"]


async def _read_crontab_raw(cron_user: str) -> str:
    """读取原始 crontab 内容"""
    cmd = _crontab_read_cmd(cron_user)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        if "no crontab for" in stderr.decode():
            return ""
        raise RuntimeError(stderr.decode().strip())
    return stdout.decode()


async def _write_crontab_raw(cron_user: str, content: str):
    """写入 crontab 内容"""
    cmd = _crontab_write_cmd(cron_user)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate(input=content.encode())
    if proc.returncode != 0:
        raise RuntimeError(f"写入 crontab 失败: {stderr.decode().strip()}")


# ─── 解析 ───


def _parse_crontab_lines(output: str) -> list[dict]:
    """解析 crontab 输出，保留注释结构

    返回列表中每项包含:
        schedule, description, command, comment, raw_line, enabled, index
    """
    entries = []
    comment_buffer = ""
    idx = 0
    for line in output.strip().splitlines():
        stripped = line.strip()

        # 检查 #DISABLED# 前缀的禁用行
        if stripped.startswith(_DISABLED_PREFIX):
            disabled_line = stripped[len(_DISABLED_PREFIX) :]
            parts = disabled_line.split(None, 5)
            if len(parts) >= 6:
                schedule = " ".join(parts[:5])
                command = parts[5]
                entries.append(
                    {
                        "schedule": schedule,
                        "description": describe_schedule(schedule),
                        "command": command,
                        "comment": comment_buffer,
                        "raw_line": stripped,
                        "enabled": False,
                        "index": idx,
                    }
                )
                idx += 1
                comment_buffer = ""
                continue

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
        entries.append(
            {
                "schedule": schedule,
                "description": describe_schedule(schedule),
                "command": command,
                "comment": comment_buffer,
                "raw_line": stripped,
                "enabled": True,
                "index": idx,
            }
        )
        idx += 1
        comment_buffer = ""
    return entries


# ─── 读取 ───


async def get_user_crontab(username: str = "zhengxiaodong") -> list[dict]:
    _validate_username(username)
    raw = await _read_crontab_raw(username)
    return _parse_crontab_lines(raw) if raw else []


async def get_root_crontab() -> list[dict]:
    raw = await _read_crontab_raw("root")
    return _parse_crontab_lines(raw) if raw else []


# ─── 修改计划 ───


async def update_cron_schedule(cron_user: str, old_schedule: str, old_command: str, new_schedule: str) -> bool:
    """修改某条 cron 任务的时间表达式"""
    if len(new_schedule.split()) != 5:
        raise ValueError("Cron 表达式必须包含 5 个字段")

    raw = await _read_crontab_raw(cron_user)
    lines = raw.splitlines()

    old_line_prefix = old_schedule + " "
    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(old_line_prefix) and old_command in stripped:
            new_line = stripped.replace(old_schedule, new_schedule, 1)
            new_lines.append(new_line)
            found = True
        else:
            new_lines.append(line)

    if not found:
        raise ValueError(f"未找到匹配的任务: {old_schedule} {old_command[:50]}")

    await _write_crontab_raw(cron_user, "\n".join(new_lines) + "\n")
    return True


# ─── 新增任务 ───


async def add_cron_job(cron_user: str, schedule: str, command: str, comment: str = "") -> bool:
    """添加一条新的 cron 任务

    Args:
        cron_user: "root" 或 Linux 用户名
        schedule: cron 表达式 (5 字段)
        command: 要执行的命令
        comment: 可选备注（写入 cron 行上方的注释）
    """
    validation = validate_cron_expression(schedule)
    if not validation["valid"]:
        raise ValueError(f"无效的 cron 表达式: {validation['error']}")

    raw = await _read_crontab_raw(cron_user)
    lines = raw.rstrip("\n").split("\n") if raw.strip() else []

    # 检查重复
    new_job_line = f"{schedule} {command}"
    for line in lines:
        stripped = line.strip()
        if stripped == new_job_line:
            raise ValueError("已存在相同的任务")

    # 追加新任务
    if comment:
        lines.append(f"# {comment}")
    lines.append(new_job_line)

    await _write_crontab_raw(cron_user, "\n".join(lines) + "\n")
    return True


# ─── 删除任务 ───


async def delete_cron_job(cron_user: str, schedule: str, command: str) -> bool:
    """删除一条 cron 任务（连同上方的注释行）"""
    raw = await _read_crontab_raw(cron_user)
    lines = raw.splitlines()

    target = f"{schedule} {command}"
    disabled_target = f"{_DISABLED_PREFIX}{target}"
    found = False
    new_lines = []
    _skip_prev_comment = False

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == target or stripped == disabled_target:
            found = True
            # 如果前一行是注释，也删除
            if new_lines and new_lines[-1].strip().startswith("#"):
                new_lines.pop()
            continue
        new_lines.append(line)

    if not found:
        raise ValueError(f"未找到匹配的任务: {schedule} {command[:50]}")

    await _write_crontab_raw(cron_user, "\n".join(new_lines) + "\n")
    return True


# ─── 启用/禁用 ───


async def toggle_cron_job(cron_user: str, schedule: str, command: str, enabled: bool) -> bool:
    """启用或禁用 cron 任务（通过 #DISABLED# 前缀）"""
    raw = await _read_crontab_raw(cron_user)
    lines = raw.splitlines()

    active_line = f"{schedule} {command}"
    disabled_line = f"{_DISABLED_PREFIX}{active_line}"
    found = False
    new_lines = []

    for line in lines:
        stripped = line.strip()
        if enabled and stripped == disabled_line:
            new_lines.append(active_line)
            found = True
        elif not enabled and stripped == active_line:
            new_lines.append(disabled_line)
            found = True
        else:
            new_lines.append(line)

    if not found:
        raise ValueError(f"未找到匹配的任务: {schedule} {command[:50]}")

    await _write_crontab_raw(cron_user, "\n".join(new_lines) + "\n")
    return True


# ─── 执行历史 ───


async def get_cron_history(command_pattern: str = "", hours: int = 24) -> list[dict]:
    """从 journal 获取 cron 执行历史

    Returns:
        [{"timestamp": str, "user": str, "command": str}]
    """
    cmd = [
        "journalctl",
        "-u",
        "cron",
        "--no-pager",
        "-q",
        "--since",
        f"{hours} hours ago",
        "-o",
        "short-iso",
    ]
    if command_pattern:
        cmd.extend(["--grep", command_pattern])

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()
    output = stdout.decode(errors="replace")

    entries = []
    # 格式: 2024-03-20T08:00:01+0800 hostname CRON[12345]: (user) CMD (command)
    cron_re = re.compile(r"^(\S+)\s+\S+\s+CRON\[\d+\]:\s+\((\w+)\)\s+CMD\s+\((.+)\)\s*$")
    for line in output.strip().splitlines():
        m = cron_re.match(line)
        if m:
            entries.append(
                {
                    "timestamp": m.group(1),
                    "user": m.group(2),
                    "command": m.group(3),
                }
            )

    return entries[-100:]  # 最多返回 100 条


# ─── 备份与还原 ───

_BACKUP_DIR = BASE_DIR / "data" / "cron_backups"


async def backup_crontab(cron_user: str) -> str:
    """备份用户 crontab，返回备份文件路径"""
    _validate_username(cron_user)
    raw = await _read_crontab_raw(cron_user)

    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{cron_user}_{ts}.txt"
    path = _BACKUP_DIR / filename
    path.write_text(raw, encoding="utf-8")
    return str(path)


async def restore_crontab(cron_user: str, backup_filename: str) -> bool:
    """从备份还原 crontab"""
    _validate_username(cron_user)
    # 安全：只允许引用 backup 目录内的文件名（防路径穿越）
    if "/" in backup_filename or "\\" in backup_filename:
        raise ValueError("备份文件名不能包含路径分隔符")
    path = _BACKUP_DIR / backup_filename
    if not path.is_file():
        raise FileNotFoundError(f"备份文件不存在: {backup_filename}")

    content = path.read_text(encoding="utf-8")
    await _write_crontab_raw(cron_user, content)
    return True


def list_cron_backups(cron_user: str = "") -> list[dict]:
    """列出可用的 crontab 备份文件"""
    if not _BACKUP_DIR.is_dir():
        return []
    backups = []
    for f in sorted(_BACKUP_DIR.iterdir(), reverse=True):
        if not f.name.endswith(".txt"):
            continue
        if cron_user and not f.name.startswith(f"{cron_user}_"):
            continue
        backups.append(
            {
                "filename": f.name,
                "cron_user": f.name.rsplit("_", 2)[0],
                "size": f.stat().st_size,
                "created_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return backups[:20]  # 最多 20 条

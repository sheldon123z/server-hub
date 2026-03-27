"""
Linux 用户与配额管理服务。
"""

from __future__ import annotations

import grp
import logging
import os
import pwd
from pathlib import Path
import re
import subprocess

import psutil

from config import settings
from utils.command import run_command, run_command_text

logger = logging.getLogger(__name__)

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_ALLOWED_SHELLS = {
    "/bin/bash",
    "/bin/sh",
    "/bin/zsh",
    "/usr/bin/zsh",
    "/usr/sbin/nologin",
    "/bin/false",
}


def _iter_linux_users(include_admin: bool = False) -> list[pwd.struct_passwd]:
    admin_users = set(settings.admin_linux_users)
    users = []
    for entry in pwd.getpwall():
        if entry.pw_uid < 1000:
            continue
        if not include_admin and entry.pw_name in admin_users:
            continue
        users.append(entry)
    return users


def _group_cache(entries: list[pwd.struct_passwd]) -> dict[str, str]:
    memberships = {entry.pw_name: set() for entry in entries}
    groups = grp.getgrall()
    primary_map = {group.gr_gid: group.gr_name for group in groups}

    for entry in entries:
        primary_group = primary_map.get(entry.pw_gid)
        if primary_group:
            memberships[entry.pw_name].add(primary_group)

    for group in groups:
        for member in group.gr_mem:
            if member in memberships:
                memberships[member].add(group.gr_name)

    return {
        username: " ".join(sorted(group_names))
        for username, group_names in memberships.items()
    }


def _user_exists(username: str) -> bool:
    try:
        pwd.getpwnam(username)
        return True
    except KeyError:
        return False


def _validate_new_username(username: str):
    """校验用户名合法性。"""
    if not _USERNAME_RE.match(username):
        raise ValueError(f"用户名格式不合法: {username}")
    if len(username) < 2 or len(username) > 32:
        raise ValueError("用户名长度需在 2-32 字符之间")


def get_linux_users() -> list[dict]:
    """
    获取 Linux 普通用户列表 (UID >= 1000)，排除管理员。
    返回 [{name, uid, groups}, ...]
    """
    entries = _iter_linux_users(include_admin=False)
    groups_cache = _group_cache(entries)
    return [
        {
            "name": entry.pw_name,
            "uid": entry.pw_uid,
            "groups": groups_cache.get(entry.pw_name, ""),
        }
        for entry in entries
    ]


def get_user_stats() -> list[dict]:
    """
    获取每用户资源使用统计。
    包含: 内存、进程数、GPU 显存、Top 进程
    """
    entries = _iter_linux_users(include_admin=False)
    valid_users = {entry.pw_name: entry for entry in entries}
    groups_cache = _group_cache(entries)

    all_procs: dict[str, list[tuple[int, int, str]]] = {}
    for process in psutil.process_iter(["pid", "username", "memory_info", "name"]):
        try:
            info = process.info
            username = info.get("username") or ""
            if username not in valid_users:
                continue
            rss = info["memory_info"].rss if info.get("memory_info") else 0
            all_procs.setdefault(username, []).append(
                (info["pid"], rss, info.get("name") or "")
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    gpu_user_mem: dict[str, int] = {}
    try:
        gpu_procs_raw = run_command_text(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            timeout=10,
            check=False,
        )
    except RuntimeError:
        gpu_procs_raw = ""
    if gpu_procs_raw:
        pid_user: dict[int, str] = {}
        for username, procs in all_procs.items():
            for pid, _, _ in procs:
                pid_user[pid] = username
        for line in gpu_procs_raw.splitlines():
            parts = [part.strip() for part in line.split(",")]
            if len(parts) < 2 or not parts[0].isdigit():
                continue
            owner = pid_user.get(int(parts[0]))
            if owner:
                gpu_user_mem[owner] = gpu_user_mem.get(owner, 0) + int(parts[1] or 0)

    users = []
    for entry in entries:
        user_procs = all_procs.get(entry.pw_name, [])
        mem_kb = sum(rss for _, rss, _ in user_procs) / 1024
        top_sorted = sorted(user_procs, key=lambda item: item[1], reverse=True)[:3]
        users.append(
            {
                "name": entry.pw_name,
                "uid": entry.pw_uid,
                "groups": groups_cache.get(entry.pw_name, ""),
                "mem_gb": round(mem_kb / 1024 / 1024, 1),
                "proc_count": len(user_procs),
                "gpu_mem_mb": gpu_user_mem.get(entry.pw_name, 0),
                "top_procs": [
                    {
                        "pid": pid,
                        "mem_mb": round(rss / 1024 / 1024, 1),
                        "name": name,
                    }
                    for pid, rss, name in top_sorted
                ],
            }
        )

    users.sort(key=lambda item: item["mem_gb"], reverse=True)
    return users


def read_quotas() -> list[dict]:
    """
    读取配额配置文件。
    格式: key mem_gb proc_limit # comment
    """
    quotas = []
    quota_file = settings.quota_file
    if not os.path.exists(quota_file):
        return quotas
    with open(quota_file, encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                comment = raw_line.split("#", 1)[1].strip() if "#" in raw_line else ""
                quotas.append(
                    {
                        "key": parts[0],
                        "mem_gb": int(parts[1]),
                        "proc_limit": int(parts[2]),
                        "comment": comment,
                    }
                )
    return quotas


def save_quotas(quotas: list[dict]):
    """将配额列表写回配置文件。"""
    lines = [
        "# 用户资源配额配置",
        "# 格式: 用户名或@组名  内存上限(GB)  进程上限  说明",
        "# 优先级: 用户名 > @组名 > default",
        "",
    ]
    for quota in quotas:
        comment = f"  # {quota['comment']}" if quota.get("comment") else ""
        lines.append(
            f"{quota['key']:<18}{quota['mem_gb']:<8}{quota['proc_limit']:<8}{comment}"
        )
    with open(settings.quota_file, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def get_user_quota(username: str, groups_str: str, quotas: list[dict]) -> dict | None:
    """
    三级配额匹配: 精确用户名 > @组名 > default。
    """
    for quota in quotas:
        if quota["key"] == username:
            return quota

    if groups_str:
        for group_name in groups_str.split():
            for quota in quotas:
                if quota["key"] == f"@{group_name}":
                    return quota

    for quota in quotas:
        if quota["key"] == "default":
            return quota

    return None


def kill_user_processes(username: str) -> dict:
    """
    终止指定用户的所有进程。
    先 pkill -u，再 pkill -9 -u 强制清理。
    """
    if username in set(settings.admin_linux_users):
        return {"ok": False, "error": "不能终止管理员进程"}
    if not _USERNAME_RE.match(username):
        return {"ok": False, "error": "用户名不合法"}

    try:
        subprocess.run(["pkill", "-u", username], timeout=5, check=False)
        subprocess.run(["pkill", "-9", "-u", username], timeout=5, check=False)
        return {"ok": True, "error": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def get_all_linux_users() -> list[dict]:
    """获取所有 Linux 用户 (UID >= 1000)，包含管理员，带详细信息。"""
    entries = _iter_linux_users(include_admin=True)
    groups_cache = _group_cache(entries)
    users = []
    for entry in entries:
        lastlog = run_command_text(
            ["lastlog", "-u", entry.pw_name],
            timeout=10,
            check=False,
        )
        last_login = "从未登录"
        lines = [line for line in lastlog.splitlines() if line.strip()]
        if len(lines) >= 2 and "Never logged in" not in lines[-1]:
            cols = lines[-1].split(None, 3)
            if len(cols) >= 4 and cols[0] == entry.pw_name:
                last_login = cols[3]

        users.append(
            {
                "name": entry.pw_name,
                "uid": entry.pw_uid,
                "home": entry.pw_dir,
                "shell": entry.pw_shell,
                "groups": groups_cache.get(entry.pw_name, ""),
                "last_login": last_login,
                "is_admin": entry.pw_name in settings.admin_linux_users,
            }
        )
    users.sort(key=lambda item: item["uid"])
    return users


def get_user_login_history(username: str = "", count: int = 20) -> list[dict]:
    """获取用户登录历史（基于 last 命令）。"""
    if username and not _USERNAME_RE.match(username):
        raise ValueError(f"无效的用户名: {username}")

    command = ["last", "-n", str(min(count, 100)), "-F", "-w"]
    if username:
        command.append(username)
    raw = run_command_text(command, timeout=10, check=False)

    entries = []
    for line in raw.splitlines():
        if not line.strip() or line.startswith("wtmp begins") or line.startswith("reboot"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        entries.append(
            {
                "username": parts[0],
                "tty": parts[1],
                "source": parts[2] if not parts[2].startswith(":") or len(parts) > 9 else "",
                "raw": line.strip(),
            }
        )
    return entries[:count]


def get_active_sessions() -> list[dict]:
    """获取当前活跃登录会话（基于 who 命令）。"""
    raw = run_command_text(["who"], timeout=10, check=False)
    sessions = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            sessions.append(
                {
                    "username": parts[0],
                    "tty": parts[1],
                    "login_time": " ".join(parts[2:4]) if len(parts) >= 4 else parts[2],
                    "source": parts[4].strip("()") if len(parts) >= 5 else "",
                }
            )
    return sessions


def create_linux_user(username: str, groups: str = "", shell: str = "/bin/bash") -> dict:
    """创建新的 Linux 用户。"""
    _validate_new_username(username)
    if _user_exists(username):
        return {"ok": False, "error": f"用户 {username} 已存在"}
    if shell not in _ALLOWED_SHELLS:
        return {"ok": False, "error": f"不允许的 shell: {shell}"}

    command = ["sudo", "useradd", "-m", "-s", shell]
    if groups:
        for group_name in groups.split(","):
            group_name = group_name.strip()
            if group_name and not _USERNAME_RE.match(group_name):
                return {"ok": False, "error": f"无效的组名: {group_name}"}
        command.extend(["-G", groups])
    command.append(username)

    try:
        result = run_command(command, timeout=10, check=False)
        if result.returncode != 0:
            return {"ok": False, "error": result.output}
        return {"ok": True, "error": None}
    except Exception as exc:
        logger.exception("创建 Linux 用户失败: %s", username)
        return {"ok": False, "error": str(exc)}


def delete_linux_user(username: str, remove_home: bool = False) -> dict:
    """删除 Linux 用户。"""
    if not _USERNAME_RE.match(username):
        return {"ok": False, "error": "用户名不合法"}
    if username in settings.admin_linux_users:
        return {"ok": False, "error": "不能删除管理员用户"}
    if not _user_exists(username):
        return {"ok": False, "error": f"用户 {username} 不存在"}

    command = ["sudo", "userdel"]
    if remove_home:
        command.append("-r")
    command.append(username)

    try:
        result = run_command(command, timeout=10, check=False)
        if result.returncode != 0:
            return {"ok": False, "error": result.output}
        return {"ok": True, "error": None}
    except Exception as exc:
        logger.exception("删除 Linux 用户失败: %s", username)
        return {"ok": False, "error": str(exc)}


def modify_linux_user(username: str, groups: str = None, shell: str = None) -> dict:
    """修改用户属性（组、shell）。"""
    if not _USERNAME_RE.match(username):
        return {"ok": False, "error": "用户名不合法"}
    if username in settings.admin_linux_users:
        return {"ok": False, "error": "不能修改管理员用户"}

    command = ["sudo", "usermod"]
    if groups is not None:
        for group_name in groups.split(","):
            group_name = group_name.strip()
            if group_name and not _USERNAME_RE.match(group_name):
                return {"ok": False, "error": f"无效的组名: {group_name}"}
        command.extend(["-G", groups])
    if shell is not None:
        if shell not in _ALLOWED_SHELLS:
            return {"ok": False, "error": f"不允许的 shell: {shell}"}
        command.extend(["-s", shell])
    command.append(username)

    if len(command) <= 3:
        return {"ok": False, "error": "未指定要修改的属性"}

    try:
        result = run_command(command, timeout=10, check=False)
        if result.returncode != 0:
            return {"ok": False, "error": result.output}
        return {"ok": True, "error": None}
    except Exception as exc:
        logger.exception("修改 Linux 用户失败: %s", username)
        return {"ok": False, "error": str(exc)}


def set_user_password(username: str, password: str) -> dict:
    """设置用户密码。"""
    if not _USERNAME_RE.match(username):
        return {"ok": False, "error": "用户名不合法"}
    if username in settings.admin_linux_users:
        return {"ok": False, "error": "不能修改管理员密码"}
    if len(password) < 6:
        return {"ok": False, "error": "密码长度至少 6 个字符"}

    try:
        result = run_command(
            ["sudo", "chpasswd"],
            timeout=10,
            check=False,
            input_text=f"{username}:{password}",
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.output}
        return {"ok": True, "error": None}
    except Exception as exc:
        logger.exception("设置 Linux 用户密码失败: %s", username)
        return {"ok": False, "error": str(exc)}


def kill_single_process(pid: int, username: str) -> dict:
    """终止指定用户的单个进程。"""
    if username in settings.admin_linux_users:
        return {"ok": False, "error": "不能终止管理员进程"}

    try:
        process = psutil.Process(pid)
        process_user = process.username()
    except psutil.NoSuchProcess:
        return {"ok": False, "error": f"进程 {pid} 不存在"}
    except (psutil.AccessDenied, psutil.ZombieProcess) as exc:
        return {"ok": False, "error": str(exc)}

    if process_user != username:
        return {"ok": False, "error": f"进程 {pid} 不属于用户 {username}"}

    try:
        subprocess.run(["kill", str(pid)], timeout=5, check=False)
        return {"ok": True, "error": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


# ─── 进程列表 & 配额状态 & 处置引擎 ───

def get_user_processes(username: str, sort_by: str = "mem", search: str = "") -> list[dict]:
    """获取指定用户的完整进程列表"""
    import time

    procs = []
    now = time.time()
    for p in psutil.process_iter(["pid", "username", "memory_info", "cpu_percent", "name", "cmdline", "create_time"]):
        try:
            info = p.info
            if (info.get("username") or "") != username:
                continue
            rss = info["memory_info"].rss if info.get("memory_info") else 0
            create_time = info.get("create_time") or now
            elapsed_sec = max(0, now - create_time)
            # 人类可读时长
            if elapsed_sec < 60:
                elapsed = f"{int(elapsed_sec)}s"
            elif elapsed_sec < 3600:
                elapsed = f"{int(elapsed_sec // 60)}m"
            elif elapsed_sec < 86400:
                elapsed = f"{int(elapsed_sec // 3600)}h{int((elapsed_sec % 3600) // 60)}m"
            else:
                elapsed = f"{int(elapsed_sec // 86400)}d{int((elapsed_sec % 86400) // 3600)}h"

            cmdline = " ".join(info.get("cmdline") or [])[:200]
            name = info.get("name") or ""

            if search and search.lower() not in name.lower() and search.lower() not in cmdline.lower():
                continue

            procs.append({
                "pid": info["pid"],
                "name": name,
                "cmdline": cmdline,
                "mem_mb": round(rss / 1024 / 1024, 1),
                "cpu_percent": info.get("cpu_percent") or 0.0,
                "elapsed": elapsed,
                "elapsed_sec": elapsed_sec,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    sort_key = {"mem": "mem_mb", "cpu": "cpu_percent", "time": "elapsed_sec", "name": "name"}.get(sort_by, "mem_mb")
    reverse = sort_by != "name"
    procs.sort(key=lambda x: x.get(sort_key, 0), reverse=reverse)
    return procs


def get_quota_status() -> dict:
    """获取所有用户的配额使用状态（含聚合统计）"""
    users = get_user_stats()
    quotas = read_quotas()

    results = []
    over_quota_count = 0
    warning_count = 0
    total_mem_gb = 0.0

    for u in users:
        total_mem_gb += u["mem_gb"]
        q = get_user_quota(u["name"], u.get("groups", ""), quotas)
        mem_limit = q.get("mem_gb", 0) if q else 0
        proc_limit = q.get("proc_limit", 0) if q else 0

        mem_pct = round(u["mem_gb"] / mem_limit * 100, 1) if mem_limit > 0 else 0
        proc_pct = round(u["proc_count"] / proc_limit * 100, 1) if proc_limit > 0 else 0
        max_pct = max(mem_pct, proc_pct)

        if max_pct >= 100:
            status = "critical"
            over_quota_count += 1
        elif max_pct >= 75:
            status = "warning"
            warning_count += 1
        else:
            status = "normal"

        results.append({
            **u,
            "mem_usage_pct": mem_pct,
            "proc_usage_pct": proc_pct,
            "status": status,
            "quota": q,
        })

    return {
        "users": results,
        "over_quota_count": over_quota_count,
        "warning_count": warning_count,
        "total_mem_gb": round(total_mem_gb, 1),
    }


def get_enforcement_config() -> dict:
    """读取处置策略配置"""
    import json
    config_path = Path(settings.db_path).parent / "enforcement-config.json"
    defaults = {
        "enabled": True,
        "mode": "notify",
        "warning_pct": 75,
        "critical_pct": 100,
        "kill_pct": 120,
        "grace_minutes": 5,
        "cooldown_minutes": 30,
    }
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            defaults.update(data)
        except Exception:
            pass
    return defaults


def save_enforcement_config(config: dict):
    """保存处置策略配置"""
    import json
    config_path = Path(settings.db_path).parent / "enforcement-config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


async def check_and_enforce_quotas():
    """配额处置引擎 — 由调度器每 60s 调用"""
    import json
    from datetime import datetime, timedelta
    from database import get_db

    config = get_enforcement_config()
    if not config.get("enabled"):
        return

    users = get_user_stats()
    quotas = read_quotas()
    db = await get_db()
    now = datetime.now()

    for u in users:
        username = u["name"]
        if username in settings.admin_linux_users:
            continue

        q = get_user_quota(username, quotas)
        if not q:
            continue

        mem_limit = q.get("mem_gb", 0)
        if mem_limit <= 0:
            continue

        mem_pct = u["mem_gb"] / mem_limit * 100
        violation_type = None

        if mem_pct >= config.get("kill_pct", 120):
            violation_type = "kill"
        elif mem_pct >= config.get("critical_pct", 100):
            violation_type = "critical"
        elif mem_pct >= config.get("warning_pct", 75):
            violation_type = "warning"

        if not violation_type:
            continue

        # 检查冷却期
        cooldown = config.get("cooldown_minutes", 30)
        cursor = await db.execute(
            "SELECT notified_at, first_detected_at FROM quota_violations "
            "WHERE username = ? AND violation_type = ? ORDER BY created_at DESC LIMIT 1",
            (username, violation_type),
        )
        last = await cursor.fetchone()

        in_cooldown = False
        first_detected = now
        if last:
            if last[0]:
                notified_time = datetime.fromisoformat(last[0])
                if now - notified_time < timedelta(minutes=cooldown):
                    in_cooldown = True
            if last[1]:
                first_detected = datetime.fromisoformat(last[1])

        action_taken = None

        # Level 3: 自动 kill（仅 auto_kill 模式 + 超过 grace period）
        if violation_type == "kill" and config.get("mode") == "auto_kill":
            grace = config.get("grace_minutes", 5)
            if (now - first_detected).total_seconds() >= grace * 60:
                # Kill 最耗内存的进程
                top_procs = u.get("top_procs", [])
                if top_procs:
                    top_pid = top_procs[0]["pid"]
                    result = kill_single_process(top_pid, username)
                    action_taken = f"killed_pid:{top_pid}" if result.get("ok") else f"kill_failed:{top_pid}"

        # 发送通知（不在冷却期内）
        if not in_cooldown:
            try:
                from modules.notifications.services import send_to_all_channels
                level_names = {"warning": "预警", "critical": "告警", "kill": "强制处置"}
                msg = (
                    f"[配额{level_names.get(violation_type, '通知')}] 用户 {username} "
                    f"内存使用 {u['mem_gb']:.1f}GB / 配额 {mem_limit}GB ({mem_pct:.0f}%)"
                )
                if action_taken and action_taken.startswith("killed"):
                    msg += f"\n已自动终止进程 PID {top_procs[0]['pid']} ({top_procs[0]['name']})"
                await send_to_all_channels(msg)
                action_taken = action_taken or "notified"
            except Exception as e:
                logger.warning(f"配额通知发送失败: {e}")
                action_taken = action_taken or "notify_failed"

        # 记录违规
        await db.execute(
            "INSERT INTO quota_violations (username, violation_type, mem_gb, quota_mem_gb, usage_pct, action_taken, first_detected_at, notified_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (username, violation_type, u["mem_gb"], mem_limit, round(mem_pct, 1),
             action_taken, first_detected.isoformat(), now.isoformat() if not in_cooldown else None),
        )
        await db.commit()

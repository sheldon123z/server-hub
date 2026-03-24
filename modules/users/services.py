"""
Linux 用户与配额管理服务
移植自 server-panel.py 的核心逻辑 + 用户生命周期管理
"""

import os
import re
import subprocess
from datetime import datetime

from config import settings

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _run(cmd: str) -> str:
    """执行 shell 命令并返回 stdout"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


def get_linux_users() -> list[dict]:
    """
    获取 Linux 普通用户列表 (UID >= 1000)，排除管理员
    返回 [{name, uid, groups}, ...]
    """
    admin_users = set(settings.admin_linux_users)
    users = []

    passwd_raw = _run("awk -F: '$3 >= 1000 {print $1, $3}' /etc/passwd")
    for line in passwd_raw.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in admin_users:
            uname = parts[0]
            uid = int(parts[1])
            groups = _run(f"id -Gn {uname} 2>/dev/null")
            users.append({"name": uname, "uid": uid, "groups": groups})

    return users


def get_user_stats() -> list[dict]:
    """
    获取每用户资源使用统计（移植自 server-panel.py）
    包含: 内存、进程数、GPU 显存、Top 进程
    """
    admin_users = set(settings.admin_linux_users)

    # --- 1. 一次性 ps 获取所有进程的 user, pid, rss, comm ---
    all_procs: dict[str, list[tuple[int, int, str]]] = {}
    ps_raw = _run("ps -eo user=,pid=,rss=,comm= --no-headers 2>/dev/null")
    for line in ps_raw.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        uname, pid, rss, comm = parts[0], int(parts[1]), int(parts[2]), parts[3]
        if uname not in all_procs:
            all_procs[uname] = []
        all_procs[uname].append((pid, rss, comm))

    # --- 2. 一次性查 GPU 进程映射 ---
    gpu_user_mem: dict[str, int] = {}
    gpu_procs_raw = _run(
        "nvidia-smi --query-compute-apps=pid,used_gpu_memory "
        "--format=csv,noheader,nounits 2>/dev/null"
    )
    if gpu_procs_raw:
        # 建 pid -> user 映射
        pid_user: dict[int, str] = {}
        for uname, procs in all_procs.items():
            for pid, _, _ in procs:
                pid_user[pid] = uname
        for gline in gpu_procs_raw.splitlines():
            gparts = [x.strip() for x in gline.split(",")]
            if len(gparts) >= 2:
                gpid = int(gparts[0])
                owner = pid_user.get(gpid, "")
                if owner:
                    gpu_user_mem[owner] = gpu_user_mem.get(owner, 0) + int(gparts[1])

    # --- 3. 构建每用户数据 ---
    users = []
    passwd = _run("awk -F: '$3 >= 1000 {print $1, $3}' /etc/passwd")

    # 批量获取所有用户的组信息 (单次 shell 调用)
    user_list: list[tuple[str, int]] = []
    for line in passwd.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] not in admin_users:
            user_list.append((parts[0], int(parts[1])))

    unames = [u for u, _ in user_list]
    groups_cmd = (
        " && ".join([f'echo "{u}:$(id -Gn {u} 2>/dev/null)"' for u in unames])
        if unames
        else "true"
    )
    groups_raw = _run(groups_cmd) if unames else ""
    groups_cache: dict[str, str] = {}
    for gline in groups_raw.splitlines():
        if ":" in gline:
            k, v = gline.split(":", 1)
            groups_cache[k] = v

    for uname, uid in user_list:
        user_procs = all_procs.get(uname, [])
        proc_count = len(user_procs)
        mem_kb = sum(rss for _, rss, _ in user_procs)
        mem_gb = round(mem_kb / 1024 / 1024, 1)

        # top 3 by RSS
        top_sorted = sorted(user_procs, key=lambda x: x[1], reverse=True)[:3]
        top_procs = [
            {"pid": p, "mem_mb": round(r / 1024, 1), "name": c}
            for p, r, c in top_sorted
        ]

        users.append({
            "name": uname,
            "uid": uid,
            "groups": groups_cache.get(uname, ""),
            "mem_gb": mem_gb,
            "proc_count": proc_count,
            "gpu_mem_mb": gpu_user_mem.get(uname, 0),
            "top_procs": top_procs,
        })

    users.sort(key=lambda x: x["mem_gb"], reverse=True)
    return users


def read_quotas() -> list[dict]:
    """
    读取配额配置文件
    格式: key mem_gb proc_limit # comment
    """
    quotas = []
    quota_file = settings.quota_file
    if not os.path.exists(quota_file):
        return quotas
    with open(quota_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                comment = ""
                if "#" in line:
                    comment = line.split("#", 1)[1].strip()
                quotas.append({
                    "key": parts[0],
                    "mem_gb": int(parts[1]),
                    "proc_limit": int(parts[2]),
                    "comment": comment,
                })
    return quotas


def save_quotas(quotas: list[dict]):
    """将配额列表写回配置文件"""
    lines = [
        "# 用户资源配额配置",
        "# 格式: 用户名或@组名  内存上限(GB)  进程上限  说明",
        "# 优先级: 用户名 > @组名 > default",
        "",
    ]
    for q in quotas:
        comment = f"  # {q['comment']}" if q.get("comment") else ""
        lines.append(f"{q['key']:<18}{q['mem_gb']:<8}{q['proc_limit']:<8}{comment}")
    with open(settings.quota_file, "w") as f:
        f.write("\n".join(lines) + "\n")


def get_user_quota(username: str, groups_str: str, quotas: list[dict]) -> dict | None:
    """
    三级配额匹配: 精确用户名 > @组名 > default

    Args:
        username: Linux 用户名
        groups_str: 空格分隔的组名字符串
        quotas: 配额列表
    """
    # 1. 精确用户名匹配
    for q in quotas:
        if q["key"] == username:
            return q

    # 2. @组名匹配
    if groups_str:
        for g in groups_str.split():
            for q in quotas:
                if q["key"] == f"@{g}":
                    return q

    # 3. default 匹配
    for q in quotas:
        if q["key"] == "default":
            return q

    return None


def kill_user_processes(username: str) -> dict:
    """
    终止指定用户的所有进程
    先 pkill -u，再 pkill -9 -u 强制清理

    Returns:
        {"ok": True/False, "error": str | None}
    """
    admin_users = set(settings.admin_linux_users)

    # 安全检查: 不能杀管理员
    if username in admin_users:
        return {"ok": False, "error": "不能终止管理员进程"}

    # 安全检查: 用户名合法性
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        return {"ok": False, "error": "用户名不合法"}

    try:
        subprocess.run(["pkill", "-u", username], timeout=5)
        subprocess.run(["pkill", "-9", "-u", username], timeout=5)
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── 用户全量列表（含管理员） ───

def get_all_linux_users() -> list[dict]:
    """获取所有 Linux 用户 (UID >= 1000)，包含管理员，带详细信息"""
    users = []
    passwd_raw = _run("awk -F: '$3 >= 1000 {print $1\":\"$3\":\"$6\":\"$7}' /etc/passwd")
    for line in passwd_raw.splitlines():
        parts = line.split(":")
        if len(parts) < 4:
            continue
        uname, uid, home, shell = parts[0], int(parts[1]), parts[2], parts[3]
        groups = _run(f"id -Gn {uname} 2>/dev/null")
        last_login = _run(f"lastlog -u {uname} 2>/dev/null | tail -1")
        # lastlog 输出格式: Username  Port  From  Latest
        login_info = ""
        if last_login and "Never logged in" not in last_login:
            # 跳过 header 行
            cols = last_login.split(None, 3)
            if len(cols) >= 4 and cols[0] == uname:
                login_info = cols[3]  # Latest 部分

        users.append({
            "name": uname,
            "uid": uid,
            "home": home,
            "shell": shell,
            "groups": groups,
            "last_login": login_info or "从未登录",
            "is_admin": uname in settings.admin_linux_users,
        })
    users.sort(key=lambda x: x["uid"])
    return users


# ─── 登录历史 ───

def get_user_login_history(username: str = "", count: int = 20) -> list[dict]:
    """获取用户登录历史（基于 last 命令）

    Args:
        username: 留空则查询所有用户
        count: 最大返回条数
    """
    if username and not _USERNAME_RE.match(username):
        raise ValueError(f"无效的用户名: {username}")

    cmd = f"last -n {min(count, 100)} -F -w"
    if username:
        cmd += f" {username}"
    cmd += " 2>/dev/null"
    raw = _run(cmd)

    entries = []
    for line in raw.splitlines():
        if not line.strip() or line.startswith("wtmp begins") or line.startswith("reboot"):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        entries.append({
            "username": parts[0],
            "tty": parts[1],
            "source": parts[2] if not parts[2].startswith(":") or len(parts) > 9 else "",
            "raw": line.strip(),
        })
    return entries[:count]


def get_active_sessions() -> list[dict]:
    """获取当前活跃登录会话（基于 who 命令）"""
    raw = _run("who 2>/dev/null")
    sessions = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            sessions.append({
                "username": parts[0],
                "tty": parts[1],
                "login_time": " ".join(parts[2:4]) if len(parts) >= 4 else parts[2],
                "source": parts[4].strip("()") if len(parts) >= 5 else "",
            })
    return sessions


# ─── 用户增删改 ───

def _validate_new_username(username: str):
    """校验用户名合法性"""
    if not _USERNAME_RE.match(username):
        raise ValueError(f"用户名格式不合法: {username}")
    if len(username) < 2 or len(username) > 32:
        raise ValueError("用户名长度需在 2-32 字符之间")


def create_linux_user(username: str, groups: str = "", shell: str = "/bin/bash") -> dict:
    """创建新的 Linux 用户

    Args:
        username: 用户名
        groups: 逗号分隔的附加组（如 "students,docker"）
        shell: 登录 shell
    """
    _validate_new_username(username)

    # 检查是否已存在
    check = _run(f"id {username} 2>/dev/null")
    if check:
        return {"ok": False, "error": f"用户 {username} 已存在"}

    # shell 白名单
    allowed_shells = {"/bin/bash", "/bin/sh", "/bin/zsh", "/usr/bin/zsh", "/usr/sbin/nologin", "/bin/false"}
    if shell not in allowed_shells:
        return {"ok": False, "error": f"不允许的 shell: {shell}"}

    cmd = ["sudo", "useradd", "-m", "-s", shell]
    if groups:
        # 验证组名
        for g in groups.split(","):
            g = g.strip()
            if g and not _USERNAME_RE.match(g):
                return {"ok": False, "error": f"无效的组名: {g}"}
        cmd.extend(["-G", groups])
    cmd.append(username)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.strip()}
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def delete_linux_user(username: str, remove_home: bool = False) -> dict:
    """删除 Linux 用户

    Args:
        username: 要删除的用户名
        remove_home: 是否同时删除 home 目录
    """
    if not _USERNAME_RE.match(username):
        return {"ok": False, "error": "用户名不合法"}

    if username in settings.admin_linux_users:
        return {"ok": False, "error": "不能删除管理员用户"}

    # 检查用户是否存在
    check = _run(f"id {username} 2>/dev/null")
    if not check:
        return {"ok": False, "error": f"用户 {username} 不存在"}

    cmd = ["sudo", "userdel"]
    if remove_home:
        cmd.append("-r")
    cmd.append(username)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.strip()}
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def modify_linux_user(username: str, groups: str = None, shell: str = None) -> dict:
    """修改用户属性（组、shell）"""
    if not _USERNAME_RE.match(username):
        return {"ok": False, "error": "用户名不合法"}

    if username in settings.admin_linux_users:
        return {"ok": False, "error": "不能修改管理员用户"}

    cmd = ["sudo", "usermod"]
    if groups is not None:
        for g in groups.split(","):
            g = g.strip()
            if g and not _USERNAME_RE.match(g):
                return {"ok": False, "error": f"无效的组名: {g}"}
        cmd.extend(["-G", groups])
    if shell is not None:
        allowed_shells = {"/bin/bash", "/bin/sh", "/bin/zsh", "/usr/bin/zsh", "/usr/sbin/nologin", "/bin/false"}
        if shell not in allowed_shells:
            return {"ok": False, "error": f"不允许的 shell: {shell}"}
        cmd.extend(["-s", shell])
    cmd.append(username)

    if len(cmd) <= 3:
        return {"ok": False, "error": "未指定要修改的属性"}

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.strip()}
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def set_user_password(username: str, password: str) -> dict:
    """设置用户密码"""
    if not _USERNAME_RE.match(username):
        return {"ok": False, "error": "用户名不合法"}

    if username in settings.admin_linux_users:
        return {"ok": False, "error": "不能修改管理员密码"}

    if len(password) < 6:
        return {"ok": False, "error": "密码长度至少 6 个字符"}

    try:
        r = subprocess.run(
            ["sudo", "chpasswd"],
            input=f"{username}:{password}",
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return {"ok": False, "error": r.stderr.strip()}
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ─── 单进程终止 ───

def kill_single_process(pid: int, username: str) -> dict:
    """终止指定用户的单个进程

    Args:
        pid: 进程 ID
        username: 进程所属用户（用于校验）
    """
    if username in settings.admin_linux_users:
        return {"ok": False, "error": "不能终止管理员进程"}

    # 验证 PID 归属
    proc_user = _run(f"ps -o user= -p {pid} 2>/dev/null").strip()
    if not proc_user:
        return {"ok": False, "error": f"进程 {pid} 不存在"}
    if proc_user != username:
        return {"ok": False, "error": f"进程 {pid} 不属于用户 {username}"}

    try:
        subprocess.run(["kill", str(pid)], timeout=5)
        return {"ok": True, "error": None}
    except Exception as e:
        return {"ok": False, "error": str(e)}

"""
Linux 用户与配额管理服务
移植自 server-panel.py 的核心逻辑
"""

import os
import re
import subprocess

from config import settings


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

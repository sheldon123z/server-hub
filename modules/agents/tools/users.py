"""用户资源与管理工具"""

from langchain_core.tools import tool


@tool
async def get_user_resources(server_id: str = "local") -> str:
    """获取所有用户的资源使用情况：内存、进程数、GPU显存。

    Args:
        server_id: 目标服务器ID。'local' 表示本机。
    """
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client

        client = await get_agent_client(server_id)
        result = await client.user_stats()
        if not result.get("ok"):
            return f"远程获取失败: {result.get('error', '未知')}"
        users = result["data"].get("users", [])
        if not users:
            return f"服务器 {server_id} 没有用户进程信息。"
        lines = [f"## 服务器 {server_id} 用户资源\n| 用户 | 内存% | 内存(GB) |", "|---|---|---|"]
        for u in users[:20]:
            lines.append(f"| {u['username']} | {u['mem_percent']} | {u['mem_gb']} |")
        return "\n".join(lines)

    from modules.users.services import get_user_stats

    users = get_user_stats()
    if not users:
        return "当前没有活跃的非管理员用户。"
    lines = ["## 用户资源使用\n| 用户 | 内存(GB) | 进程数 | GPU显存(MiB) |", "|---|---|---|---|"]
    for u in users:
        lines.append(f"| {u['name']} | {u['mem_gb']} | {u['proc_count']} | {u.get('gpu_mem_mb', 0)} |")
    return "\n".join(lines)


@tool
def get_user_quotas() -> str:
    """获取所有用户资源配额配置。"""
    from modules.users.services import read_quotas

    quotas = read_quotas()
    if not quotas:
        return "没有配置配额。"
    lines = ["## 用户配额\n| 标识 | 内存上限(GB) | 进程上限 | 备注 |", "|---|---|---|---|"]
    for q in quotas:
        lines.append(f"| {q['key']} | {q['mem_gb']} | {q['proc_limit']} | {q.get('comment', '')} |")
    return "\n".join(lines)


@tool
def update_user_quotas(key: str, mem_gb: int, proc_limit: int, comment: str = "") -> str:
    """修改用户资源配额。

    Args:
        key: 用户名或@组名（如 wangtao 或 @students）
        mem_gb: 内存上限（GB）
        proc_limit: 进程数上限
        comment: 备注说明
    """
    from modules.users.services import read_quotas, save_quotas

    quotas = read_quotas()
    found = False
    for q in quotas:
        if q["key"] == key:
            q["mem_gb"] = mem_gb
            q["proc_limit"] = proc_limit
            if comment:
                q["comment"] = comment
            found = True
            break
    if not found:
        quotas.append({"key": key, "mem_gb": mem_gb, "proc_limit": proc_limit, "comment": comment})
    save_quotas(quotas)
    return f"配额已更新: {key} → 内存 {mem_gb}GB, 进程 {proc_limit}"


@tool
async def kill_user_processes(username: str, server_id: str = "local") -> str:
    """终止指定用户的所有进程。不能终止管理员用户的进程。

    Args:
        username: 要终止进程的用户名
        server_id: 目标服务器ID。'local' 表示本机。
    """
    if server_id != "local":
        # 注意: pkill -u 不在结构化端点中，但远程 kill 单进程可用
        # 这里保留警告，建议逐个 kill 进程
        return (
            f"远程批量终止用户进程暂不支持。请使用 kill_single_process_tool 逐个终止 "
            f"服务器 {server_id} 上用户 {username} 的进程。"
        )

    from modules.users.services import kill_user_processes as _kill

    result = _kill(username)
    if result.get("ok"):
        return f"已终止用户 {username} 的所有进程。"
    return f"操作失败: {result.get('error', '未知错误')}"


@tool
def get_user_login_history_tool(username: str = "", count: int = 10) -> str:
    """查询 Linux 用户登录历史。"""
    from modules.users.services import get_user_login_history

    entries = get_user_login_history(username, min(count, 50))
    if not entries:
        target = username or "所有用户"
        return f"{target} 没有登录记录"
    lines = [f"## 登录历史 ({len(entries)} 条)\n"]
    for e in entries:
        lines.append(f"- {e['raw']}")
    return "\n".join(lines)


@tool
def get_active_sessions_tool() -> str:
    """获取当前服务器上的活跃登录会话。"""
    from modules.users.services import get_active_sessions

    sessions = get_active_sessions()
    if not sessions:
        return "当前没有活跃的登录会话"
    lines = [f"## 活跃会话 ({len(sessions)} 个)\n"]
    for s in sessions:
        source = f" (来自 {s['source']})" if s["source"] else ""
        lines.append(f"- **{s['username']}** @ {s['tty']} — {s['login_time']}{source}")
    return "\n".join(lines)


@tool
def manage_linux_user(action: str, username: str, groups: str = "", shell: str = "/bin/bash") -> str:
    """管理 Linux 用户：创建、删除或修改。"""
    from modules.users.services import create_linux_user, delete_linux_user, modify_linux_user

    if action == "create":
        result = create_linux_user(username, groups, shell)
    elif action == "delete":
        result = delete_linux_user(username, remove_home=False)
    elif action == "modify":
        result = modify_linux_user(username, groups=groups or None, shell=shell if shell != "/bin/bash" else None)
    else:
        return f"不支持的操作: {action}"
    if result["ok"]:
        return f"已成功执行 {action} 用户 {username}"
    return f"操作失败: {result['error']}"


@tool
def kill_single_process_tool(pid: int, username: str) -> str:
    """终止指定用户的单个进程。"""
    from modules.users.services import kill_single_process

    result = kill_single_process(pid, username)
    if result["ok"]:
        return f"已终止进程 {pid} (用户: {username})"
    return f"终止失败: {result['error']}"


@tool
def get_user_full_processes(username: str) -> str:
    """获取指定用户的完整进程列表，包含 PID、命令、CPU%、内存、运行时长。"""
    from modules.users.services import get_user_processes

    procs = get_user_processes(username)
    if not procs:
        return f"用户 {username} 无运行中的进程"
    lines = [f"用户 {username} 的进程列表 ({len(procs)} 个):", ""]
    lines.append("| PID | 进程名 | 内存(MB) | CPU% | 运行时长 |")
    lines.append("|-----|--------|---------|------|---------|")
    for p in procs[:50]:
        lines.append(f"| {p['pid']} | {p['name'][:20]} | {p['mem_mb']} | {p['cpu_percent']:.1f} | {p['elapsed']} |")
    if len(procs) > 50:
        lines.append(f"\n... 共 {len(procs)} 个进程，仅显示前 50 个")
    return "\n".join(lines)


@tool
def check_quota_violations() -> str:
    """检查所有用户的配额使用情况，返回超配额和接近配额的用户列表。"""
    from modules.users.services import get_quota_status

    qs = get_quota_status()
    lines = [
        f"配额状态概览: 超配额 {qs['over_quota_count']} 人, 预警 {qs['warning_count']} 人, 总内存 {qs['total_mem_gb']} GB",
        "",
    ]

    abnormal = [u for u in qs["users"] if u["status"] != "normal"]
    if not abnormal:
        lines.append("所有用户配额使用正常。")
        return "\n".join(lines)

    lines.append("| 用户 | 内存使用 | 配额 | 使用率 | 状态 |")
    lines.append("|------|---------|------|-------|------|")
    for u in abnormal:
        q = u.get("quota")
        quota_str = f"{q['mem_gb']}GB" if q else "-"
        lines.append(f"| {u['name']} | {u['mem_gb']}GB | {quota_str} | {u['mem_usage_pct']}% | {u['status']} |")
    return "\n".join(lines)

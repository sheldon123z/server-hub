"""运维工具集 — 封装现有 services 为 LangChain @tool"""

import asyncio
import json
import re
from langchain_core.tools import tool
from config import settings


# ─── safe: 只读查询 ───

@tool
def get_system_overview() -> str:
    """获取系统状态概览：CPU使用率、内存、Swap、磁盘、GPU、负载、运行时间。"""
    from modules.dashboard.collectors import get_system_info
    info = get_system_info()
    gpu = info.get("gpu", {})
    gpu_str = f"GPU: {gpu['util']}% 利用率, {gpu['mem_used']}/{gpu['mem_total']}MiB 显存, {gpu['temp']}°C" if gpu else "GPU: 无"
    return (
        f"## 系统状态\n"
        f"- CPU: {info['cpu_percent']}% ({info['cpu_count']}核)\n"
        f"- 内存: {info['mem_percent']}% ({round(info['mem_used']/1073741824,1)}/{round(info['mem_total']/1073741824,1)} GB)\n"
        f"- Swap: {info['swap_percent']}% ({round(info['swap_used']/1073741824,1)}/{round(info['swap_total']/1073741824,1)} GB)\n"
        f"- 系统盘: {info['disk_percent']}% ({round(info['disk_used']/1073741824,1)}/{round(info['disk_total']/1073741824,1)} GB)\n"
        f"- 负载: {info['load']}\n"
        f"- {gpu_str}\n"
        f"- 运行时间: {info['uptime']}"
    )


@tool
def get_disk_info() -> str:
    """获取所有磁盘挂载点的使用情况。"""
    from modules.dashboard.collectors import get_extra_disks
    disks = get_extra_disks()
    if not disks:
        return "没有额外的挂载点。"
    lines = ["## 磁盘挂载点"]
    for d in disks:
        lines.append(f"- {d['mountpoint']} ({d['device']}): {d['percent']}% "
                      f"({round(d['used']/1099511627776,2)}/{round(d['total']/1099511627776,2)} TB)")
    return "\n".join(lines)


@tool
def get_user_resources() -> str:
    """获取所有用户的资源使用情况：内存、进程数、GPU显存。"""
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
async def list_docker_containers() -> str:
    """列出所有 Docker 容器及其运行状态。"""
    from modules.docker.services import list_containers
    containers = await list_containers(all=True)
    if not containers:
        return "当前没有 Docker 容器。"
    lines = ["## Docker 容器\n| 容器 | 状态 | 镜像 |", "|---|---|---|"]
    for c in containers:
        name = c.get("Names") or c.get("name", "?")
        status = c.get("Status") or c.get("status", "?")
        image = c.get("Image") or c.get("image", "?")
        lines.append(f"| {name} | {status} | {image[:40]} |")
    return "\n".join(lines)


@tool
async def get_container_logs(name: str, tail: int = 50) -> str:
    """获取指定 Docker 容器的最近日志。

    Args:
        name: 容器名称
        tail: 获取最后多少行，默认50
    """
    from modules.docker.services import container_logs
    logs = await container_logs(name, tail=min(tail, 200))
    if not logs:
        return f"容器 {name} 没有日志输出。"
    return f"## {name} 日志 (最后{tail}行)\n```\n{logs[-3000:]}\n```"


@tool
async def list_systemd_services() -> str:
    """列出所有管理的 systemd 服务及其状态。"""
    from modules.services.services import list_services
    services = await list_services()
    if not services:
        return "没有管理的服务。"
    lines = ["## Systemd 服务\n| 服务 | 状态 | 启用 |", "|---|---|---|"]
    for s in services:
        status = "运行中" if s.get("active") else "已停止"
        enabled = "是" if s.get("enabled") else "否"
        lines.append(f"| {s['name']} | {status} | {enabled} |")
    return "\n".join(lines)


@tool
async def get_service_logs(name: str, lines: int = 50) -> str:
    """获取指定 systemd 服务的日志。

    Args:
        name: 服务名称（必须在管理列表中）
        lines: 获取最后多少行，默认50
    """
    if name not in settings.managed_services:
        return f"服务 {name} 不在管理列表中。可管理的服务: {', '.join(settings.managed_services)}"
    from modules.services.services import service_journal
    journal = await service_journal(name, lines=min(lines, 200))
    return f"## {name} 日志\n```\n{journal[-3000:]}\n```"


# ─── moderate: 可逆操作 ───

@tool
async def send_notification(message: str) -> str:
    """发送通知到所有启用的通知渠道（Telegram、企业微信、钉钉等）。

    Args:
        message: 消息内容
    """
    from modules.notifications.services import send_notification as broadcast_notification
    results = await broadcast_notification(message)
    success = sum(1 for r in results if r.get("success"))
    failed = len(results) - success
    if failed == 0:
        return f"通知已发送成功，共 {success} 个渠道。"
    return f"通知发送完成: {success} 个渠道成功, {failed} 个渠道失败。"


@tool
async def docker_container_action(name: str, action: str) -> str:
    """对 Docker 容器执行操作。

    Args:
        name: 容器名称
        action: 操作类型，可选 start, stop, restart
    """
    if action not in ("start", "stop", "restart"):
        return f"不支持的操作: {action}。可选: start, stop, restart"
    from modules.docker.services import container_action
    result = await container_action(name, action)
    return f"容器 {name} 已执行 {action}。{result}"


@tool
async def docker_compose_action(stack_name: str, action: str) -> str:
    """对 Docker Compose 堆栈执行操作。

    Args:
        stack_name: 堆栈名称 (dify, lobe, grid-autopilot)
        action: 操作类型，可选 up, down, restart, pull
    """
    if stack_name not in settings.compose_stacks:
        return f"未知堆栈: {stack_name}。可选: {', '.join(settings.compose_stacks.keys())}"
    if action not in ("up", "down", "restart", "pull"):
        return f"不支持的操作: {action}。可选: up, down, restart, pull"
    from modules.docker.services import compose_action
    result = await compose_action(stack_name, action)
    return f"堆栈 {stack_name} 已执行 {action}。{result}"


@tool
async def service_control(name: str, action: str) -> str:
    """管理 systemd 服务。

    Args:
        name: 服务名称（必须在管理列表中）
        action: 操作类型，可选 start, stop, restart
    """
    if name not in settings.managed_services:
        return f"服务 {name} 不在管理列表中。可管理: {', '.join(settings.managed_services)}"
    if action not in ("start", "stop", "restart"):
        return f"不支持的操作: {action}。可选: start, stop, restart"
    from modules.services.services import service_action
    result = await service_action(name, action)
    return f"服务 {name} 已执行 {action}。{result}"


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
async def execute_ops_script(script_key: str, args: list[str] = []) -> str:
    """执行注册的运维管理脚本。

    Args:
        script_key: 脚本标识（如 dify_manage, health_check, block_baidupan 等）
        args: 脚本参数列表
    """
    from scripts_bridge.registry import SCRIPT_REGISTRY
    if script_key not in SCRIPT_REGISTRY:
        available = ", ".join(SCRIPT_REGISTRY.keys())
        return f"未知脚本: {script_key}。可用: {available}"
    from scripts_bridge.executor import execute_script
    result = await execute_script(script_key, args, username="agent", ip="127.0.0.1")
    output = result.get("stdout", "")
    if result.get("exit_code", 1) != 0:
        output += f"\n[ERROR] {result.get('stderr', '')}"
    return f"脚本 {script_key} 执行结果:\n```\n{output[:3000]}\n```"


# ─── danger: 高风险操作 ───

@tool
def kill_user_processes(username: str) -> str:
    """终止指定用户的所有进程。不能终止管理员用户的进程。

    Args:
        username: 要终止进程的用户名
    """
    from modules.users.services import kill_user_processes as _kill
    result = _kill(username)
    if result.get("ok"):
        return f"已终止用户 {username} 的所有进程。"
    return f"操作失败: {result.get('error', '未知错误')}"


# run_shell_command 已删除 — 被 Deep Agents 内置的 execute (持久化 Shell 会话) 替代


# ─── 工具注册表 ───

def get_server_tools() -> list:
    """返回所有服务器管理工具（15 个）

    Deep Agents 还会自动注入内置工具:
    - execute (持久化 Shell)
    - read_file / write_file / edit_file (文件操作)
    - ls / glob / grep (文件搜索)
    - write_todos (任务规划)
    - task (子智能体)
    """
    return [
        get_system_overview,
        get_disk_info,
        get_user_resources,
        get_user_quotas,
        list_docker_containers,
        get_container_logs,
        list_systemd_services,
        get_service_logs,
        send_notification,
        docker_container_action,
        docker_compose_action,
        service_control,
        update_user_quotas,
        execute_ops_script,
        kill_user_processes,
    ]


# 向后兼容
get_all_tools = get_server_tools

"""页面上下文提供器 — 为 AI 智能体注入当前页面感知信息

每个页面注册一个 provider 函数，返回 10-15 行的文本摘要。
当用户通过页面内气泡对话框发送消息时，该上下文作为系统消息注入 agent 输入。
"""

import asyncio
import logging
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

# 注册表: page_name -> async provider function
_providers: dict[str, Callable[[], Awaitable[str]]] = {}


def register(page_name: str, provider: Callable[[], Awaitable[str]]):
    """注册页面上下文提供器"""
    _providers[page_name] = provider


async def get_page_context(page_name: str) -> str:
    """获取指定页面的实时数据摘要"""
    provider = _providers.get(page_name)
    if not provider:
        return ""
    try:
        return await provider()
    except Exception as e:
        logger.warning("页面上下文获取失败 [%s]: %s", page_name, e)
        return ""


# ─── Provider 实现 ───


async def _dashboard_context() -> str:
    from modules.dashboard.collectors import get_system_info
    info = await asyncio.get_event_loop().run_in_executor(None, get_system_info)
    gpu = info.get("gpu", {})
    gpu_line = (
        f"GPU: 利用率 {gpu['util']}%, 显存 {gpu['mem_used']}/{gpu['mem_total']}MiB, 温度 {gpu['temp']}°C"
        if gpu else "GPU: 无"
    )
    return (
        f"[当前页面: 仪表盘]\n"
        f"CPU: {info['cpu_percent']}% ({info['cpu_count']}核), 负载: {info['load']}\n"
        f"内存: {info['mem_percent']}% ({round(info['mem_used']/1073741824,1)}/{round(info['mem_total']/1073741824,1)} GB)\n"
        f"Swap: {info['swap_percent']}%\n"
        f"根分区: {info['disk_percent']}%\n"
        f"{gpu_line}\n"
        f"运行时间: {info['uptime']}\n"
        f"用户正在查看系统仪表盘，可帮助分析系统状态、定位性能瓶颈。"
    )


async def _monitoring_context() -> str:
    from modules.monitoring.collectors import collect_realtime_fast
    data = await asyncio.get_event_loop().run_in_executor(None, collect_realtime_fast)
    cpu = data.get("cpu", {})
    mem = data.get("memory", {})
    return (
        f"[当前页面: 系统监控]\n"
        f"CPU: {cpu.get('overall_percent', 'N/A')}%\n"
        f"内存: {mem.get('ram', {}).get('percent', 'N/A')}%\n"
        f"Swap: {mem.get('swap', {}).get('percent', 'N/A')}%\n"
        f"用户正在查看实时监控数据，可帮助分析趋势、检测异常。"
    )


async def _docker_context() -> str:
    from modules.docker.services import list_containers, list_compose_stacks
    containers = await list_containers()
    stacks = await list_compose_stacks()
    running = sum(1 for c in containers if "Up" in (c.get("Status", "") or ""))
    stopped = len(containers) - running
    container_list = ", ".join(
        f"{c.get('Names', c.get('name', '?'))}({'运行' if 'Up' in (c.get('Status','') or '') else '停止'})"
        for c in containers[:15]
    )
    stack_list = ", ".join(s.get("name", "?") for s in stacks[:10])
    return (
        f"[当前页面: Docker 管理]\n"
        f"容器: {len(containers)} 个 (运行 {running}, 停止 {stopped})\n"
        f"容器列表: {container_list}\n"
        f"堆栈: {stack_list or '无'}\n"
        f"用户正在管理 Docker，可帮助启停容器、查看日志、分析异常。"
    )


async def _users_context() -> str:
    from modules.users.services import get_user_stats, read_quotas
    users = await asyncio.get_event_loop().run_in_executor(None, get_user_stats)
    quotas = await asyncio.get_event_loop().run_in_executor(None, read_quotas)
    user_lines = []
    for u in users[:10]:
        mem_gb = u.get("mem_gb", round(u.get("mem_bytes", 0) / 1073741824, 1))
        user_lines.append(f"  {u.get('name', u.get('username', '?'))}: 内存 {mem_gb}GB, {u.get('proc_count', u.get('process_count', 0))} 进程")
    return (
        f"[当前页面: 用户管理]\n"
        f"用户数: {len(users)}\n"
        + "\n".join(user_lines) + "\n"
        f"配额规则: {len(quotas)} 条\n"
        f"用户正在管理 Linux 用户，可帮助创建用户、调整配额、终止进程。"
    )


async def _services_context() -> str:
    from modules.services.services import list_services
    services = await list_services()
    active = sum(1 for s in services if s.get("active_state") == "active")
    svc_list = ", ".join(
        f"{s['name']}({'运行' if s.get('active_state') == 'active' else '停止'})"
        for s in services[:20]
    )
    return (
        f"[当前页面: 服务管理]\n"
        f"服务: {len(services)} 个 (运行 {active}, 停止 {len(services) - active})\n"
        f"服务列表: {svc_list}\n"
        f"用户正在管理 systemd 服务，可帮助启停服务、查看日志、分析依赖。"
    )


async def _cron_context() -> str:
    from modules.cron.services import get_user_crontab, get_root_crontab
    user_jobs = await get_user_crontab()
    root_jobs = await get_root_crontab()
    all_jobs = user_jobs + root_jobs
    enabled = sum(1 for j in all_jobs if j.get("enabled"))
    job_lines = []
    for j in all_jobs[:10]:
        status = "启用" if j.get("enabled") else "禁用"
        job_lines.append(f"  [{status}] {j['schedule']} — {j.get('description', j['command'][:60])}")
    return (
        f"[当前页面: 定时任务]\n"
        f"任务总数: {len(all_jobs)} (启用 {enabled}, 禁用 {len(all_jobs) - enabled})\n"
        + "\n".join(job_lines) + "\n"
        f"用户正在管理 cron 定时任务，可帮助创建/修改/删除任务。"
    )


async def _network_context() -> str:
    from modules.network.services import get_listening_ports
    ports = await get_listening_ports()
    port_list = ", ".join(
        f"{p.get('port')}/{p.get('proto', 'tcp')}({p.get('process', '?')})"
        for p in ports[:15]
    )
    return (
        f"[当前页面: 网络管理]\n"
        f"监听端口: {len(ports)} 个\n"
        f"端口列表: {port_list}\n"
        f"用户正在查看网络状态，可帮助分析端口占用、连接状况。"
    )


async def _proxy_context() -> str:
    return (
        "[当前页面: 代理管理]\n"
        "用户正在管理网络代理，可帮助切换节点、更新订阅、查看状态。"
    )


async def _logs_context() -> str:
    return (
        "[当前页面: 日志查看]\n"
        "用户正在查看系统日志，可帮助搜索日志内容、分析错误模式。"
    )


async def _notifications_context() -> str:
    return (
        "[当前页面: 通知管理]\n"
        "用户正在管理通知渠道，可帮助发送测试通知、查看历史。"
    )


async def _settings_context() -> str:
    return (
        "[当前页面: 系统设置]\n"
        "用户正在配置系统设置，可帮助调整大模型配置等。"
    )


async def _assets_context() -> str:
    return (
        "[当前页面: 资产台账]\n"
        "用户正在查看资产清单，可帮助发现资产、查看拓扑关系。"
    )


async def _audit_context() -> str:
    return (
        "[当前页面: 审计日志]\n"
        "用户正在审查操作日志，可帮助筛选和分析审计记录。"
    )


async def _panel_users_context() -> str:
    return (
        "[当前页面: 面板用户管理]\n"
        "用户正在管理面板登录账号，可帮助创建/修改面板用户。"
    )


# ─── 注册所有 provider ───

def _register_all():
    register("dashboard", _dashboard_context)
    register("monitoring", _monitoring_context)
    register("docker", _docker_context)
    register("users", _users_context)
    register("services", _services_context)
    register("cron", _cron_context)
    register("network", _network_context)
    register("proxy", _proxy_context)
    register("logs", _logs_context)
    register("notifications", _notifications_context)
    register("settings", _settings_context)
    register("assets", _assets_context)
    register("audit", _audit_context)
    register("panel_users", _panel_users_context)


_register_all()

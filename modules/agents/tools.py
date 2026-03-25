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


# ─── safe: 趋势分析 ───

@tool
async def analyze_resource_trend(metric: str = "all", hours: int = 168) -> str:
    """分析系统资源的历史趋势。从监控数据库查询指定时间范围的指标历史，计算统计量和趋势预测。

    Args:
        metric: 指标类型 — all(全部), cpu(CPU使用率), memory(内存), gpu(GPU), disk(磁盘)。默认 all。
        hours: 分析的时间范围（小时），默认 168（一周）。
    """
    import aiosqlite
    from datetime import datetime, timedelta
    from config import settings

    db_path = settings.db_path
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()

    try:
        async with aiosqlite.connect(db_path) as db:
            cursor = await db.execute(
                "SELECT timestamp, value_json FROM metrics WHERE metric_type = 'all' AND timestamp > ? ORDER BY timestamp",
                (cutoff,),
            )
            rows = await cursor.fetchall()
    except Exception as e:
        return f"查询历史数据失败: {e}"

    if not rows:
        return f"最近 {hours} 小时内没有监控数据。请确认监控采集器正在运行。"

    # 提取指标时间序列
    series = {"cpu": [], "memory": [], "swap": [], "disk": [], "gpu_util": [], "gpu_mem": [], "gpu_temp": []}
    timestamps = []

    for ts, val_json in rows:
        try:
            data = json.loads(val_json) if isinstance(val_json, str) else val_json
        except (json.JSONDecodeError, TypeError):
            continue

        timestamps.append(ts)
        cpu = data.get("cpu", {})
        mem = data.get("memory", {})
        gpu = data.get("gpu", {})
        disk_list = data.get("disk", [])

        # CPU: 兼容 overall_percent 或 percent
        series["cpu"].append(cpu.get("overall_percent", cpu.get("percent", 0)))

        # 内存: 嵌套结构 memory.ram.percent
        ram = mem.get("ram", mem) if isinstance(mem, dict) else {}
        swap = mem.get("swap", {}) if isinstance(mem, dict) else {}
        series["memory"].append(ram.get("percent", mem.get("percent", 0)))
        series["swap"].append(swap.get("percent", 0))

        # 磁盘: list 格式，取根分区
        if isinstance(disk_list, list):
            root_disk = next((d for d in disk_list if d.get("mountpoint") == "/"), None)
            series["disk"].append(root_disk["percent"] if root_disk else 0)
        elif isinstance(disk_list, dict):
            series["disk"].append(disk_list.get("percent", 0))

        # GPU
        if gpu and gpu.get("available", True):
            series["gpu_util"].append(gpu.get("util", 0))
            mem_total = gpu.get("mem_total", 1)
            mem_used = gpu.get("mem_used", 0)
            series["gpu_mem"].append(round(mem_used / mem_total * 100, 1) if mem_total else 0)
            series["gpu_temp"].append(gpu.get("temp", 0))

    def calc_stats(values, name):
        if not values:
            return f"- {name}: 无数据\n"
        n = len(values)
        avg = sum(values) / n
        peak = max(values)
        minimum = min(values)
        sorted_v = sorted(values)
        p95 = sorted_v[int(n * 0.95)] if n > 1 else sorted_v[0]
        # 简单线性趋势 (最小二乘)
        if n >= 10:
            x_mean = (n - 1) / 2
            y_mean = avg
            num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
            den = sum((i - x_mean) ** 2 for i in range(n))
            slope = num / den if den else 0
            trend = "上升" if slope > 0.01 else "下降" if slope < -0.01 else "平稳"
            # 预测（假设每小时一个数据点）
            hours_per_point = hours / n if n else 1
            predicted_7d = values[-1] + slope * (7 * 24 / hours_per_point)
            predicted_7d = max(0, min(100, predicted_7d))  # clamp 到 0-100%
        else:
            trend = "数据不足"
            slope = 0
            predicted_7d = avg

        return (
            f"- **{name}**: 均值 {avg:.1f}%, 峰值 {peak:.1f}%, P95 {p95:.1f}%, "
            f"最低 {minimum:.1f}% | 趋势: {trend} | 7天预测: {predicted_7d:.1f}%\n"
        )

    # 构建报告
    lines = [f"## 资源趋势分析 (最近 {hours} 小时, {len(rows)} 个数据点)\n"]

    target_metrics = {
        "all": ["cpu", "memory", "swap", "disk", "gpu_util", "gpu_mem", "gpu_temp"],
        "cpu": ["cpu"],
        "memory": ["memory", "swap"],
        "gpu": ["gpu_util", "gpu_mem", "gpu_temp"],
        "disk": ["disk"],
    }

    names = {
        "cpu": "CPU使用率", "memory": "内存使用率", "swap": "Swap使用率",
        "disk": "系统盘使用率", "gpu_util": "GPU利用率", "gpu_mem": "GPU显存", "gpu_temp": "GPU温度(°C)",
    }

    metrics_to_analyze = target_metrics.get(metric, target_metrics["all"])
    for m in metrics_to_analyze:
        lines.append(calc_stats(series.get(m, []), names.get(m, m)))

    # 汇总建议
    lines.append("\n### 建议\n")
    for m in metrics_to_analyze:
        vals = series.get(m, [])
        if vals:
            p95 = sorted(vals)[int(len(vals) * 0.95)] if len(vals) > 1 else vals[0]
            if m in ("cpu", "memory") and p95 > 85:
                lines.append(f"- ⚠️ {names[m]} P95={p95:.1f}% 偏高，建议关注资源分配\n")
            if m == "disk" and p95 > 80:
                lines.append(f"- ⚠️ {names[m]} P95={p95:.1f}%，建议清理或扩容\n")
            if m == "gpu_temp" and max(vals) > 80:
                lines.append(f"- ⚠️ {names[m]} 峰值={max(vals):.0f}°C，注意散热\n")

    return "".join(lines)


# ─── safe: 合规检查 ───

@tool
def check_compliance(category: str = "") -> str:
    """执行安全合规基线检查。基于 CIS Benchmark 标准检查 SSH、口令策略、文件权限、网络安全等配置。

    Args:
        category: 可选，只检查指定分类（如 SSH安全、口令策略、网络安全）。留空检查全部。
    """
    from modules.agents.compliance import run_compliance_checks

    return run_compliance_checks(category)


# ─── safe: 故障案例库 ───

@tool
async def search_fault_cases(query: str) -> str:
    """搜索故障案例库。从历史故障案例中检索匹配的问题和解决方案。

    Args:
        query: 搜索关键词（如 "内存超限"、"Docker 重启"、"SSH 连接"）
    """
    import aiosqlite
    from config import settings

    try:
        async with aiosqlite.connect(settings.db_path) as db:
            try:
                cursor = await db.execute(
                    "SELECT fc.id, fc.title, fc.category, fc.symptoms, fc.root_cause, fc.solution, fc.tags "
                    "FROM fault_cases_fts fts JOIN fault_cases fc ON fts.rowid = fc.id "
                    "WHERE fault_cases_fts MATCH ? ORDER BY rank LIMIT 5",
                    (query,),
                )
            except Exception:
                like = f"%{query}%"
                cursor = await db.execute(
                    "SELECT id, title, category, symptoms, root_cause, solution, tags "
                    "FROM fault_cases WHERE title LIKE ? OR symptoms LIKE ? OR root_cause LIKE ? OR tags LIKE ? "
                    "ORDER BY created_at DESC LIMIT 5",
                    (like, like, like, like),
                )

            rows = await cursor.fetchall()

        if not rows:
            return f"没有找到与 \"{query}\" 相关的故障案例。"

        lines = [f"## 故障案例搜索: \"{query}\" ({len(rows)} 条结果)\n"]
        for r in rows:
            lines.append(f"### [{r[2] or '通用'}] {r[1]}")
            if r[3]:
                lines.append(f"**症状**: {r[3][:200]}")
            if r[4]:
                lines.append(f"**根因**: {r[4][:200]}")
            if r[5]:
                lines.append(f"**解决方案**: {r[5][:300]}")
            if r[6]:
                lines.append(f"**标签**: {r[6]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"搜索案例库失败: {e}"


@tool
async def save_fault_case(title: str, category: str, symptoms: str, root_cause: str, solution: str, tags: str = "") -> str:
    """将故障案例保存到案例库。

    Args:
        title: 案例标题（简短描述问题）
        category: 分类（memory/docker/service/network/security/gpu）
        symptoms: 症状描述
        root_cause: 根本原因
        solution: 解决方案
        tags: 标签（逗号分隔，如 "内存,超限,kill"）
    """
    import aiosqlite
    from config import settings

    try:
        async with aiosqlite.connect(settings.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO fault_cases (title, category, symptoms, root_cause, solution, tags, source) "
                "VALUES (?, ?, ?, ?, ?, ?, 'manual') RETURNING id",
                (title, category, symptoms, root_cause, solution, tags),
            )
            row = await cursor.fetchone()
            case_id = row[0] if row else None

            if case_id:
                try:
                    await db.execute(
                        "INSERT INTO fault_cases_fts(rowid, title, symptoms, root_cause, solution, tags) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (case_id, title, symptoms, root_cause, solution, tags),
                    )
                except Exception:
                    pass

            await db.commit()
            return f"案例已保存 (ID: {case_id})。标题: {title}"
    except Exception as e:
        return f"保存案例失败: {e}"


# ─── danger: 合规自动修复 ───

@tool
def auto_fix_compliance(item_id: str) -> str:
    """自动修复指定的不合规项。仅对白名单中的 auto_fixable 项生效，并在执行后验证结果。

    Args:
        item_id: 合规基线项 ID（如 ssh_empty_password, ssh_max_auth_tries）
    """
    from modules.agents.compliance import fix_compliance_item

    return fix_compliance_item(item_id)


# ─── safe: 资产台账 ───

@tool
async def get_asset_inventory(asset_type: str = "") -> str:
    """查询服务器资产清单。返回所有已发现的服务、容器、端口、存储等资产。

    Args:
        asset_type: 可选，按类型过滤（service/container/compose/port/storage）。留空返回全部。
    """
    from modules.assets.services import get_assets
    assets = await get_assets(asset_type)
    if not assets:
        return f"没有找到{'类型为 ' + asset_type + ' 的' if asset_type else ''}资产。请先执行资产发现。"

    type_names = {"service": "系统服务", "container": "Docker容器", "compose": "Compose堆栈",
                  "port": "监听端口", "storage": "存储挂载"}
    lines = ["## 资产清单\n"]

    current_type = ""
    for a in assets:
        if a["type"] != current_type:
            current_type = a["type"]
            lines.append(f"\n### {type_names.get(current_type, current_type)}\n")
            lines.append("| 名称 | 状态 | 详情 |")
            lines.append("|---|---|---|")
        props = a.get("properties", {})
        detail = ", ".join(f"{k}={v}" for k, v in (props.items() if isinstance(props, dict) else []))[:80]
        status_icon = {"running": "🟢", "stopped": "🔴", "listening": "🔵", "ok": "🟢", "warning": "🟡"}.get(a["status"], "⚪")
        lines.append(f"| {a['name']} | {status_icon} {a['status']} | {detail} |")

    lines.append(f"\n共 {len(assets)} 项资产")
    return "\n".join(lines)


@tool
async def get_asset_topology() -> str:
    """生成服务器资产拓扑关系图（Mermaid 格式）并分析潜在风险（单点故障、冗余不足等）。"""
    from modules.assets.services import get_assets, generate_topology_mermaid

    assets = await get_assets()
    if not assets:
        return "没有资产数据。请先执行资产发现。"

    mermaid = await generate_topology_mermaid()

    risks = []
    type_counts = {}
    stopped = []
    for a in assets:
        type_counts[a["type"]] = type_counts.get(a["type"], 0) + 1
        if a["status"] in ("stopped", "unknown"):
            stopped.append(a)

    if stopped:
        risks.append(f"⚠️ {len(stopped)} 个资产处于停止/未知状态: {', '.join(a['name'] for a in stopped[:5])}")

    for t, count in type_counts.items():
        if t == "compose" and count > 0:
            risks.append(f"ℹ️ {count} 个 Compose 堆栈（单节点部署，无高可用）")

    risk_text = "\n".join(risks) if risks else "未发现明显风险"
    return f"## 资产拓扑图\n\n```mermaid\n{mermaid}\n```\n\n## 风险分析\n{risk_text}\n\n共 {len(assets)} 项资产"


# ─── moderate: 服务自启动管理 ───

@tool
async def service_enable_disable_tool(name: str, action: str) -> str:
    """启用或禁用 systemd 服务的自启动。"""
    from modules.services.services import service_enable_disable
    try:
        await service_enable_disable(name, action)
        action_cn = "启用" if action == "enable" else "禁用"
        return f"已{action_cn}服务 {name} 的自启动"
    except (ValueError, RuntimeError) as e:
        return f"操作失败: {e}"


# ─── safe: 服务依赖查询 ───

@tool
async def get_service_dependencies_tool(name: str) -> str:
    """获取 systemd 服务的依赖关系树。"""
    from modules.services.services import service_dependencies
    try:
        result = await service_dependencies(name)
        deps = result["dependencies"]
        if not deps:
            return f"服务 {name} 没有依赖项"
        lines = [f"## {name} 的依赖关系 ({len(deps)} 项)\n"]
        for d in deps[:30]:
            lines.append(f"- {d}")
        return "\n".join(lines)
    except (ValueError, RuntimeError) as e:
        return f"查询失败: {e}"


# ─── safe: Docker 增强 ───

@tool
async def list_docker_networks() -> str:
    """列出 Docker 网络，包含名称、驱动和范围。"""
    from modules.docker.services import list_networks
    networks = await list_networks()
    if not networks:
        return "没有 Docker 网络"
    lines = [f"## Docker 网络 ({len(networks)} 个)\n"]
    for n in networks:
        lines.append(f"- **{n['name']}** — 驱动: {n['driver']}, 范围: {n['scope']}")
    return "\n".join(lines)


# ─── moderate: Docker 容器 exec ───

@tool
async def docker_container_exec(container_name: str, command: str) -> str:
    """在运行中的 Docker 容器内执行命令。"""
    from modules.docker.services import container_exec
    try:
        output = await container_exec(container_name, command)
        return f"容器 {container_name} 执行结果:\n```\n{output[:5000]}\n```"
    except (ValueError, RuntimeError) as e:
        return f"执行失败: {e}"


# ─── danger: Docker 资源清理 ───

@tool
async def docker_prune(resource_type: str = "all") -> str:
    """清理未使用的 Docker 资源。此操作不可逆。"""
    from modules.docker.services import prune_resources
    try:
        result = await prune_resources(resource_type)
        return f"清理完成 ({resource_type}):\n{result[:2000]}"
    except (ValueError, RuntimeError) as e:
        return f"清理失败: {e}"


# ─── safe: 用户登录审计 ───

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


# ─── danger: 用户管理 ───

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


# ─── safe: 定时任务查询 ───

@tool
async def list_cron_jobs(cron_user: str = "zhengxiaodong") -> str:
    """列出指定用户的 cron 定时任务。"""
    from modules.cron.services import get_user_crontab, get_root_crontab
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


# ─── safe: RAG 检索 ───

@tool
async def retrieve_knowledge(query: str, source: str = "", top_k: int = 5) -> str:
    """从知识库检索相关信息。使用语义搜索+关键词搜索混合检索运维文档、故障案例、巡检报告、API文档等。

    比 search_fault_cases 更强大：覆盖全部知识源，支持语义理解。

    Args:
        query: 搜索查询（如 "Docker 容器频繁重启怎么排查"、"nginx 配置在哪里"）
        source: 可选，限定数据源。可选值: ops-docs, api-docs, fault_case, patrol_history, compliance, agent-memory。留空搜索全部。
        top_k: 返回结果数量，默认5
    """
    from modules.agents.rag import hybrid_search
    results = await asyncio.get_event_loop().run_in_executor(
        None, hybrid_search, query, top_k, source
    )
    if not results:
        return f"知识库中没有找到与 \"{query}\" 相关的信息。"
    lines = [f"## 知识检索: \"{query}\" ({len(results)} 条结果)\n"]
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        src = meta.get("source", "unknown")
        title = meta.get("title", meta.get("file", ""))
        lines.append(f"### [{i}] [{src}] {title}")
        lines.append(r["content"][:500])
        lines.append(f"*相关度: {r['score']:.2f} | 检索方式: {r['search_type']}*\n")
    return "\n".join(lines)


@tool
async def reindex_knowledge_base() -> str:
    """手动触发知识库全量重建索引。管理员在更新了运维文档或导入新故障案例后使用。"""
    from modules.agents.rag import build_full_index
    stats = await asyncio.get_event_loop().run_in_executor(
        None, build_full_index, True
    )
    lines = ["## 知识库重建完成\n"]
    for key, count in stats.items():
        if key not in ("total", "build_time_seconds", "skipped"):
            lines.append(f"- {key}: {count} 个文档")
    lines.append(f"\n总计: {stats.get('total', 0)} 个文档")
    lines.append(f"耗时: {stats.get('build_time_seconds', 0):.1f} 秒")
    return "\n".join(lines)


# ─── safe: 页面上下文数据查询 ───

@tool
async def get_page_data(page_name: str) -> str:
    """获取指定页面的实时数据摘要。当用户从页面内气泡对话框提问时，用此工具获取该页面的最新数据。

    Args:
        page_name: 页面标识，可选值: dashboard, monitoring, docker, users, services, cron, network, proxy, logs, notifications, settings, assets, audit, panel_users
    """
    from modules.agents.page_context import get_page_context
    result = await get_page_context(page_name)
    if not result:
        return f"未找到页面 '{page_name}' 的数据提供器。可用页面: dashboard, docker, users, services, cron, monitoring, network, proxy"
    return result


# ─── 工具注册表 ───

def get_server_tools(user_role: str = "admin") -> list:
    """返回服务器管理工具列表

    Args:
        user_role: "admin" 返回全部工具，"user" 只返回只读安全工具
    """
    all_tools = [
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
        check_compliance,
        analyze_resource_trend,
        search_fault_cases,
        save_fault_case,
        get_asset_inventory,
        get_asset_topology,
        auto_fix_compliance,
        # 服务增强
        service_enable_disable_tool,
        get_service_dependencies_tool,
        # Docker 增强
        list_docker_networks,
        docker_container_exec,
        docker_prune,
        # 用户审计与管理
        get_user_login_history_tool,
        get_active_sessions_tool,
        manage_linux_user,
        kill_single_process_tool,
        # 定时任务
        list_cron_jobs,
        validate_cron_expr,
        create_cron_job,
        modify_cron_schedule,
        toggle_cron_job_tool,
        delete_cron_job_tool,
        # RAG 知识库
        retrieve_knowledge,
        reindex_knowledge_base,
        # 页面上下文
        get_page_data,
    ]

    if user_role == "admin":
        return all_tools

    # 普通用户：只返回 SAFE 级别工具
    from modules.agents.safety import TOOL_RISK_MAP, RiskLevel
    excluded = {"send_notification", "save_fault_case"}
    return [
        t for t in all_tools
        if TOOL_RISK_MAP.get(t.name, RiskLevel.DANGER) == RiskLevel.SAFE
        and t.name not in excluded
    ]


# 向后兼容
get_all_tools = get_server_tools

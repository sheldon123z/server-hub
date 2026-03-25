"""系统状态工具 — CPU/内存/磁盘/GPU/趋势分析"""

import json
from langchain_core.tools import tool
from config import settings


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
async def analyze_resource_trend(metric: str = "all", hours: int = 168) -> str:
    """分析系统资源的历史趋势。从监控数据库查询指定时间范围的指标历史，计算统计量和趋势预测。

    Args:
        metric: 指标类型 — all(全部), cpu(CPU使用率), memory(内存), gpu(GPU), disk(磁盘)。默认 all。
        hours: 分析的时间范围（小时），默认 168（一周）。
    """
    import aiosqlite
    from datetime import datetime, timedelta

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

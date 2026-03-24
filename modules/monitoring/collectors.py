"""
系统指标采集模块
采集 CPU、内存、GPU、磁盘、网络、Docker、进程等系统指标
"""

import json
import logging
import os
import re
import subprocess
import time

import psutil

logger = logging.getLogger(__name__)


def _run(cmd: str, timeout: int = 10) -> str:
    """执行 shell 命令并返回 stdout"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------

def collect_cpu() -> dict:
    """采集 CPU 指标: 每核使用率、整体使用率、负载均值、核心数"""
    per_cpu = psutil.cpu_percent(interval=1, percpu=True)
    overall = psutil.cpu_percent(interval=0)
    load_1, load_5, load_15 = psutil.getloadavg()
    return {
        "per_cpu_percent": per_cpu,
        "overall_percent": overall,
        "load_avg": {
            "1min": round(load_1, 2),
            "5min": round(load_5, 2),
            "15min": round(load_15, 2),
        },
        "count": psutil.cpu_count(logical=True),
    }


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

def collect_memory() -> dict:
    """采集内存指标: RAM 和 Swap 的总量、已用、可用、百分比"""
    vm = psutil.virtual_memory()
    sw = psutil.swap_memory()
    return {
        "ram": {
            "total": vm.total,
            "used": vm.used,
            "available": vm.available,
            "percent": vm.percent,
        },
        "swap": {
            "total": sw.total,
            "used": sw.used,
            "available": sw.total - sw.used,
            "percent": sw.percent,
        },
    }


# ---------------------------------------------------------------------------
# GPU
# ---------------------------------------------------------------------------

def collect_gpu() -> dict:
    """
    采集 GPU 指标: 利用率、显存使用、温度、进程列表
    通过 nvidia-smi 解析获取
    """
    result = {
        "available": False,
        "util": 0,
        "mem_used": 0,
        "mem_total": 0,
        "temp": 0,
        "processes": [],
    }

    # 基础 GPU 信息
    raw = _run(
        "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,"
        "temperature.gpu --format=csv,noheader,nounits 2>/dev/null"
    )
    if not raw:
        return result

    parts = [x.strip() for x in raw.split(",")]
    if len(parts) >= 4:
        result["available"] = True
        result["util"] = int(parts[0])
        result["mem_used"] = int(parts[1])
        result["mem_total"] = int(parts[2])
        result["temp"] = int(parts[3])

    # GPU 进程列表
    procs_raw = _run(
        "nvidia-smi --query-compute-apps=pid,used_gpu_memory,process_name "
        "--format=csv,noheader,nounits 2>/dev/null"
    )
    if procs_raw:
        for line in procs_raw.splitlines():
            pparts = [x.strip() for x in line.split(",")]
            if len(pparts) >= 3:
                result["processes"].append({
                    "pid": int(pparts[0]),
                    "gpu_mem_mb": int(pparts[1]),
                    "name": pparts[2],
                })

    return result


# ---------------------------------------------------------------------------
# Disk (usage)
# ---------------------------------------------------------------------------

def collect_disk() -> list:
    """采集所有挂载点的磁盘使用情况"""
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "device": part.device,
                "mountpoint": part.mountpoint,
                "fstype": part.fstype,
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            })
        except (PermissionError, OSError):
            continue
    return disks


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

_prev_net: dict = {"counters": None, "time": 0.0}


def collect_network() -> dict:
    """
    采集网络指标: 收发速率、错误/丢包计数、TCP 连接状态分布
    通过与上次采样做差计算速率
    """
    now = time.time()
    counters = psutil.net_io_counters()

    totals: dict = {
        "bytes_recv_rate": 0.0,
        "bytes_sent_rate": 0.0,
        "packets_recv_rate": 0.0,
        "packets_sent_rate": 0.0,
        "err_in": counters.errin,
        "err_out": counters.errout,
        "drop_in": counters.dropin,
        "drop_out": counters.dropout,
    }

    prev_c = _prev_net["counters"]
    prev_t = _prev_net["time"]

    if prev_c is not None and now > prev_t:
        dt = now - prev_t
        totals["bytes_recv_rate"] = round((counters.bytes_recv - prev_c.bytes_recv) / dt, 1)
        totals["bytes_sent_rate"] = round((counters.bytes_sent - prev_c.bytes_sent) / dt, 1)
        totals["packets_recv_rate"] = round((counters.packets_recv - prev_c.packets_recv) / dt, 1)
        totals["packets_sent_rate"] = round((counters.packets_sent - prev_c.packets_sent) / dt, 1)

    _prev_net["counters"] = counters
    _prev_net["time"] = now

    # TCP 连接状态分布
    tcp_states: dict = {}
    try:
        conns = psutil.net_connections("tcp")
        for c in conns:
            st = c.status
            tcp_states[st] = tcp_states.get(st, 0) + 1
    except (psutil.AccessDenied, PermissionError):
        pass

    tcp_total = sum(tcp_states.values())

    return {
        "totals": totals,
        "tcp_states": tcp_states,
        "tcp_total": tcp_total,
    }


# ---------------------------------------------------------------------------
# Docker stats
# ---------------------------------------------------------------------------

_SIZE_RE = re.compile(r"([\d.]+)\s*([KMGT]?i?B)", re.IGNORECASE)

_SIZE_UNITS = {
    "B": 1, "KB": 1e3, "KIB": 1024,
    "MB": 1e6, "MIB": 1024**2,
    "GB": 1e9, "GIB": 1024**3,
    "TB": 1e12, "TIB": 1024**4,
}


def _parse_size_mb(s: str) -> float:
    """将 '123.4MiB' / '1.2GiB' 等字符串解析为 MB"""
    m = _SIZE_RE.search(s)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2).upper()
    multiplier = _SIZE_UNITS.get(unit, 1)
    return round(val * multiplier / (1024**2), 2)


def _parse_percent(s: str) -> float:
    """将 '12.34%' 解析为 float"""
    try:
        return float(s.strip().rstrip("%"))
    except (ValueError, AttributeError):
        return 0.0


def _parse_net_io(s: str) -> tuple[float, float]:
    """将 '1.2MB / 3.4kB' 解析为 (rx_mb, tx_mb)"""
    parts = s.split("/")
    if len(parts) != 2:
        return 0.0, 0.0
    return _parse_size_mb(parts[0]), _parse_size_mb(parts[1])


def collect_docker_stats() -> dict:
    """
    采集 Docker 容器资源使用指标
    通过 docker stats --no-stream + docker inspect 获取
    """
    result: dict = {
        "containers": [],
        "groups": {},
        "total_containers": 0,
        "total_running": 0,
    }

    # docker stats JSON 输出
    raw = _run(
        "docker stats --no-stream --format '{{json .}}' 2>/dev/null",
        timeout=30,
    )
    if not raw:
        return result

    names = []
    stats_map: dict = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        name = item.get("Name", "")
        if not name:
            continue
        names.append(name)
        stats_map[name] = item

    if not names:
        return result

    # 批量获取 RestartCount 和 compose project
    names_arg = " ".join(f"'{n}'" for n in names)
    inspect_raw = _run(
        f"docker inspect --format '{{{{.Name}}}}|{{{{.RestartCount}}}}|"
        f"{{{{index .Config.Labels \"com.docker.compose.project\"}}}}|"
        f"{{{{.State.Status}}}}' {names_arg} 2>/dev/null",
        timeout=15,
    )
    inspect_map: dict = {}
    if inspect_raw:
        for line in inspect_raw.splitlines():
            parts = line.strip().split("|")
            if len(parts) >= 4:
                cname = parts[0].lstrip("/")
                inspect_map[cname] = {
                    "restart_count": int(parts[1]) if parts[1].isdigit() else 0,
                    "compose_project": parts[2] if parts[2] and parts[2] != "<no value>" else "",
                    "status": parts[3],
                }

    # 组装容器列表
    groups: dict = {}
    for name in names:
        item = stats_map[name]
        info = inspect_map.get(name, {})

        cpu_pct = _parse_percent(item.get("CPUPerc", "0%"))

        # MemUsage: "123.4MiB / 456.7GiB"
        mem_usage_str = item.get("MemUsage", "0B / 0B")
        mem_parts = mem_usage_str.split("/")
        mem_usage_mb = _parse_size_mb(mem_parts[0]) if len(mem_parts) >= 1 else 0.0
        mem_limit_mb = _parse_size_mb(mem_parts[1]) if len(mem_parts) >= 2 else 0.0
        mem_pct = _parse_percent(item.get("MemPerc", "0%"))

        net_rx_mb, net_tx_mb = _parse_net_io(item.get("NetIO", "0B / 0B"))

        pids = 0
        try:
            pids = int(item.get("PIDs", "0"))
        except (ValueError, TypeError):
            pass

        restart_count = info.get("restart_count", 0)
        compose_project = info.get("compose_project", "")
        status = info.get("status", "running")

        container = {
            "name": name,
            "status": status,
            "cpu_percent": cpu_pct,
            "mem_usage_mb": mem_usage_mb,
            "mem_limit_mb": mem_limit_mb,
            "mem_percent": mem_pct,
            "net_rx_mb": net_rx_mb,
            "net_tx_mb": net_tx_mb,
            "pids": pids,
            "restart_count": restart_count,
            "compose_project": compose_project,
        }
        result["containers"].append(container)

        # 按 compose project 分组聚合
        grp_key = compose_project or "_standalone"
        if grp_key not in groups:
            groups[grp_key] = {"count": 0, "running": 0, "total_cpu": 0.0, "total_mem_mb": 0.0}
        groups[grp_key]["count"] += 1
        if status == "running":
            groups[grp_key]["running"] += 1
        groups[grp_key]["total_cpu"] = round(groups[grp_key]["total_cpu"] + cpu_pct, 2)
        groups[grp_key]["total_mem_mb"] = round(groups[grp_key]["total_mem_mb"] + mem_usage_mb, 2)

    result["groups"] = groups
    result["total_containers"] = len(names)
    result["total_running"] = sum(1 for c in result["containers"] if c["status"] == "running")

    return result


# ---------------------------------------------------------------------------
# Disk I/O
# ---------------------------------------------------------------------------

_prev_disk_io: dict = {"counters": None, "time": 0.0}


def collect_disk_io() -> dict:
    """
    采集磁盘 I/O 指标: IOPS、吞吐量(MB/s)、延迟(ms)、利用率(%)
    通过与上次采样做差计算速率
    """
    now = time.time()
    try:
        current = psutil.disk_io_counters(perdisk=True)
    except Exception:
        return {"devices": {}}

    prev_c = _prev_disk_io["counters"]
    prev_t = _prev_disk_io["time"]

    devices: dict = {}

    if prev_c is not None and now > prev_t:
        dt = now - prev_t
        for dev_name, cur in current.items():
            # 跳过 loop/ram 等虚拟设备
            if dev_name.startswith(("loop", "ram", "dm-")):
                continue
            prev = prev_c.get(dev_name)
            if prev is None:
                continue

            read_count_d = cur.read_count - prev.read_count
            write_count_d = cur.write_count - prev.write_count
            read_bytes_d = cur.read_bytes - prev.read_bytes
            write_bytes_d = cur.write_bytes - prev.write_bytes
            read_time_d = cur.read_time - prev.read_time
            write_time_d = cur.write_time - prev.write_time
            busy_time_d = cur.busy_time - prev.busy_time if hasattr(cur, "busy_time") else 0

            devices[dev_name] = {
                "read_iops": round(read_count_d / dt, 1) if dt > 0 else 0.0,
                "write_iops": round(write_count_d / dt, 1) if dt > 0 else 0.0,
                "read_mbps": round(read_bytes_d / dt / 1024 / 1024, 2) if dt > 0 else 0.0,
                "write_mbps": round(write_bytes_d / dt / 1024 / 1024, 2) if dt > 0 else 0.0,
                "avg_read_latency_ms": round(read_time_d / read_count_d, 2) if read_count_d > 0 else 0.0,
                "avg_write_latency_ms": round(write_time_d / write_count_d, 2) if write_count_d > 0 else 0.0,
                "util_percent": round(busy_time_d / (dt * 1000) * 100, 1) if dt > 0 else 0.0,
            }

    _prev_disk_io["counters"] = current
    _prev_disk_io["time"] = now

    return {"devices": devices}


# ---------------------------------------------------------------------------
# Inode
# ---------------------------------------------------------------------------

def collect_inode() -> list:
    """采集所有挂载点的 inode 使用情况"""
    result = []
    for part in psutil.disk_partitions(all=False):
        try:
            st = os.statvfs(part.mountpoint)
        except (PermissionError, OSError):
            continue
        total = st.f_files
        free = st.f_ffree
        if total == 0:
            continue
        used = total - free
        percent = round(used / total * 100, 1)
        result.append({
            "mountpoint": part.mountpoint,
            "total": total,
            "used": used,
            "free": free,
            "percent": percent,
        })
    return result


# ---------------------------------------------------------------------------
# Top Processes
# ---------------------------------------------------------------------------

def collect_top_processes(limit: int = 15) -> dict:
    """
    采集资源占用 Top N 进程
    按 CPU、内存、GPU 显存分别排序
    """
    # 预热 cpu_percent（第一次调用返回 0）
    for p in psutil.process_iter():
        try:
            p.cpu_percent(interval=0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # 短暂等待以获取有意义的 cpu_percent
    time.sleep(0.1)

    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "cmdline"]):
        try:
            info = p.info
            rss = info["memory_info"].rss if info.get("memory_info") else 0
            cmdline_parts = info.get("cmdline") or []
            cmdline = " ".join(cmdline_parts)[:200] if cmdline_parts else info.get("name", "")
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "",
                "user": info.get("username") or "",
                "cpu_percent": info.get("cpu_percent") or 0.0,
                "mem_rss_mb": round(rss / 1024 / 1024, 1),
                "cmdline": cmdline,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    by_cpu = sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)[:limit]
    by_mem = sorted(procs, key=lambda x: x["mem_rss_mb"], reverse=True)[:limit]

    # GPU 进程排行
    gpu_data = collect_gpu()
    by_gpu = sorted(gpu_data.get("processes", []), key=lambda x: x.get("gpu_mem_mb", 0), reverse=True)[:limit]

    return {
        "by_cpu": by_cpu,
        "by_mem": by_mem,
        "by_gpu": by_gpu,
    }


# ---------------------------------------------------------------------------
# Realtime Fast (lightweight, no blocking)
# ---------------------------------------------------------------------------

def collect_realtime_fast() -> dict:
    """5秒快速快照 - 仅轻量指标，不含 Docker/进程排行"""
    load_1, load_5, load_15 = psutil.getloadavg()
    return {
        "timestamp": time.time(),
        "cpu": {
            "overall_percent": psutil.cpu_percent(interval=0),
            "per_cpu_percent": psutil.cpu_percent(interval=0, percpu=True),
            "load_avg": {
                "1min": round(load_1, 2),
                "5min": round(load_5, 2),
                "15min": round(load_15, 2),
            },
            "count": psutil.cpu_count(logical=True),
        },
        "memory": collect_memory(),
        "gpu": collect_gpu(),
        "network": collect_network(),
        "disk_io": collect_disk_io(),
    }


# ---------------------------------------------------------------------------
# Full Snapshot
# ---------------------------------------------------------------------------

def collect_all() -> dict:
    """完整快照（含Docker和进程，60s周期用）"""
    return {
        "timestamp": time.time(),
        "cpu": collect_cpu(),
        "memory": collect_memory(),
        "gpu": collect_gpu(),
        "disk": collect_disk(),
        "network": collect_network(),
        "disk_io": collect_disk_io(),
        "inode": collect_inode(),
        "docker": collect_docker_stats(),
        "top_processes": collect_top_processes(),
    }

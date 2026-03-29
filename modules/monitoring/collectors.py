"""
系统指标采集模块
采集 CPU、内存、GPU、磁盘、网络、Docker、进程等系统指标
"""

import copy
import json
import logging
import os
import platform
import re
import threading
import time

import psutil
from utils.command import run_command, run_command_text

from config import settings

logger = logging.getLogger(__name__)

_gpu_cache = {"ts": 0.0, "value": None}
_gpu_cache_lock = threading.Lock()
_cpu_cache = {"ts": 0.0, "value": None}
_cpu_cache_lock = threading.Lock()
_CPU_CACHE_TTL = 5  # seconds
_top_process_cache = {"ts": 0.0, "limit": 0, "value": None}
_top_process_lock = threading.Lock()
_top_process_cpu_primed = False


def _read_os_pretty_name() -> str:
    """读取当前系统发行版名称"""
    try:
        with open("/etc/os-release", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception as e:
        logger.debug("读取 /etc/os-release 失败: %s", e)
    return platform.system()


def _read_cpu_model() -> str:
    """读取 CPU 型号"""
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception as e:
        logger.debug("读取 /proc/cpuinfo 失败: %s", e)
    return platform.processor() or "Unknown CPU"


def _format_uptime(seconds: float) -> str:
    """将秒数格式化为可读 uptime 文本"""
    total = max(int(seconds), 0)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def collect_system_info() -> dict:
    """采集主机基础信息"""
    return {
        "hostname": platform.node(),
        "os": _read_os_pretty_name(),
        "kernel": platform.release(),
        "cpu_model": _read_cpu_model(),
    }


# ---------------------------------------------------------------------------
# CPU
# ---------------------------------------------------------------------------


def collect_cpu() -> dict:
    """采集 CPU 指标: 每核使用率、整体使用率、负载均值、核心数

    使用 interval=0 非阻塞采集 + 5 秒 TTL 缓存，避免并发请求
    各自阻塞 1 秒。首次调用返回 0（psutil 需要两次采样差值），
    但 scheduler 每 60s 定时采集，实际运行时缓存命中率高。
    """
    now = time.time()
    with _cpu_cache_lock:
        cached = _cpu_cache["value"]
        if cached is not None and now - _cpu_cache["ts"] < _CPU_CACHE_TTL:
            return copy.deepcopy(cached)

    per_cpu = psutil.cpu_percent(interval=0, percpu=True)
    overall = psutil.cpu_percent(interval=0)
    load_1, load_5, load_15 = psutil.getloadavg()
    result = {
        "per_cpu_percent": per_cpu,
        "overall_percent": overall,
        "load_avg": {
            "1min": round(load_1, 2),
            "5min": round(load_5, 2),
            "15min": round(load_15, 2),
        },
        "count": psutil.cpu_count(logical=True),
    }

    with _cpu_cache_lock:
        _cpu_cache["ts"] = now
        _cpu_cache["value"] = copy.deepcopy(result)
    return result


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
    now = time.time()
    with _gpu_cache_lock:
        cached = _gpu_cache["value"]
        if cached is not None and now - _gpu_cache["ts"] < settings.gpu_metrics_ttl_seconds:
            return copy.deepcopy(cached)

    result = {
        "available": False,
        "name": "",
        "util": 0,
        "mem_used": 0,
        "mem_total": 0,
        "temp": 0,
        "processes": [],
    }

    # 基础 GPU 信息
    raw = run_command_text(
        [
            "nvidia-smi",
            "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits",
        ],
        timeout=10,
        check=False,
    )
    if not raw:
        return result

    parts = [x.strip() for x in raw.split(",")]
    if len(parts) >= 5:
        result["available"] = True
        result["name"] = parts[0]
        result["util"] = int(parts[1])
        result["mem_used"] = int(parts[2])
        result["mem_total"] = int(parts[3])
        result["temp"] = int(parts[4])

    # GPU 进程列表
    procs_raw = run_command_text(
        [
            "nvidia-smi",
            "--query-compute-apps=pid,used_gpu_memory,process_name",
            "--format=csv,noheader,nounits",
        ],
        timeout=10,
        check=False,
    )
    if procs_raw:
        for line in procs_raw.splitlines():
            pparts = [x.strip() for x in line.split(",")]
            if len(pparts) >= 3:
                pid = int(pparts[0])
                user = ""
                try:
                    user = psutil.Process(pid).username()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                result["processes"].append(
                    {
                        "pid": pid,
                        "user": user,
                        "gpu_mem_mb": int(pparts[1]),
                        "used_memory": int(pparts[1]),
                        "gpu_memory_usage": int(pparts[1]),
                        "name": pparts[2],
                    }
                )

    with _gpu_cache_lock:
        _gpu_cache["ts"] = now
        _gpu_cache["value"] = copy.deepcopy(result)
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
            disks.append(
                {
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "fstype": part.fstype,
                    "total": usage.total,
                    "used": usage.used,
                    "free": usage.free,
                    "percent": usage.percent,
                }
            )
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
    except (psutil.AccessDenied, PermissionError) as e:
        logger.debug("TCP 连接状态采集受限: %s", e)

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
    "B": 1,
    "KB": 1e3,
    "KIB": 1024,
    "MB": 1e6,
    "MIB": 1024**2,
    "GB": 1e9,
    "GIB": 1024**3,
    "TB": 1e12,
    "TIB": 1024**4,
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
    raw = run_command_text(
        ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
        timeout=30,
        check=False,
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

    ps_raw = run_command_text(
        ["docker", "ps", "--format", "{{json .}}"],
        timeout=15,
        check=False,
    )
    ps_map: dict = {}
    if ps_raw:
        for line in ps_raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = item.get("Names", "")
            if name:
                ps_map[name] = {
                    "image": item.get("Image", ""),
                    "ports": item.get("Ports", ""),
                }

    # 批量获取 RestartCount 和 compose project
    inspect_result = run_command(
        [
            "docker",
            "inspect",
            "--format",
            '{{.Name}}|{{.RestartCount}}|{{index .Config.Labels "com.docker.compose.project"}}|{{.State.Status}}',
            *names,
        ],
        timeout=15,
        check=False,
    )
    inspect_raw = inspect_result.output
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
        ps_info = ps_map.get(name, {})

        container = {
            "name": name,
            "status": status,
            "state": status,
            "image": ps_info.get("image", ""),
            "ports": ps_info.get("ports", ""),
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
                "read_bytes_rate": round(read_bytes_d / dt, 1) if dt > 0 else 0.0,
                "write_bytes_rate": round(write_bytes_d / dt, 1) if dt > 0 else 0.0,
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
        result.append(
            {
                "mountpoint": part.mountpoint,
                "total": total,
                "used": used,
                "free": free,
                "percent": percent,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Top Processes
# ---------------------------------------------------------------------------


def collect_top_processes(limit: int = 15, gpu_snapshot: dict | None = None) -> dict:
    """
    采集资源占用 Top N 进程
    按 CPU、内存、GPU 显存分别排序
    """
    now = time.time()
    with _top_process_lock:
        cached = _top_process_cache["value"]
        if (
            cached is not None
            and now - _top_process_cache["ts"] < settings.top_processes_cache_seconds
            and _top_process_cache["limit"] >= limit
        ):
            return {
                "by_cpu": cached["by_cpu"][:limit],
                "by_mem": cached["by_mem"][:limit],
                "by_gpu": cached["by_gpu"][:limit],
            }

    sample_limit = max(limit, settings.top_processes_limit)

    global _top_process_cpu_primed
    if not _top_process_cpu_primed:
        for process in psutil.process_iter():
            try:
                process.cpu_percent(interval=0)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        _top_process_cpu_primed = True

    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info", "cmdline"]):
        try:
            info = p.info
            rss = info["memory_info"].rss if info.get("memory_info") else 0
            mem_percent = round(p.memory_percent(), 1)
            cmdline_parts = info.get("cmdline") or []
            cmdline = " ".join(cmdline_parts)[:200] if cmdline_parts else info.get("name", "")
            procs.append(
                {
                    "pid": info["pid"],
                    "name": info["name"] or "",
                    "user": info.get("username") or "",
                    "cpu_percent": info.get("cpu_percent") or 0.0,
                    "mem_percent": mem_percent,
                    "rss": rss,
                    "mem_rss_mb": round(rss / 1024 / 1024, 1),
                    "cmd": cmdline,
                    "cmdline": cmdline,
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    by_cpu = sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)[:sample_limit]
    by_mem = sorted(procs, key=lambda x: x["mem_rss_mb"], reverse=True)[:sample_limit]

    # GPU 进程排行
    gpu_data = gpu_snapshot or collect_gpu()
    by_gpu = sorted(
        gpu_data.get("processes", []),
        key=lambda x: x.get("gpu_mem_mb", 0),
        reverse=True,
    )[:sample_limit]

    result = {
        "by_cpu": by_cpu,
        "by_mem": by_mem,
        "by_gpu": by_gpu,
    }
    with _top_process_lock:
        _top_process_cache["ts"] = now
        _top_process_cache["limit"] = sample_limit
        _top_process_cache["value"] = copy.deepcopy(result)
    return {
        "by_cpu": result["by_cpu"][:limit],
        "by_mem": result["by_mem"][:limit],
        "by_gpu": result["by_gpu"][:limit],
    }


# ---------------------------------------------------------------------------
# Realtime Fast (lightweight, no blocking)
# ---------------------------------------------------------------------------


def collect_realtime_fast() -> dict:
    """5秒快速快照 - 仅轻量指标，不含 Docker/进程排行"""
    uptime = _format_uptime(time.time() - psutil.boot_time())
    load_1, load_5, load_15 = psutil.getloadavg()
    return {
        "timestamp": time.time(),
        "uptime": uptime,
        "system_info": collect_system_info(),
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
    uptime = _format_uptime(time.time() - psutil.boot_time())
    gpu_snapshot = collect_gpu()
    return {
        "timestamp": time.time(),
        "uptime": uptime,
        "system_info": collect_system_info(),
        "cpu": collect_cpu(),
        "memory": collect_memory(),
        "gpu": gpu_snapshot,
        "disk": collect_disk(),
        "network": collect_network(),
        "disk_io": collect_disk_io(),
        "inode": collect_inode(),
        "docker": collect_docker_stats(),
        "top_processes": collect_top_processes(gpu_snapshot=gpu_snapshot),
    }

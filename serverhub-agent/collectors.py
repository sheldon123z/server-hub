"""
ServerHub Agent 指标采集器
精简版系统指标采集，复用 hub 端 collectors.py 的核心逻辑，无数据库/WebSocket 依赖
"""

import json
import logging
import os
import platform
import re
import subprocess
import time

import psutil

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _read_os_pretty_name() -> str:
    """读取当前系统发行版名称"""
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    return line.split("=", 1)[1].strip().strip('"')
    except Exception:
        logger.debug("读取 /etc/os-release 失败，使用 platform.system() 回退", exc_info=True)
    return platform.system()


def _read_cpu_model() -> str:
    """读取 CPU 型号"""
    try:
        with open("/proc/cpuinfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        logger.debug("读取 /proc/cpuinfo 失败，使用 platform.processor() 回退", exc_info=True)
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


def _run_cmd(args: list[str], timeout: int = 10) -> str:
    """执行命令并返回 stdout，失败返回空串"""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return ""


def _safe_int(value: str, default: int = 0) -> int:
    """安全将字符串转 int，处理 N/A、空串、浮点等情况"""
    if not value:
        return default
    value = value.strip()
    try:
        return int(value)
    except ValueError:
        try:
            return int(float(value))
        except (ValueError, OverflowError):
            return default


# ---------------------------------------------------------------------------
# 系统基础信息
# ---------------------------------------------------------------------------

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
    """采集 CPU 指标"""
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
    """采集内存指标: RAM + Swap"""
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
# Disk
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
        except (PermissionError, OSError, ValueError):
            continue
    return disks


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------

_prev_net: dict = {"counters": None, "time": 0.0}


def collect_network() -> dict:
    """采集网络指标: 收发速率、错误/丢包计数"""
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

    return {"totals": totals}


# ---------------------------------------------------------------------------
# GPU (nvidia-smi)
# ---------------------------------------------------------------------------

_gpu_cache: dict = {"ts": 0.0, "value": None}
_GPU_CACHE_TTL = 10  # seconds


def collect_gpu() -> dict:
    """采集 GPU 指标（nvidia-smi），支持多 GPU

    多 GPU 时返回第一块 GPU 的概要 + gpus 列表。
    前端兼容字段: name/util/mem_used/mem_total/temp (主 GPU 概要)。
    """
    now = time.time()
    cached = _gpu_cache["value"]
    if cached is not None and now - _gpu_cache["ts"] < _GPU_CACHE_TTL:
        return cached

    result: dict = {
        "available": False,
        "name": "",
        "util": 0,
        "mem_used": 0,
        "mem_total": 0,
        "temp": 0,
        "processes": [],
        "gpus": [],
    }

    raw = _run_cmd([
        "nvidia-smi",
        "--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu",
        "--format=csv,noheader,nounits",
    ])
    if not raw:
        return result

    # 每行一块 GPU — 必须按行分割再按逗号分割
    total_util = 0
    total_mem_used = 0
    total_mem_total = 0
    max_temp = 0
    for line in raw.splitlines():
        parts = [x.strip() for x in line.split(",")]
        if len(parts) < 5:
            continue
        gpu_info = {
            "name": parts[0],
            "util": _safe_int(parts[1]),
            "mem_used": _safe_int(parts[2]),
            "mem_total": _safe_int(parts[3]),
            "temp": _safe_int(parts[4]),
        }
        result["gpus"].append(gpu_info)
        total_util += gpu_info["util"]
        total_mem_used += gpu_info["mem_used"]
        total_mem_total += gpu_info["mem_total"]
        max_temp = max(max_temp, gpu_info["temp"])

    gpu_count = len(result["gpus"])
    if gpu_count > 0:
        result["available"] = True
        result["name"] = result["gpus"][0]["name"]
        if gpu_count > 1:
            result["name"] += f" (×{gpu_count})"
        # 聚合: 平均利用率, 总显存, 最高温度
        result["util"] = round(total_util / gpu_count)
        result["mem_used"] = total_mem_used
        result["mem_total"] = total_mem_total
        result["temp"] = max_temp

    procs_raw = _run_cmd([
        "nvidia-smi",
        "--query-compute-apps=pid,used_gpu_memory,process_name",
        "--format=csv,noheader,nounits",
    ])
    if procs_raw:
        for line in procs_raw.splitlines():
            pparts = [x.strip() for x in line.split(",")]
            if len(pparts) >= 3:
                pid = _safe_int(pparts[0])
                if pid < 1:
                    continue
                user = ""
                try:
                    user = psutil.Process(pid).username()
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
                result["processes"].append({
                    "pid": pid,
                    "user": user,
                    "gpu_mem_mb": _safe_int(pparts[1]),
                    "name": pparts[2],
                })

    _gpu_cache["ts"] = now
    _gpu_cache["value"] = result
    return result


# ---------------------------------------------------------------------------
# Docker containers (简化版，只列出容器名和状态)
# ---------------------------------------------------------------------------

def collect_docker_containers() -> list[dict]:
    """列出 Docker 容器列表"""
    raw = _run_cmd(
        ["docker", "ps", "-a", "--format", "{{json .}}"],
        timeout=15,
    )
    if not raw:
        return []

    containers = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        containers.append({
            "id": item.get("ID", ""),
            "name": item.get("Names", ""),
            "image": item.get("Image", ""),
            "status": item.get("Status", ""),
            "state": item.get("State", ""),
            "ports": item.get("Ports", ""),
            "created": item.get("CreatedAt", ""),
        })
    return containers


# ---------------------------------------------------------------------------
# Systemd services (列出关键服务状态)
# ---------------------------------------------------------------------------

def collect_services() -> list[dict]:
    """列出 systemd 服务状态"""
    raw = _run_cmd(
        [
            "systemctl", "list-units", "--type=service",
            "--no-pager", "--no-legend", "--plain",
        ],
        timeout=10,
    )
    if not raw:
        return []

    services = []
    for line in raw.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 4:
            continue
        unit = parts[0]
        # 只包含 .service 单元
        if not unit.endswith(".service"):
            continue
        services.append({
            "name": unit.replace(".service", ""),
            "load": parts[1],
            "active": parts[2],
            "sub": parts[3],
            "description": parts[4] if len(parts) > 4 else "",
        })
    return services


# ---------------------------------------------------------------------------
# Top processes (简化版)
# ---------------------------------------------------------------------------

def collect_top_processes(limit: int = 10) -> dict:
    """采集 Top N 进程（按 CPU 和内存排序）"""
    procs = []
    for p in psutil.process_iter(["pid", "name", "username", "cpu_percent", "memory_info"]):
        try:
            info = p.info
            rss = info["memory_info"].rss if info.get("memory_info") else 0
            procs.append({
                "pid": info["pid"],
                "name": info["name"] or "",
                "user": info.get("username") or "",
                "cpu_percent": info.get("cpu_percent") or 0.0,
                "mem_rss_mb": round(rss / 1024 / 1024, 1),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    by_cpu = sorted(procs, key=lambda x: x["cpu_percent"], reverse=True)[:limit]
    by_mem = sorted(procs, key=lambda x: x["mem_rss_mb"], reverse=True)[:limit]

    return {"by_cpu": by_cpu, "by_mem": by_mem}


# ---------------------------------------------------------------------------
# 聚合采集
# ---------------------------------------------------------------------------

def collect_all() -> dict:
    """完整指标快照"""
    uptime_s = time.time() - psutil.boot_time()
    return {
        "timestamp": time.time(),
        "hostname": platform.node(),
        "uptime": _format_uptime(uptime_s),
        "uptime_seconds": uptime_s,
        "system_info": collect_system_info(),
        "cpu": collect_cpu(),
        "memory": collect_memory(),
        "gpu": collect_gpu(),
        "disk": collect_disk(),
        "network": collect_network(),
        "docker": {"containers": collect_docker_containers()},
        "top_processes": collect_top_processes(),
    }


def collect_fast() -> dict:
    """轻量级快速快照（无阻塞调用）"""
    vm = psutil.virtual_memory()
    gpu = collect_gpu()
    disks = []
    for part in psutil.disk_partitions(all=False):
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mountpoint": part.mountpoint,
                "percent": usage.percent,
            })
        except (PermissionError, OSError, ValueError):
            continue

    return {
        "timestamp": time.time(),
        "hostname": platform.node(),
        "cpu_percent": psutil.cpu_percent(interval=0),
        "memory_percent": vm.percent,
        "memory_used": vm.used,
        "memory_total": vm.total,
        "disk": disks,
        "gpu_util": gpu.get("util", 0) if gpu.get("available") else None,
        "gpu_mem_used": gpu.get("mem_used", 0) if gpu.get("available") else None,
        "gpu_mem_total": gpu.get("mem_total", 0) if gpu.get("available") else None,
        "load_avg": list(psutil.getloadavg()),
    }

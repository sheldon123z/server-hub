"""
系统指标采集模块
采集 CPU、内存、GPU、磁盘等系统指标
"""

import subprocess
import time

import psutil


def _run(cmd: str) -> str:
    """执行 shell 命令并返回 stdout"""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except Exception:
        return ""


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


def collect_all() -> dict:
    """采集所有系统指标的完整快照"""
    return {
        "timestamp": time.time(),
        "cpu": collect_cpu(),
        "memory": collect_memory(),
        "gpu": collect_gpu(),
        "disk": collect_disk(),
    }

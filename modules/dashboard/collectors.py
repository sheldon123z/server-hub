"""系统信息采集（移植自 server-panel.py）"""

import subprocess
import psutil
from datetime import datetime


def run(cmd: str, timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip()
    except Exception:
        return ""


def get_system_info() -> dict:
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    disk = psutil.disk_usage("/")
    load = psutil.getloadavg()
    cpu_count = psutil.cpu_count()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = str(datetime.now() - boot_time).split(".")[0]

    cpu_percent = psutil.cpu_percent(interval=0.5)

    gpu = {}
    gpu_raw = run("nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>/dev/null")
    if gpu_raw:
        parts = [x.strip() for x in gpu_raw.split(",")]
        if len(parts) >= 4:
            gpu = {
                "util": int(parts[0]),
                "mem_used": int(parts[1]),
                "mem_total": int(parts[2]),
                "temp": int(parts[3]),
            }

    return {
        "mem_total": mem.total,
        "mem_used": mem.used,
        "mem_percent": mem.percent,
        "swap_total": swap.total,
        "swap_used": swap.used,
        "swap_percent": swap.percent,
        "disk_total": disk.total,
        "disk_used": disk.used,
        "disk_percent": disk.percent,
        "load": [round(x, 2) for x in load],
        "cpu_count": cpu_count,
        "cpu_percent": cpu_percent,
        "uptime": uptime,
        "gpu": gpu,
        "hostname": run("hostname"),
        "timestamp": datetime.now().isoformat(),
    }


def get_extra_disks() -> list[dict]:
    """获取额外挂载点信息"""
    disks = []
    for part in psutil.disk_partitions():
        if part.mountpoint in ("/", "/boot", "/boot/efi"):
            continue
        if not part.mountpoint.startswith("/mnt"):
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mountpoint": part.mountpoint,
                "device": part.device,
                "total": usage.total,
                "used": usage.used,
                "percent": usage.percent,
            })
        except Exception:
            pass
    return disks

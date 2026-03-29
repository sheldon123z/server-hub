"""
Systemd 服务管理服务层
通过 systemctl / journalctl 异步查询和控制系统服务
"""

import asyncio

from utils.command import run_command_async

from config import settings


async def _run(cmd: list[str], timeout: int = 15, check: bool = True) -> tuple[int, str]:
    """
    执行命令，返回 (returncode, stdout)

    Args:
        cmd: 命令参数列表
        timeout: 超时秒数
        check: 是否在失败时抛异常

    Returns:
        (returncode, stdout)
    """
    result = await run_command_async(cmd, timeout=timeout, check=check)
    return result.returncode, result.output


def _validate_service(name: str) -> str:
    """校验服务名是否在白名单中"""
    if name not in settings.managed_services:
        raise ValueError(f"不在受管服务列表中: {name}")
    return name


async def list_services() -> list[dict]:
    """
    列出所有受管 systemd 服务的状态

    Returns:
        服务状态列表
    """
    services = []

    for name in settings.managed_services:
        # 并行查询 is-active 和 is-enabled
        active_task = _run(["systemctl", "is-active", name], check=False)
        enabled_task = _run(["systemctl", "is-enabled", name], check=False)

        (active_rc, active_out), (enabled_rc, enabled_out) = await asyncio.gather(active_task, enabled_task)

        services.append(
            {
                "name": name,
                "active": active_rc == 0,
                "enabled": enabled_out.strip() == "enabled",
                "status_text": active_out.strip(),
            }
        )

    return services


async def service_status(name: str) -> str:
    """
    获取服务的详细状态输出

    Args:
        name: 服务名（必须在受管列表中）

    Returns:
        systemctl status 完整输出
    """
    _validate_service(name)
    # systemctl status 对非活跃服务返回非零，不做 check
    _, output = await _run(["systemctl", "status", name], check=False, timeout=10)
    return output


async def service_action(name: str, action: str) -> str:
    """
    对服务执行操作（start / stop / restart）

    Args:
        name: 服务名（必须在受管列表中）
        action: start / stop / restart

    Returns:
        命令输出
    """
    _validate_service(name)
    if action not in {"start", "stop", "restart"}:
        raise ValueError(f"不支持的操作: {action}")

    _, output = await _run(
        ["sudo", "systemctl", action, name],
        timeout=30,
    )
    return output


async def service_journal(name: str, lines: int = 100) -> str:
    """
    获取服务的 journal 日志

    Args:
        name: 服务名（必须在受管列表中）
        lines: 返回最近多少行

    Returns:
        日志文本
    """
    _validate_service(name)
    lines = min(max(lines, 1), 5000)

    _, output = await _run(
        ["journalctl", "-u", name, "-n", str(lines), "--no-pager"],
        check=False,
        timeout=15,
    )
    return output


# ─── 自启动管理 ───


async def service_enable_disable(name: str, action: str) -> str:
    """启用或禁用服务自启动

    Args:
        name: 服务名（必须在受管列表中）
        action: enable / disable
    """
    _validate_service(name)
    if action not in {"enable", "disable"}:
        raise ValueError(f"不支持的操作: {action}")

    _, output = await _run(
        ["sudo", "systemctl", action, name],
        timeout=15,
    )
    return output


async def service_reload(name: str) -> str:
    """重新加载服务配置（不重启）"""
    _validate_service(name)
    _, output = await _run(
        ["sudo", "systemctl", "reload", name],
        timeout=15,
    )
    return output


# ─── 资源使用 ───


async def service_resource_usage(name: str) -> dict:
    """获取服务的资源使用情况"""
    _validate_service(name)
    _, output = await _run(
        ["systemctl", "show", name, "-p", "MemoryCurrent,CPUUsageNSec,MainPID,Tasks"],
        check=False,
        timeout=10,
    )
    result = {}
    for line in output.splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            result[key] = val.strip()

    # 转换内存为人类可读
    mem = result.get("MemoryCurrent", "[not set]")
    if mem.isdigit():
        mem_mb = round(int(mem) / 1024 / 1024, 1)
        result["MemoryMB"] = mem_mb

    # 转换 CPU 时间
    cpu_ns = result.get("CPUUsageNSec", "0")
    if cpu_ns.isdigit():
        cpu_sec = round(int(cpu_ns) / 1_000_000_000, 2)
        result["CPUSeconds"] = cpu_sec

    return result


# ─── 依赖关系 ───


async def service_dependencies(name: str) -> dict:
    """获取服务的依赖关系"""
    _validate_service(name)
    _, output = await _run(
        ["systemctl", "list-dependencies", name, "--no-pager"],
        check=False,
        timeout=10,
    )
    # 解析缩进树形结构
    deps = []
    for line in output.splitlines():
        stripped = line.lstrip("│ ├└─●")
        stripped = stripped.strip()
        if stripped and stripped != name:
            deps.append(stripped)
    return {"service": name, "dependencies": deps, "raw": output}

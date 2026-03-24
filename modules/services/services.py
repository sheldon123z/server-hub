"""
Systemd 服务管理服务层
通过 systemctl / journalctl 异步查询和控制系统服务
"""

import asyncio

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
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"命令超时 ({timeout}s): {' '.join(cmd)}")

    output = stdout.decode("utf-8", errors="replace").strip()

    if check and proc.returncode != 0:
        raise RuntimeError(f"命令失败 (exit={proc.returncode}): {output}")

    return proc.returncode, output


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

        (active_rc, active_out), (enabled_rc, enabled_out) = await asyncio.gather(
            active_task, enabled_task
        )

        services.append({
            "name": name,
            "active": active_rc == 0,
            "enabled": enabled_out.strip() == "enabled",
            "status_text": active_out.strip(),
        })

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

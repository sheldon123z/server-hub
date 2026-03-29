"""
安全脚本执行引擎
基于白名单注册表，防止命令注入，支持异步执行和审计日志
"""

import asyncio
import re

from modules.audit.middleware import log_audit
from scripts_bridge.registry import SCRIPT_REGISTRY

# 禁止 shell 元字符
_SHELL_META_RE = re.compile(r"[;&|`$(){}!\\\n\r]")


def _sanitize_arg(arg: str) -> str:
    """检查参数中是否包含 shell 元字符"""
    if _SHELL_META_RE.search(arg):
        raise ValueError(f"参数包含非法字符: {arg}")
    return arg


async def execute_script(
    script_key: str,
    args: list[str],
    username: str,
    ip: str,
) -> dict:
    """
    安全执行注册表中的脚本

    Args:
        script_key: 注册表中的脚本标识
        args: 参数列表（每个参数必须在 allowed_args 白名单中）
        username: 操作用户名（用于审计）
        ip: 客户端 IP（用于审计）

    Returns:
        dict: exit_code, stdout, stderr

    Raises:
        ValueError: 脚本不存在、参数非法
        RuntimeError: 执行超时或失败
    """
    # 校验脚本是否注册
    if script_key not in SCRIPT_REGISTRY:
        raise ValueError(f"未注册的脚本: {script_key}")

    entry = SCRIPT_REGISTRY[script_key]
    allowed = entry["allowed_args"]

    # 校验每个参数
    for arg in args:
        _sanitize_arg(arg)
        if allowed and arg not in allowed:
            raise ValueError(f"参数 '{arg}' 不在白名单中 (脚本: {script_key})")

    # 构建命令
    cmd = []
    if entry.get("sudo"):
        cmd.append("sudo")
    cmd.append(entry["path"])
    cmd.extend(args)

    timeout = entry.get("timeout", 30)

    # 执行
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        # 记录超时审计
        await log_audit(
            username=username,
            action="script.timeout",
            target=f"{script_key} {' '.join(args)}",
            ip=ip,
            detail=f"脚本执行超时 ({timeout}s)",
        )
        raise RuntimeError(f"脚本执行超时 ({timeout}s): {script_key}")

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")

    # 审计日志
    status_text = "success" if proc.returncode == 0 else f"failed (exit={proc.returncode})"
    await log_audit(
        username=username,
        action=f"script.execute.{status_text}",
        target=f"{script_key} {' '.join(args)}",
        ip=ip,
        detail=stdout[:500] if stdout else stderr[:500],
    )

    return {
        "exit_code": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }

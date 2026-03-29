"""共享子进程执行工具。"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class CommandResult:
    """统一的命令执行结果。"""

    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        parts = [self.stdout.strip(), self.stderr.strip()]
        return "\n".join(part for part in parts if part).strip()


def run_command(
    args: Sequence[str],
    *,
    timeout: int = 10,
    check: bool = False,
    input_text: str | None = None,
) -> CommandResult:
    """以非 shell 方式执行命令。"""
    try:
        completed = subprocess.run(
            list(args),
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"命令超时 ({timeout}s): {' '.join(args)}") from exc
    except OSError as exc:
        raise RuntimeError(f"命令启动失败: {' '.join(args)}") from exc

    result = CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"命令失败 (exit={result.returncode}): {result.output or '无输出'}")
    return result


def run_command_text(
    args: Sequence[str],
    *,
    timeout: int = 10,
    check: bool = False,
) -> str:
    """执行命令并返回合并后的文本输出。"""
    return run_command(args, timeout=timeout, check=check).output


async def run_command_async(
    args: Sequence[str],
    *,
    timeout: int = 15,  # noqa: ASYNC109 — timeout 传给 asyncio.wait_for
    check: bool = False,
) -> CommandResult:
    """异步执行命令。"""
    proc = await asyncio.create_subprocess_exec(
        *list(args),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"命令超时 ({timeout}s): {' '.join(args)}") from exc

    result = CommandResult(
        returncode=proc.returncode,
        stdout=stdout.decode("utf-8", errors="replace").strip(),
        stderr=stderr.decode("utf-8", errors="replace").strip(),
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"命令失败 (exit={result.returncode}): {result.output or '无输出'}")
    return result

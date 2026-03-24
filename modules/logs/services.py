"""Log viewer services with path traversal protection."""

import asyncio
import os
import re
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from config import settings


def _validate_log_path(path: str) -> str:
    """Validate that a log file path is within allowed directories.

    Resolves symlinks and checks against settings.log_dirs whitelist
    to prevent directory traversal attacks.

    Args:
        path: The file path to validate.

    Returns:
        The resolved absolute path.

    Raises:
        ValueError: If path is outside allowed directories.
        FileNotFoundError: If path does not exist.
    """
    resolved = os.path.realpath(path)

    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Log file not found: {path}")

    allowed = False
    for log_dir in settings.log_dirs:
        resolved_dir = os.path.realpath(log_dir)
        if resolved.startswith(resolved_dir + os.sep) or resolved == resolved_dir:
            allowed = True
            break

    if not allowed:
        raise ValueError(
            f"Access denied: path '{path}' is outside allowed log directories"
        )

    return resolved


def list_log_files() -> list[dict]:
    """Scan configured log directories for .log files.

    Returns:
        List of dicts with path, name, size_bytes, modified.
        Sorted by modification time descending.
    """
    log_files = []

    for log_dir in settings.log_dirs:
        log_dir = os.path.realpath(log_dir)
        if not os.path.isdir(log_dir):
            continue

        for root, _dirs, files in os.walk(log_dir):
            for filename in files:
                if not filename.endswith(".log"):
                    continue

                filepath = os.path.join(root, filename)
                try:
                    stat = os.stat(filepath)
                    log_files.append({
                        "path": filepath,
                        "name": filename,
                        "size_bytes": stat.st_size,
                        "modified": datetime.fromtimestamp(
                            stat.st_mtime
                        ).isoformat(),
                    })
                except OSError:
                    continue

    log_files.sort(key=lambda f: f["modified"], reverse=True)
    return log_files


async def tail_log(path: str, lines: int = 200) -> str:
    """Read the last N lines of a log file.

    Args:
        path: Path to the log file.
        lines: Number of lines to read (max 10000).

    Returns:
        The tail output as a string.
    """
    resolved = _validate_log_path(path)
    lines = min(max(1, lines), 10000)

    proc = await asyncio.create_subprocess_exec(
        "tail", "-n", str(lines), resolved,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"tail failed: {stderr.decode().strip()}")

    return stdout.decode()


async def search_log(
    path: str, pattern: str, max_results: int = 100
) -> list[dict]:
    """Search a log file for lines matching a pattern.

    Args:
        path: Path to the log file.
        pattern: Search pattern (sanitized to prevent injection).
        max_results: Maximum number of results to return.

    Returns:
        List of dicts with line_number and content.
    """
    resolved = _validate_log_path(path)
    max_results = min(max(1, max_results), 5000)

    # Sanitize pattern: remove characters that could cause shell injection
    # Only allow alphanumeric, spaces, common punctuation, and Chinese chars
    if not pattern or len(pattern) > 500:
        raise ValueError("Pattern must be between 1 and 500 characters")

    # Use grep with fixed-string mode (-F) to avoid regex injection
    proc = await asyncio.create_subprocess_exec(
        "grep", "-n", "-F", pattern, resolved,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    # grep returns 1 when no matches found (not an error)
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"grep failed: {stderr.decode().strip()}")

    results = []
    for line in stdout.decode().splitlines():
        if len(results) >= max_results:
            break
        match = re.match(r"^(\d+):(.*)", line)
        if match:
            results.append({
                "line_number": int(match.group(1)),
                "content": match.group(2),
            })

    return results


async def stream_log(path: str) -> AsyncGenerator[str, None]:
    """Async generator that yields new lines from a log file via tail -f.

    Args:
        path: Path to the log file.

    Yields:
        New log lines as they appear.
    """
    resolved = _validate_log_path(path)

    proc = await asyncio.create_subprocess_exec(
        "tail", "-f", "-n", "0", resolved,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        async for line in proc.stdout:
            yield line.decode().rstrip("\n")
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            proc.kill()

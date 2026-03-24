"""
Docker 容器管理服务层
通过 CLI 异步调用 docker / docker compose 命令
"""

import asyncio
import json
import re
from typing import Optional

from config import settings

# 容器/镜像名称校验正则
_NAME_RE = re.compile(r"^[a-zA-Z0-9_.\-]+$")
# 镜像 ID 校验（短 ID 或 sha256 长 ID）
_IMAGE_ID_RE = re.compile(r"^[a-zA-Z0-9:._\-/]+$")


def _validate_name(name: str) -> str:
    """校验容器/镜像名称，防止命令注入"""
    if not _NAME_RE.match(name):
        raise ValueError(f"非法名称: {name}")
    return name


def _validate_image_id(image_id: str) -> str:
    """校验镜像 ID"""
    if not _IMAGE_ID_RE.match(image_id):
        raise ValueError(f"非法镜像 ID: {image_id}")
    return image_id


async def run_cmd(cmd: list[str], timeout: int = 30) -> str:
    """
    异步执行子进程命令，返回 stdout 字符串

    Args:
        cmd: 命令参数列表
        timeout: 超时秒数

    Returns:
        stdout 输出

    Raises:
        RuntimeError: 命令执行失败或超时
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"命令超时 ({timeout}s): {' '.join(cmd)}")

    if proc.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"命令执行失败 (exit={proc.returncode}): {err_msg}")

    return stdout.decode("utf-8", errors="replace").strip()


async def list_containers(all: bool = True) -> list[dict]:
    """
    列出 Docker 容器

    Args:
        all: 是否包含已停止的容器

    Returns:
        容器信息列表
    """
    cmd = ["docker", "ps", "--format", "json"]
    if all:
        cmd.insert(2, "-a")

    output = await run_cmd(cmd)
    if not output:
        return []

    containers = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            containers.append({
                "name": raw.get("Names", ""),
                "id": raw.get("ID", ""),
                "image": raw.get("Image", ""),
                "status": raw.get("Status", ""),
                "ports": raw.get("Ports", ""),
                "state": raw.get("State", ""),
                "created": raw.get("CreatedAt", ""),
            })
        except json.JSONDecodeError:
            continue

    return containers


async def container_stats(name: str) -> dict:
    """获取容器资源使用统计"""
    _validate_name(name)
    output = await run_cmd(
        ["docker", "stats", name, "--no-stream", "--format", "json"],
        timeout=15,
    )
    if not output:
        return {}

    # docker stats --format json 输出单行 JSON
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            return {
                "name": raw.get("Name", name),
                "cpu_percent": raw.get("CPUPerc", "0%"),
                "memory_usage": raw.get("MemUsage", ""),
                "memory_percent": raw.get("MemPerc", "0%"),
                "net_io": raw.get("NetIO", ""),
                "block_io": raw.get("BlockIO", ""),
                "pids": raw.get("PIDs", "0"),
            }
        except json.JSONDecodeError:
            continue

    return {}


async def container_logs(name: str, tail: int = 100) -> str:
    """
    获取容器日志

    Args:
        name: 容器名称（经过校验）
        tail: 返回最近多少行

    Returns:
        日志文本
    """
    _validate_name(name)
    tail = min(max(tail, 1), 5000)

    proc = await asyncio.create_subprocess_exec(
        "docker", "logs", "--tail", str(tail), "--timestamps", name,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30)
    return stdout.decode("utf-8", errors="replace")


async def container_action(name: str, action: str) -> str:
    """
    对容器执行操作（start / stop / restart）

    Returns:
        命令输出
    """
    _validate_name(name)
    if action not in {"start", "stop", "restart"}:
        raise ValueError(f"不支持的操作: {action}")

    return await run_cmd(["docker", action, name], timeout=60)


async def container_inspect(name: str) -> dict:
    """获取容器完整 inspect 信息"""
    _validate_name(name)
    output = await run_cmd(["docker", "inspect", name], timeout=15)
    data = json.loads(output)
    if isinstance(data, list) and data:
        return data[0]
    return data


async def list_images() -> list[dict]:
    """列出本地 Docker 镜像"""
    output = await run_cmd(["docker", "images", "--format", "json"])
    if not output:
        return []

    images = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            images.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return images


async def remove_image(image_id: str) -> str:
    """删除指定镜像"""
    _validate_image_id(image_id)
    return await run_cmd(["docker", "rmi", image_id], timeout=30)


async def list_compose_stacks() -> list[dict]:
    """
    列出配置中的 Docker Compose 堆栈及其运行状态

    Returns:
        堆栈信息列表，包含名称、路径、容器数、运行数
    """
    stacks = []

    for name, info in settings.compose_stacks.items():
        stack_path = info["path"]
        compose_file = f"{stack_path}/docker-compose.yml"
        entry = {
            "name": name,
            "display_name": info.get("display_name", name),
            "path": stack_path,
            "containers": 0,
            "running": 0,
            "error": None,
        }

        try:
            output = await run_cmd(
                ["docker", "compose", "-f", compose_file, "ps", "--format", "json"],
                timeout=15,
            )
            if output:
                for line in output.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        svc = json.loads(line)
                        entry["containers"] += 1
                        state = svc.get("State", "").lower()
                        if state == "running":
                            entry["running"] += 1
                    except json.JSONDecodeError:
                        continue
        except RuntimeError as e:
            entry["error"] = str(e)

        stacks.append(entry)

    return stacks


async def compose_action(stack_name: str, action: str) -> str:
    """
    对 Compose 堆栈执行操作

    Args:
        stack_name: 堆栈名称（必须在 settings.compose_stacks 中）
        action: up / down / restart / pull
    """
    if action not in {"up", "down", "restart", "pull"}:
        raise ValueError(f"不支持的 Compose 操作: {action}")

    if stack_name not in settings.compose_stacks:
        raise ValueError(f"未知的堆栈: {stack_name}")

    stack_info = settings.compose_stacks[stack_name]
    compose_file = f"{stack_info['path']}/docker-compose.yml"

    if action == "up":
        cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]
    elif action == "down":
        cmd = ["docker", "compose", "-f", compose_file, "down"]
    elif action == "restart":
        cmd = ["docker", "compose", "-f", compose_file, "restart"]
    elif action == "pull":
        cmd = ["docker", "compose", "-f", compose_file, "pull"]

    return await run_cmd(cmd, timeout=120)

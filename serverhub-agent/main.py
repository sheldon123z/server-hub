"""
ServerHub Agent — 轻量级服务器监控代理

部署在被管服务器上，提供系统指标采集、结构化操作、Docker/服务状态查询。
Hub 端通过 HTTP + Bearer Token 与本 agent 通信。

安全设计: 优先使用结构化 action 端点 (create_subprocess_exec)，
         避免 shell 注入。/execute 端点默认禁用，仅在调试模式下可选启用。
"""

import asyncio
import logging
import os
import platform
import re
import time
from contextlib import asynccontextmanager

import psutil
from collectors import (
    collect_all,
    collect_docker_containers,
    collect_fast,
    collect_services,
)
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from config import AGENT_PORT, AGENT_TOKEN

# 是否允许原始命令执行（默认禁用，仅调试用）
ALLOW_EXECUTE: bool = os.environ.get("AGENT_ALLOW_EXECUTE", "false").lower() in ("true", "1", "yes")

__version__ = "0.1.0"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("serverhub-agent")

# ---------------------------------------------------------------------------
# 启动/关闭
# ---------------------------------------------------------------------------

_boot_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info(
        "ServerHub Agent v%s 启动 — port=%d, hostname=%s",
        __version__,
        AGENT_PORT,
        platform.node(),
    )
    # 预热 CPU 百分比采集（首次调用返回 0）
    psutil.cpu_percent(interval=0)
    yield
    logger.info("ServerHub Agent 关闭")


app = FastAPI(
    title="ServerHub Agent",
    version=__version__,
    docs_url=None,
    redoc_url=None,
)


# ---------------------------------------------------------------------------
# 认证
# ---------------------------------------------------------------------------


async def verify_token(authorization: str = Header(None)) -> None:
    """验证 Bearer Token"""
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != AGENT_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")


# ---------------------------------------------------------------------------
# 输入校验辅助
# ---------------------------------------------------------------------------

# 合法的服务名: 字母数字 + _@.- (匹配 systemd unit 命名规范)
_RE_SERVICE_NAME = re.compile(r"^[a-zA-Z0-9_@.\-]+$")
# 合法的容器名/ID: 字母数字 + _.- (Docker 规范)
_RE_CONTAINER_NAME = re.compile(r"^[a-zA-Z0-9_.\-]+$")
# 合法的用户名
_RE_USERNAME = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_name(value: str, pattern: re.Pattern, label: str) -> None:
    """校验名称参数，不合法则抛 400"""
    if not value or not pattern.match(value):
        raise HTTPException(status_code=400, detail=f"无效的{label}: {value!r}")


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class ExecuteRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=4096, description="要执行的 shell 命令")
    timeout: int = Field(default=30, ge=1, le=300, description="超时秒数")


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


class ServiceActionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256, description="systemd 服务名")
    action: str = Field(..., description="操作: start/stop/restart/reload/status")


class ServiceJournalRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256, description="systemd 服务名")
    lines: int = Field(default=100, ge=1, le=5000, description="日志行数")


class DockerActionRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256, description="容器名或 ID")
    action: str = Field(..., description="操作: start/stop/restart/rm/logs/inspect")
    tail: int = Field(default=200, ge=1, le=5000, description="logs 时的尾行数")


class DockerImagesRequest(BaseModel):
    """Docker 镜像列表请求（无需 shell）"""


class DockerStacksRequest(BaseModel):
    """Docker Compose 堆栈列表请求"""


class KillProcessRequest(BaseModel):
    pid: int = Field(..., ge=2, description="要终止的进程 PID (>= 2)")


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    """健康检查 — 无需认证"""
    uptime_s = time.time() - psutil.boot_time()
    return {
        "status": "ok",
        "version": __version__,
        "hostname": platform.node(),
        "uptime": uptime_s,
        "agent_port": AGENT_PORT,
    }


@app.get("/metrics", dependencies=[Depends(verify_token)])
async def get_metrics():
    """完整指标快照（CPU 采集有 1s 阻塞，放到线程池）"""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, collect_all)
    return data


@app.get("/metrics/fast", dependencies=[Depends(verify_token)])
async def get_fast_metrics():
    """轻量级指标快照（无阻塞）"""
    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, collect_fast)
    return data


@app.get("/assets/discover", dependencies=[Depends(verify_token)])
async def discover_assets():
    """资产发现 — 从本机采集 systemd 服务、Docker 容器/堆栈、监听端口、存储挂载"""
    loop = asyncio.get_event_loop()
    assets = await loop.run_in_executor(None, _collect_assets)
    return assets


def _collect_assets() -> list[dict]:
    """同步采集所有资产类型"""
    import subprocess

    assets: list[dict] = []

    # ─── systemd 服务 ───
    try:
        svc_data = collect_services()
        for s in svc_data:
            assets.append({
                "id": f"service:{s['name']}",
                "type": "service",
                "name": s["name"],
                "status": "running" if s.get("active_state") == "active" else "stopped",
                "properties": {
                    "enabled": s.get("enabled", False),
                    "description": s.get("description", ""),
                },
            })
    except Exception as e:
        logging.debug("服务资产发现失败: %s", e)

    # ─── Docker 容器 ───
    try:
        containers = collect_docker_containers()
        for c in containers:
            name = c.get("name", "?").lstrip("/")
            raw_status = c.get("status", "unknown")
            assets.append({
                "id": f"container:{name}",
                "type": "container",
                "name": name,
                "status": "running" if c.get("running") else "stopped",
                "properties": {
                    "image": c.get("image", ""),
                    "status_detail": raw_status,
                },
            })
    except Exception as e:
        logging.debug("容器资产发现失败: %s", e)

    # ─── 监听端口 ───
    try:
        import psutil as _ps

        for conn in _ps.net_connections(kind="inet"):
            if conn.status == "LISTEN" and conn.laddr:
                port_str = f"{conn.laddr.port}/tcp"
                proc_name = ""
                try:
                    proc_name = _ps.Process(conn.pid).name() if conn.pid else ""
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                assets.append({
                    "id": f"port:{port_str}",
                    "type": "port",
                    "name": port_str,
                    "status": "listening",
                    "properties": {
                        "local_addr": f"{conn.laddr.ip}:{conn.laddr.port}",
                        "pid": conn.pid or 0,
                        "process": proc_name,
                    },
                })
    except Exception as e:
        logging.debug("端口资产发现失败: %s", e)

    # ─── 存储挂载 ───
    try:
        for part in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(part.mountpoint)
                assets.append({
                    "id": f"storage:{part.mountpoint}",
                    "type": "storage",
                    "name": part.mountpoint,
                    "status": "warning" if usage.percent > 85 else "ok",
                    "properties": {
                        "device": part.device,
                        "total": usage.total,
                        "used": usage.used,
                        "percent": usage.percent,
                    },
                })
            except (PermissionError, OSError, ValueError):
                continue
    except Exception as e:
        logging.debug("存储资产发现失败: %s", e)

    return assets


@app.post("/execute", dependencies=[Depends(verify_token)], response_model=ExecuteResponse)
async def execute_command(req: ExecuteRequest):
    """
    在远程服务器上执行原始 shell 命令。

    ⚠️ 安全风险: 此端点使用 create_subprocess_shell，存在 shell 注入风险。
    默认禁用，需设置 AGENT_ALLOW_EXECUTE=true 环境变量才能启用。
    生产环境请使用 /actions/* 结构化端点替代。
    """
    if not ALLOW_EXECUTE:
        raise HTTPException(
            status_code=403,
            detail="原始命令执行已禁用。请使用结构化 action 端点，"
            "或设置 AGENT_ALLOW_EXECUTE=true 启用（仅建议调试用）。",
        )

    # 安全：拒绝一些极端危险的命令模式
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", ":(){ :|:& };:"]
    cmd_lower = req.command.lower().strip()
    for pattern in dangerous:
        if pattern in cmd_lower:
            raise HTTPException(status_code=400, detail=f"命令被安全策略拒绝: 包含危险模式 '{pattern}'")

    logger.warning("执行原始命令 (调试模式): %s", req.command[:200])
    try:
        proc = await asyncio.create_subprocess_shell(
            req.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=req.timeout)
        return ExecuteResponse(
            stdout=stdout.decode("utf-8", errors="replace"),
            stderr=stderr.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
        )
    except TimeoutError:
        try:
            proc.kill()
            await proc.communicate()
        except Exception:
            logger.debug("超时后 kill 进程失败", exc_info=True)
        raise HTTPException(status_code=408, detail=f"命令执行超时 ({req.timeout}s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"命令执行失败: {e!s}")


# ---------------------------------------------------------------------------
# 辅助: 安全执行子进程 (create_subprocess_exec, 无 shell 注入风险)
# ---------------------------------------------------------------------------


async def _safe_exec(
    args: list[str],
    timeout: int = 30,
    label: str = "command",
) -> dict:
    """
    使用 create_subprocess_exec 安全执行命令。
    返回 {"stdout": str, "stderr": str, "exit_code": int}。
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "exit_code": proc.returncode or 0,
        }
    except TimeoutError:
        try:
            proc.kill()
            await proc.communicate()
        except Exception:
            logger.debug("超时后 kill 进程失败: %s", label, exc_info=True)
        raise HTTPException(status_code=408, detail=f"{label} 执行超时 ({timeout}s)")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=f"命令不存在: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{label} 执行失败: {e}")


# ---------------------------------------------------------------------------
# 结构化 action 端点 — 使用 create_subprocess_exec，无 shell 注入
# ---------------------------------------------------------------------------


@app.post("/actions/service", dependencies=[Depends(verify_token)])
async def service_action(body: ServiceActionRequest):
    """结构化 systemd 服务控制 — 无 shell 注入风险

    返回格式: {"stdout": ..., "stderr": ..., "exit_code": ..., "output": ...}
    Hub 端 AgentClient._request() 会自动包装为 {"ok": true, "data": {...}}。
    """
    ALLOWED_ACTIONS = {"start", "stop", "restart", "reload", "status"}
    if body.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"无效操作: {body.action}，允许: {ALLOWED_ACTIONS}")
    _validate_name(body.name, _RE_SERVICE_NAME, "服务名")

    result = await _safe_exec(
        ["sudo", "systemctl", body.action, body.name],
        timeout=30,
        label=f"systemctl {body.action} {body.name}",
    )
    return {
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "output": result["stdout"] + result["stderr"],
    }


@app.post("/actions/service/journal", dependencies=[Depends(verify_token)])
async def service_journal(body: ServiceJournalRequest):
    """获取 systemd 服务 journal 日志 — 无 shell 注入风险

    返回格式: {"stdout": ..., "stderr": ..., "exit_code": ..., "output": ...}
    """
    _validate_name(body.name, _RE_SERVICE_NAME, "服务名")

    result = await _safe_exec(
        ["journalctl", "-u", body.name, "-n", str(body.lines), "--no-pager"],
        timeout=15,
        label=f"journalctl -u {body.name}",
    )
    return {
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "output": result["stdout"] + result["stderr"],
    }


@app.post("/actions/docker", dependencies=[Depends(verify_token)])
async def docker_action(body: DockerActionRequest):
    """结构化 Docker 容器控制 — 无 shell 注入风险

    返回格式: {"stdout": ..., "stderr": ..., "exit_code": ..., "output": ...}
    Hub 端 AgentClient._request() 会自动包装为 {"ok": true, "data": {...}}。
    output 是 stdout+stderr 的合并便捷字段。
    """
    ALLOWED_ACTIONS = {"start", "stop", "restart", "rm", "logs", "inspect"}
    if body.action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail=f"无效操作: {body.action}，允许: {ALLOWED_ACTIONS}")
    _validate_name(body.name, _RE_CONTAINER_NAME, "容器名")

    if body.action == "logs":
        args = ["docker", "logs", "--tail", str(body.tail), body.name]
        result = await _safe_exec(args, timeout=15, label=f"docker logs {body.name}")
    else:
        args = ["docker", body.action, body.name]
        result = await _safe_exec(args, timeout=30, label=f"docker {body.action} {body.name}")

    return {
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "exit_code": result["exit_code"],
        "output": result["stdout"] + result["stderr"],
    }


@app.get("/actions/docker/images", dependencies=[Depends(verify_token)])
async def docker_images():
    """列出 Docker 镜像 — 无 shell 注入风险"""
    result = await _safe_exec(
        [
            "docker",
            "images",
            "--format",
            '{"repository":"{{.Repository}}","tag":"{{.Tag}}","id":"{{.ID}}","size":"{{.Size}}","created":"{{.CreatedSince}}"}',
        ],
        timeout=15,
        label="docker images",
    )
    return {"output": result["stdout"], "exit_code": result["exit_code"]}


@app.get("/actions/docker/stacks", dependencies=[Depends(verify_token)])
async def docker_stacks():
    """列出 Docker Compose 堆栈 — 无 shell 注入风险"""
    result = await _safe_exec(
        ["docker", "compose", "ls", "--format", "json"],
        timeout=15,
        label="docker compose ls",
    )
    return {"output": result["stdout"], "exit_code": result["exit_code"]}


@app.get("/logs/files", dependencies=[Depends(verify_token)])
async def log_files():
    """列出 /var/log 下的日志文件 — 无 shell 注入风险"""
    result = await _safe_exec(
        [
            "find",
            "/var/log",
            "-maxdepth",
            "3",
            "-type",
            "f",
            "(",
            "-name",
            "*.log",
            "-o",
            "-name",
            "syslog",
            "-o",
            "-name",
            "auth.log",
            ")",
        ],
        timeout=10,
        label="find /var/log",
    )
    files = [f.strip() for f in result["stdout"].strip().splitlines() if f.strip()]
    return {"files": files[:50]}


@app.get("/logs/tail", dependencies=[Depends(verify_token)])
async def log_tail(
    path: str = Query(..., description="日志文件路径"),
    lines: int = Query(default=200, ge=1, le=10000, description="尾行数"),
):
    """读取日志文件末尾 — 路径限制在 /var/log 下，无 shell 注入"""
    # 路径安全: 解析真实路径，防止符号链接逃逸
    resolved = os.path.realpath(path)
    if not (resolved.startswith("/var/log/") or resolved == "/var/log"):
        raise HTTPException(status_code=403, detail="路径限制在 /var/log 下")

    result = await _safe_exec(
        ["tail", "-n", str(lines), resolved],
        timeout=15,
        label=f"tail {resolved}",
    )
    return {"path": resolved, "content": result["stdout"], "exit_code": result["exit_code"]}


@app.get("/cron/list", dependencies=[Depends(verify_token)])
async def cron_list(user: str = Query(default="", description="用户名，空则为当前用户")):
    """列出 crontab — 无 shell 注入风险"""
    if user:
        _validate_name(user, _RE_USERNAME, "用户名")
        args = ["sudo", "-u", user, "crontab", "-l"]
    else:
        args = ["crontab", "-l"]

    result = await _safe_exec(args, timeout=10, label="crontab -l")
    return {"output": result["stdout"], "exit_code": result["exit_code"]}


@app.get("/network/ports", dependencies=[Depends(verify_token)])
async def network_ports():
    """列出监听端口 — 无 shell 注入风险"""
    result = await _safe_exec(["ss", "-tlnp"], timeout=10, label="ss -tlnp")
    return {"output": result["stdout"], "exit_code": result["exit_code"]}


@app.get("/network/connections", dependencies=[Depends(verify_token)])
async def network_connections():
    """获取网络连接摘要 — 无 shell 注入风险"""
    result = await _safe_exec(["ss", "-s"], timeout=10, label="ss -s")
    return {"output": result["stdout"], "exit_code": result["exit_code"]}


@app.get("/users/sessions", dependencies=[Depends(verify_token)])
async def user_sessions():
    """获取当前活跃登录会话 — 无 shell 注入风险"""
    result = await _safe_exec(["who"], timeout=10, label="who")
    return {"output": result["stdout"], "exit_code": result["exit_code"]}


@app.get("/users/stats", dependencies=[Depends(verify_token)])
async def user_stats():
    """获取用户资源使用统计 — 无 shell 注入风险"""
    result = await _safe_exec(
        [
            "ps",
            "aux",
            "--sort=-%mem",
        ],
        timeout=15,
        label="ps aux",
    )
    # 解析 ps 输出为用户统计
    users: dict[str, dict] = {}
    for line in result["stdout"].strip().splitlines()[1:]:  # 跳过表头
        parts = line.split(None, 10)
        if len(parts) >= 6:
            uname = parts[0]
            mem_pct = float(parts[3]) if parts[3].replace(".", "").isdigit() else 0
            rss = int(parts[5]) if parts[5].isdigit() else 0
            if uname not in users:
                users[uname] = {"username": uname, "mem_percent": 0.0, "rss_kb": 0}
            users[uname]["mem_percent"] += mem_pct
            users[uname]["rss_kb"] += rss
    stats = list(users.values())
    for s in stats:
        s["mem_percent"] = round(s["mem_percent"], 1)
        s["mem_gb"] = round(s["rss_kb"] / 1024 / 1024, 2)
    return {"users": stats}


@app.post("/users/kill", dependencies=[Depends(verify_token)])
async def user_kill(body: KillProcessRequest):
    """终止指定进程 — PID 校验，无 shell 注入风险"""
    if body.pid < 2:
        raise HTTPException(status_code=400, detail="不允许终止 PID < 2 的进程")

    result = await _safe_exec(
        ["kill", "-9", str(body.pid)],
        timeout=10,
        label=f"kill -9 {body.pid}",
    )
    return {"output": result["stdout"] + result["stderr"], "exit_code": result["exit_code"]}


# ---------------------------------------------------------------------------
# 已有的数据采集端点（无 shell 注入风险，使用 psutil/docker SDK）
# ---------------------------------------------------------------------------


@app.get("/docker/containers", dependencies=[Depends(verify_token)])
async def get_docker_containers():
    """列出 Docker 容器"""
    loop = asyncio.get_event_loop()
    containers = await loop.run_in_executor(None, collect_docker_containers)
    return {"containers": containers, "total": len(containers)}


@app.get("/services", dependencies=[Depends(verify_token)])
async def get_services():
    """列出 systemd 服务"""
    loop = asyncio.get_event_loop()
    services = await loop.run_in_executor(None, collect_services)
    return {"services": services, "total": len(services)}


# ---------------------------------------------------------------------------
# 管理端点: 远程文件更新 (仅限 agent 安装目录内的 .py 文件)
# ---------------------------------------------------------------------------


class FileUpdateRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=128, description="目标文件名 (仅 .py)")
    content: str = Field(..., min_length=1, description="文件内容")
    restart: bool = Field(default=False, description="更新后是否自动重启 agent 服务")
    stage_only: bool = Field(default=False, description="仅暂存到 .pending 文件，不替换原文件")


@app.post("/admin/update-file", dependencies=[Depends(verify_token)])
async def admin_update_file(body: FileUpdateRequest):
    """安全地更新 agent 安装目录内的 Python 文件

    安全限制:
    - 仅允许 .py 文件
    - 文件名不能含路径分隔符 (防止路径穿越)
    - 仅写入 agent 安装目录 (__file__ 所在目录)
    """
    if not body.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅允许更新 .py 文件")
    if "/" in body.filename or "\\" in body.filename or ".." in body.filename:
        raise HTTPException(status_code=400, detail="文件名不能包含路径分隔符")

    agent_dir = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(agent_dir, body.filename)
    resolved = os.path.realpath(target)
    if not resolved.startswith(agent_dir):
        raise HTTPException(status_code=400, detail="路径穿越检测")

    try:
        if body.stage_only:
            # 阶段 1: 仅写入 .pending 暂存文件
            pending = target + ".pending"
            with open(pending, "w", encoding="utf-8") as f:
                f.write(body.content)
            logger.info("文件已暂存: %s.pending (%d bytes)", body.filename, len(body.content))
            return {"ok": True, "file": body.filename, "size": len(body.content), "staged": True}

        # 直接更新模式 (向后兼容)
        if os.path.exists(target):
            backup = target + ".bak"
            with open(target, encoding="utf-8") as f:
                old_content = f.read()
            with open(backup, "w", encoding="utf-8") as f:
                f.write(old_content)

        with open(target, "w", encoding="utf-8") as f:
            f.write(body.content)

        logger.info("文件已更新: %s (%d bytes)", body.filename, len(body.content))

        result = {"ok": True, "file": body.filename, "size": len(body.content)}

        if body.restart:

            async def _delayed_restart():
                await asyncio.sleep(1)
                logger.info("Agent 重启中...")
                os.execv(
                    "/usr/bin/sudo",
                    ["sudo", "systemctl", "restart", "serverhub-agent"],
                )

            asyncio.create_task(_delayed_restart())
            result["restarting"] = True

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件写入失败: {e}")


class UpdateCommitRequest(BaseModel):
    action: str = Field(..., pattern="^(commit|rollback)$", description="commit 提交暂存文件 / rollback 清理暂存")


@app.post("/admin/update-commit", dependencies=[Depends(verify_token)])
async def admin_update_commit(body: UpdateCommitRequest):
    """两阶段提交: 将所有 .pending 暂存文件原子替换为正式文件，或回滚清理"""
    agent_dir = os.path.dirname(os.path.abspath(__file__))
    pending_files = [f for f in os.listdir(agent_dir) if f.endswith(".pending")]

    if body.action == "rollback":
        for pf in pending_files:
            os.remove(os.path.join(agent_dir, pf))
        logger.info("回滚: 已清理 %d 个暂存文件", len(pending_files))
        return {"ok": True, "action": "rollback", "cleaned": len(pending_files)}

    # action == "commit"
    if not pending_files:
        return {"ok": True, "action": "commit", "committed": 0, "message": "无暂存文件"}

    committed = []
    try:
        for pf in pending_files:
            target_name = pf.removesuffix(".pending")
            target = os.path.join(agent_dir, target_name)
            pending = os.path.join(agent_dir, pf)

            # 备份原文件
            if os.path.exists(target):
                with open(target, encoding="utf-8") as f:
                    old_content = f.read()
                with open(target + ".bak", "w", encoding="utf-8") as f:
                    f.write(old_content)

            os.replace(pending, target)
            committed.append(target_name)

        logger.info("提交: 已替换 %d 个文件: %s", len(committed), ", ".join(committed))

        # 提交成功后延迟重启
        async def _delayed_restart():
            await asyncio.sleep(1)
            logger.info("Agent 重启中...")
            os.execv("/usr/bin/sudo", ["sudo", "systemctl", "restart", "serverhub-agent"])

        asyncio.create_task(_delayed_restart())
        return {"ok": True, "action": "commit", "committed": len(committed), "files": committed, "restarting": True}
    except Exception as e:
        # 提交过程失败，用 .bak 回滚已替换的文件
        for name in committed:
            bak = os.path.join(agent_dir, name + ".bak")
            if os.path.exists(bak):
                os.replace(bak, os.path.join(agent_dir, name))
        # 清理剩余 .pending
        for pf in pending_files:
            p = os.path.join(agent_dir, pf)
            if os.path.exists(p):
                os.remove(p)
        raise HTTPException(status_code=500, detail=f"提交失败并已回滚: {e}")


# ---------------------------------------------------------------------------
# 异常处理
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("未处理异常: %s %s — %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {type(exc).__name__}"},
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=AGENT_PORT,
        workers=1,
        log_level="info",
        access_log=False,
    )

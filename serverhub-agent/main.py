"""
ServerHub Agent — 轻量级服务器监控代理

部署在被管服务器上，提供系统指标采集、命令执行、Docker/服务状态查询。
Hub 端通过 HTTP + Bearer Token 与本 agent 通信。
"""

import asyncio
import logging
import platform
import subprocess
import time
from contextlib import asynccontextmanager

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from collectors import (
    collect_all,
    collect_docker_containers,
    collect_fast,
    collect_services,
)
from config import AGENT_PORT, AGENT_TOKEN

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
# 请求/响应模型
# ---------------------------------------------------------------------------

class ExecuteRequest(BaseModel):
    command: str = Field(..., min_length=1, max_length=4096, description="要执行的 shell 命令")
    timeout: int = Field(default=30, ge=1, le=300, description="超时秒数")


class ExecuteResponse(BaseModel):
    stdout: str
    stderr: str
    exit_code: int


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


@app.post("/execute", dependencies=[Depends(verify_token)], response_model=ExecuteResponse)
async def execute_command(req: ExecuteRequest):
    """在远程服务器上执行命令"""
    # 安全：拒绝一些极端危险的命令模式
    dangerous = ["rm -rf /", "mkfs", "dd if=", "> /dev/sd", ":(){ :|:& };:"]
    cmd_lower = req.command.lower().strip()
    for pattern in dangerous:
        if pattern in cmd_lower:
            raise HTTPException(status_code=400, detail=f"命令被安全策略拒绝: 包含危险模式 '{pattern}'")

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
    except asyncio.TimeoutError:
        # 超时后尝试杀死进程
        try:
            proc.kill()
            await proc.communicate()
        except Exception:
            pass
        raise HTTPException(status_code=408, detail=f"命令执行超时 ({req.timeout}s)")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"命令执行失败: {str(e)}")


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

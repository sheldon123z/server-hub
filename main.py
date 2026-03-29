"""
ServerHub — NF5468M6 服务器管理系统
FastAPI + React 18 + SQLite
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from config import settings
from database import get_db, close_db
from auth.dependencies import get_current_user
from auth.routes import router as auth_router
from auth.user_store import ensure_admin
from modules import discover_modules, get_sidebar_items
from modules.audit.middleware import AuditMiddleware


# ─── 子系统状态跟踪 ───

_start_time: float = 0.0
_subsystem_status: dict[str, str] = {}
_bg_init_task: asyncio.Task | None = None


# ─── 生命周期 ───

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _start_time, _bg_init_task
    _start_time = time.time()

    # ── 关键路径（必须在服务 ready 前完成） ──
    await get_db()
    await ensure_admin()
    modules = discover_modules()
    for m in modules:
        app.include_router(m["router"])
    logger.info("[ServerHub] 已加载 %s 个模块", len(modules))

    # LG Compat router 也需要在 ready 前挂载（路由注册不能延迟）
    try:
        from modules.agents.lg_compat import lg_router
        app.include_router(lg_router)
    except Exception as e:
        logger.warning("[ServerHub] LG Compat 路由注册失败: %s", e)

    # ── 非阻塞后台初始化（并发 + per-task 超时） ──
    async def _init_background():
        """后台初始化 — 并发执行，单个子系统超时不拖后续"""
        task_defs: list[tuple[str, object]] = [
            ("通知渠道", _init_notifications()),
            ("指标采集", _init_monitoring()),
            ("RAG 知识库", _init_rag()),
            ("异步任务清理", _init_stale_cleanup()),
            ("LG Compat graphs", _init_lg_compat()),
            ("AI 巡检调度", _init_patrol()),
            ("运维剧本", _init_playbooks()),
            ("心跳监控", _init_heartbeat()),
            ("远程指标采集", _init_remote_scheduler()),
            ("智能体团队", _init_agent_teams()),
        ]
        for name, _ in task_defs:
            _subsystem_status[name] = "starting"

        async def _run_one(name: str, coro):
            try:
                await asyncio.wait_for(coro, timeout=30)
                _subsystem_status[name] = "ready"
                logger.info("[ServerHub] %s 已启动", name)
            except asyncio.TimeoutError:
                _subsystem_status[name] = "timeout"
                logger.warning("[ServerHub] %s 启动超时(30s)", name)
            except Exception as e:
                _subsystem_status[name] = "failed"
                logger.warning("[ServerHub] %s 启动失败 (非致命): %s", name, e)

        await asyncio.gather(*(_run_one(n, c) for n, c in task_defs))

    _bg_init_task = asyncio.create_task(_init_background())

    yield

    # ── 关闭 ──
    if _bg_init_task and not _bg_init_task.done():
        _bg_init_task.cancel()

    for stop_fn_path in [
        "modules.servers.heartbeat:stop_heartbeat",
        "modules.monitoring.scheduler:stop_remote_scheduler",
        "modules.playbooks.scheduler:stop_playbook_scheduler",
        "modules.agents.lg_compat:stop_cleanup",
        "modules.agents.patrol:stop_patrol_scheduler",
        "modules.monitoring.scheduler:stop_scheduler",
    ]:
        try:
            mod_path, fn_name = stop_fn_path.rsplit(":", 1)
            import importlib
            mod = importlib.import_module(mod_path)
            await getattr(mod, fn_name)()
        except Exception:
            pass
    await close_db()


# ─── 后台初始化协程 ───

async def _init_notifications():
    from modules.notifications.services import ensure_default_channels
    await ensure_default_channels()


async def _init_monitoring():
    from modules.monitoring.scheduler import start_scheduler
    await start_scheduler()


async def _init_rag():
    from modules.agents.rag import build_full_index
    stats = await asyncio.get_event_loop().run_in_executor(None, build_full_index)
    logger.info("[ServerHub] RAG 知识库已构建: %s", stats)


async def _init_stale_cleanup():
    from modules.agents.async_tasks import cleanup_stale_tasks
    await cleanup_stale_tasks()


async def _init_lg_compat():
    from modules.agents.lg_compat import register_graph, start_cleanup
    from modules.agents.async_graphs import build_all_async_graphs
    graphs = await build_all_async_graphs()
    for gid, graph in graphs.items():
        register_graph(gid, graph)
    await start_cleanup()
    logger.info("[ServerHub] LG Compat Server: %d 个异步 graph 已注册", len(graphs))


async def _init_patrol():
    from modules.agents.patrol import start_patrol_scheduler
    await start_patrol_scheduler()


async def _init_playbooks():
    from modules.playbooks.seed import seed_builtin_playbooks
    await seed_builtin_playbooks()
    from modules.playbooks.scheduler import start_playbook_scheduler
    await start_playbook_scheduler()


async def _init_heartbeat():
    from modules.servers.heartbeat import start_heartbeat
    await start_heartbeat()


async def _init_agent_teams():
    from modules.agents.teams.templates import seed_builtin_teams
    await seed_builtin_teams()


async def _init_remote_scheduler():
    from modules.monitoring.scheduler import start_remote_scheduler
    await start_remote_scheduler()


app = FastAPI(title="ServerHub", lifespan=lifespan)

# 服务 agent 安装文件（供远程 curl 下载）
AGENT_DIR = Path(__file__).parent / "serverhub-agent"
if AGENT_DIR.exists():
    app.mount("/static/agent", StaticFiles(directory=str(AGENT_DIR)), name="agent-files")

# 认证路由
app.include_router(auth_router)

# WebSocket 路由（不走模块自发现，因为 ws_router 无 prefix 需直接挂载）
from modules.monitoring.routes import ws_router
app.include_router(ws_router)


# ─── 审计中间件 ───

app.add_middleware(AuditMiddleware)


# ─── HTTP 安全头中间件 ───

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


# ─── React 前端 sidebar API ───

@app.get("/api/sidebar")
async def sidebar_api(request: Request, user=Depends(get_current_user)):
    return get_sidebar_items(user["role"])


# ─── 健康检查（无需认证） ───

@app.get("/api/health")
async def health_check():
    """子系统状态和服务 uptime"""
    return {
        "status": "ok",
        "subsystems": dict(_subsystem_status),
        "uptime": round(time.time() - _start_time, 1) if _start_time else 0,
    }


# ─── React SPA 前端服务 ───

FRONTEND_DIR = Path(__file__).parent / "frontend" / "dist"

# 开发模式 CORS（Vite dev server 在不同端口时使用）
if os.getenv("SERVERHUB_DEV"):
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

if FRONTEND_DIR.exists():
    # React 构建产物的静态资源（JS/CSS/图片）
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR / "assets")), name="frontend-assets")

    _favicon_path = FRONTEND_DIR / "favicon.svg"
    _index_html = (FRONTEND_DIR / "index.html").read_text()

    @app.get("/favicon.svg")
    async def frontend_favicon():
        if _favicon_path.exists():
            return FileResponse(str(_favicon_path), media_type="image/svg+xml")
        raise HTTPException(status_code=404)

    # SPA catch-all: 所有非 API/非 WS 路径都返回 React index.html
    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def spa_fallback(full_path: str):
        return HTMLResponse(_index_html)
else:
    logger.warning(
        "[ServerHub] frontend/dist/ 不存在。请运行 cd frontend && npm run build 构建前端。"
        "当前只能通过 API 端点访问。"
    )


# ─── 旧 Jinja2 页面路由已移除，前端统一由 React SPA 提供 ───
# 旧模板文件已归档到 archive/templates_legacy/



# ─── 入口 ───

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9900, reload=True, workers=1)

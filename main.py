"""
ServerHub — NF5468M6 服务器管理系统
FastAPI + React 18 + SQLite
"""

import os
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


# ─── 生命周期 ───

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    await get_db()
    await ensure_admin()
    modules = discover_modules()
    for m in modules:
        app.include_router(m["router"])
    logger.info("[ServerHub] 已加载 %s 个模块", len(modules))

    # 确保默认通知渠道存在
    try:
        from modules.notifications.services import ensure_default_channels
        await ensure_default_channels()
    except Exception as e:
        logger.exception("[ServerHub] 默认通知渠道初始化失败: %s", e)

    # 启动后台指标采集
    try:
        from modules.monitoring.scheduler import start_scheduler
        await start_scheduler()
        logger.info("[ServerHub] 指标采集已启动")
    except Exception as e:
        logger.exception("[ServerHub] 指标采集启动失败: %s", e)

    # 启动 RAG 知识库索引
    try:
        from modules.agents.rag import build_full_index
        import asyncio as _aio
        stats = await _aio.get_event_loop().run_in_executor(None, build_full_index)
        logger.info("[ServerHub] RAG 知识库已构建: %s", stats)
    except Exception as e:
        logger.warning("[ServerHub] RAG 知识库构建失败 (非致命): %s", e)

    # 清理残留的异步任务
    try:
        from modules.agents.async_tasks import cleanup_stale_tasks
        await cleanup_stale_tasks()
    except Exception as e:
        logger.warning("[ServerHub] 异步任务清理失败: %s", e)

    # 初始化 LG Compat Server — 异步 SubAgent 后端
    try:
        from modules.agents.lg_compat import lg_router, register_graph, start_cleanup
        from modules.agents.async_graphs import build_all_async_graphs

        app.include_router(lg_router)
        graphs = await build_all_async_graphs()
        for gid, graph in graphs.items():
            register_graph(gid, graph)
        await start_cleanup()
        logger.info("[ServerHub] LG Compat Server: %d 个异步 graph 已注册", len(graphs))
    except Exception as e:
        logger.warning("[ServerHub] LG Compat Server 初始化失败 (非致命): %s", e)

    # 启动 AI 巡检调度器
    try:
        from modules.agents.patrol import start_patrol_scheduler
        await start_patrol_scheduler()
        logger.info("[ServerHub] AI 巡检调度器已启动")
    except Exception as e:
        logger.exception("[ServerHub] AI 巡检调度器启动失败: %s", e)

    # 初始化运维剧本系统
    try:
        from modules.playbooks.seed import seed_builtin_playbooks
        await seed_builtin_playbooks()
        from modules.playbooks.scheduler import start_playbook_scheduler
        await start_playbook_scheduler()
        logger.info("[ServerHub] 运维剧本系统已启动")
    except Exception as e:
        logger.warning("[ServerHub] 运维剧本系统启动失败 (非致命): %s", e)

    yield

    # 关闭
    try:
        from modules.playbooks.scheduler import stop_playbook_scheduler
        await stop_playbook_scheduler()
    except Exception:
        pass
    try:
        from modules.agents.lg_compat import stop_cleanup
        await stop_cleanup()
    except Exception:
        pass
    try:
        from modules.agents.patrol import stop_patrol_scheduler
        await stop_patrol_scheduler()
    except Exception:
        pass
    try:
        from modules.monitoring.scheduler import stop_scheduler
        await stop_scheduler()
    except Exception:
        pass
    await close_db()


app = FastAPI(title="ServerHub", lifespan=lifespan)

# 认证路由
app.include_router(auth_router)

# WebSocket 路由（不走模块自发现，因为 ws_router 无 prefix 需直接挂载）
from modules.monitoring.routes import ws_router
app.include_router(ws_router)


# ─── 审计中间件 ───

app.add_middleware(AuditMiddleware)


# ─── React 前端 sidebar API ───

@app.get("/api/sidebar")
async def sidebar_api(request: Request, user=Depends(get_current_user)):
    return get_sidebar_items(user["role"])


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

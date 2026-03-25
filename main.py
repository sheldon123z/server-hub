"""
ServerHub — NF5468M6 服务器管理系统
FastAPI + Jinja2/HTMX + SQLite
"""

from contextlib import asynccontextmanager
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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

    yield

    # 关闭
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

# 静态文件
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# 模板
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# 认证路由
app.include_router(auth_router)

# WebSocket 路由（不走模块自发现，因为 ws_router 无 prefix 需直接挂载）
from modules.monitoring.routes import ws_router
app.include_router(ws_router)


# ─── 审计中间件 ───

app.add_middleware(AuditMiddleware)


# ─── 页面路由辅助 ───

async def _get_user_or_redirect(request: Request):
    """获取当前用户，未登录则返回 None"""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


def _page_context(request: Request, user: dict, active_module: str, **extra):
    """构建模板渲染上下文"""
    sidebar = get_sidebar_items(user["role"])
    # 查找模块显示名（供对话气泡组件显示）
    display_name = active_module
    for item in sidebar:
        if item["name"] == active_module:
            display_name = item["display_name"]
            break
    return {
        "request": request,
        "user": user,
        "active_module": active_module,
        "active_module_display": display_name,
        "sidebar_items": sidebar,
        **extra,
    }


# ─── 登录页 ───

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


# ─── 仪表盘 ───

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("dashboard.html", _page_context(request, user, "dashboard"))


# ─── 仪表盘局部刷新 ───

@app.get("/partials/dashboard/cards", response_class=HTMLResponse)
async def dashboard_cards_partial(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return HTMLResponse("", status_code=401)
    from modules.dashboard.collectors import get_system_info
    sys_info = get_system_info()
    return templates.TemplateResponse("partials/_metrics_cards.html", {"request": request, "sys": sys_info})


@app.get("/partials/dashboard/docker-brief", response_class=HTMLResponse)
async def dashboard_docker_brief(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return HTMLResponse("", status_code=401)
    html = ""
    try:
        from modules.docker.services import list_containers
        containers = await list_containers()
        for c in containers[:8]:
            name = c.get("Names") or c.get("name", "")
            status = c.get("Status") or c.get("status", "")
            if "Up" in status:
                badge = '<span class="badge badge-ok">运行中</span>'
            elif "Restarting" in status:
                badge = '<span class="badge badge-crit">重启中</span>'
            else:
                badge = '<span class="badge badge-idle">已停止</span>'
            html += f"<tr><td>{name}</td><td>{badge}</td></tr>"
    except Exception:
        pass
    return HTMLResponse(html or '<tr><td colspan="2" class="text-muted text-center">无数据</td></tr>')


@app.get("/partials/dashboard/users-brief", response_class=HTMLResponse)
async def dashboard_users_brief(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return HTMLResponse("", status_code=401)
    html = ""
    try:
        from modules.users.services import get_user_stats
        users = get_user_stats()
        for u in users[:6]:
            html += f'<tr><td><strong>{u["name"]}</strong></td><td>{u["mem_gb"]} GB</td><td>{u["proc_count"]}</td></tr>'
    except Exception:
        pass
    return HTMLResponse(html or '<tr><td colspan="3" class="text-muted text-center">无数据</td></tr>')


# ─── 监控页面 ───

@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)


# ─── 用户管理页面 ───

@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    from modules.users.services import get_user_stats, read_quotas, get_user_quota
    users = get_user_stats()
    quotas = read_quotas()
    ctx = _page_context(request, user, "users",
                        users=users, quotas=quotas, get_user_quota=get_user_quota)
    return templates.TemplateResponse("users.html", ctx)


# ─── Docker 管理页面 ───

@app.get("/docker", response_class=HTMLResponse)
async def docker_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)

    containers, images, stacks = [], [], []
    try:
        from modules.docker.services import list_containers, list_images, list_compose_stacks
        containers = await list_containers()
        images = await list_images()
        stacks = await list_compose_stacks()
    except Exception as e:
        logger.exception("[Docker] 加载失败: %s", e)

    ctx = _page_context(request, user, "docker",
                        containers=containers, images=images, stacks=stacks)
    return templates.TemplateResponse("docker.html", ctx)


# ─── 服务管理页面 ───

@app.get("/services", response_class=HTMLResponse)
async def services_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    services = []
    try:
        from modules.services.services import list_services
        services = await list_services()
    except Exception as e:
        logger.exception("[Services] 加载失败: %s", e)
    ctx = _page_context(request, user, "services", services=services)
    return templates.TemplateResponse("services.html", ctx)


# ─── Cron 页面 ───

@app.get("/cron", response_class=HTMLResponse)
async def cron_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    user_jobs, root_jobs = [], []
    try:
        from modules.cron.services import get_user_crontab, get_root_crontab
        user_jobs = await get_user_crontab()
        if user["role"] == "admin":
            root_jobs = await get_root_crontab()
    except Exception as e:
        logger.exception("[Cron] 加载失败: %s", e)
    ctx = _page_context(request, user, "cron", user_jobs=user_jobs, root_jobs=root_jobs)
    return templates.TemplateResponse("cron.html", ctx)


# ─── 网络管理页面 ───

@app.get("/network", response_class=HTMLResponse)
async def network_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)

    ports, proxy, connections = [], {}, ""
    try:
        from modules.network.services import get_listening_ports, get_proxy_status, get_connections_summary
        ports = await get_listening_ports()
        proxy = await get_proxy_status()
        connections = await get_connections_summary()
    except Exception as e:
        logger.exception("[Network] 加载失败: %s", e)

    ctx = _page_context(request, user, "network", ports=ports, proxy=proxy, connections=connections)
    return templates.TemplateResponse("network.html", ctx)


# ─── 代理管理页面 ───

@app.get("/proxy", response_class=HTMLResponse)
async def proxy_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)
    proxy_instances = []
    default_proxy_instance_id = None
    try:
        from modules.proxy.services import list_proxy_instances
        payload = await list_proxy_instances()
        proxy_instances = payload.get("instances", [])
        default_proxy_instance_id = payload.get("default_instance_id")
    except Exception as e:
        logger.exception("[Proxy] 加载失败: %s", e)
    ctx = _page_context(
        request,
        user,
        "proxy",
        proxy_instances=proxy_instances,
        default_proxy_instance_id=default_proxy_instance_id,
    )
    return templates.TemplateResponse("proxy.html", ctx)


# ─── 日志查看页面 ───

@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)
    files = []
    try:
        from modules.logs.services import list_log_files
        files = list_log_files()
    except Exception as e:
        logger.exception("[Logs] 加载失败: %s", e)
    ctx = _page_context(request, user, "logs", files=files)
    return templates.TemplateResponse("logs.html", ctx)


# ─── 通知管理页面 ───

@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)
    channels, history = [], []
    try:
        from modules.notifications.services import get_channels, get_notification_history
        channels = await get_channels()
        history = await get_notification_history()
    except Exception as e:
        logger.exception("[Notifications] 加载失败: %s", e)
    ctx = _page_context(request, user, "notifications", history=history, channels=channels)
    return templates.TemplateResponse("notifications.html", ctx)


# ─── 审计日志页面 ───

@app.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request, page: int = 1, limit: int = 50, username: str = ""):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)
    logs, total = [], 0
    try:
        from modules.audit.routes import _get_audit_logs
        result = await _get_audit_logs(page, limit, username)
        logs = result["items"]
        total = result["total"]
    except Exception as e:
        logger.exception("[Audit] 加载失败: %s", e)
    ctx = _page_context(request, user, "audit",
                        logs=logs, total=total, page=page, limit=limit)
    return templates.TemplateResponse("audit.html", ctx)


# ─── 面板用户管理页面 ───

@app.get("/panel_users", response_class=HTMLResponse)
async def panel_users_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)
    from auth.user_store import list_users
    panel_users = await list_users()
    ctx = _page_context(request, user, "panel_users", panel_users=panel_users)
    return templates.TemplateResponse("panel_users.html", ctx)


# ─── 系统设置页面 ───

@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)
    config = {
        "metrics_interval_seconds": settings.metrics_interval_seconds,
        "metrics_retention_days": settings.metrics_retention_days,
        "managed_services": settings.managed_services,
        "compose_stacks": settings.compose_stacks,
        "log_dirs": settings.log_dirs,
    }
    ctx = _page_context(request, user, "settings", config=config)
    return templates.TemplateResponse("settings.html", ctx)


# ─── OpsAgent 页面 ───

@app.get("/assets", response_class=HTMLResponse)
async def assets_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    if user["role"] != "admin":
        return RedirectResponse("/", status_code=302)
    ctx = _page_context(request, user, "assets")
    return templates.TemplateResponse("assets.html", ctx)


@app.get("/agents", response_class=HTMLResponse)
async def agents_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    ctx = _page_context(request, user, "agents")
    return templates.TemplateResponse("agents.html", ctx)


# ─── 入口 ───

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=9900, reload=True, workers=1)

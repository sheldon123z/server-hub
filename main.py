"""
ServerHub — NF5468M6 服务器管理系统
FastAPI + Jinja2/HTMX + SQLite
"""

import logging
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from database import get_db, close_db
from auth.user_store import ensure_admin
from auth.dependencies import get_current_user
from auth.routes import router as auth_router
from modules import discover_modules, get_sidebar_items


# ─── 生命周期 ───

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    await get_db()
    await ensure_admin()
    modules = discover_modules()
    for m in modules:
        app.include_router(m["router"])
    print(f"[ServerHub] 已加载 {len(modules)} 个模块")

    # 启动后台指标采集
    try:
        from modules.monitoring.scheduler import start_scheduler
        await start_scheduler()
        print("[ServerHub] 指标采集已启动")
    except Exception as e:
        print(f"[ServerHub] 指标采集启动失败: {e}")

    # 启动 AI 巡检调度器
    try:
        from modules.agents.patrol import start_patrol_scheduler
        await start_patrol_scheduler()
        print("[ServerHub] AI 巡检调度器已启动")
    except Exception as e:
        print(f"[ServerHub] AI 巡检调度器启动失败: {e}")

    yield

    # 关闭
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

from starlette.middleware.base import BaseHTTPMiddleware

class AuditMiddlewareWrapper(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.method in ("POST", "PUT", "DELETE") and "/api/" in str(request.url.path):
            try:
                from modules.audit.middleware import log_audit
                user = None
                try:
                    from auth.jwt_handler import verify_token
                    token = request.cookies.get("access_token")
                    if token:
                        payload = verify_token(token)
                        if payload:
                            user = payload.get("sub", "unknown")
                except Exception:
                    user = "unknown"
                await log_audit(
                    username=user or "unknown",
                    action=f"{request.method} {request.url.path}",
                    target=str(request.url.path),
                    details="",
                    ip=request.client.host if request.client else "unknown",
                    success=response.status_code < 400,
                )
            except Exception as e:
                logger.error(f"审计日志写入失败: {e}")
        return response

app.add_middleware(AuditMiddlewareWrapper)


# ─── 页面路由辅助 ───

async def _get_user_or_redirect(request: Request):
    """获取当前用户，未登录则返回 None"""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


def _page_context(request: Request, user: dict, active_module: str, **extra):
    """构建模板渲染上下文"""
    return {
        "request": request,
        "user": user,
        "active_module": active_module,
        "sidebar_items": get_sidebar_items(user["role"]),
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

    from modules.dashboard.collectors import get_system_info, get_extra_disks
    from modules.users.services import get_user_stats as _get_users
    sys_info = get_system_info()

    # Docker 容器简要
    docker_containers = []
    try:
        from modules.docker.services import list_containers
        docker_containers = await list_containers()
    except Exception:
        pass

    # 用户简要
    users = []
    try:
        users = _get_users()
    except Exception:
        pass

    ctx = _page_context(request, user, "dashboard",
                        sys=sys_info, docker_containers=docker_containers, users=users)
    return templates.TemplateResponse("dashboard.html", ctx)


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
# 注意: 此路由保留独立的 /monitoring 页面。如需合并到仪表盘，可改为 RedirectResponse("/dashboard")

@app.get("/monitoring", response_class=HTMLResponse)
async def monitoring_page(request: Request):
    user = await _get_user_or_redirect(request)
    if not user:
        return RedirectResponse("/login", status_code=302)
    from modules.dashboard.collectors import get_system_info, get_extra_disks
    sys_info = get_system_info()
    extra_disks = get_extra_disks()
    ctx = _page_context(request, user, "monitoring", sys=sys_info, extra_disks=extra_disks)
    return templates.TemplateResponse("monitoring.html", ctx)


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
        print(f"[Docker] 加载失败: {e}")

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
        print(f"[Services] 加载失败: {e}")
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
        print(f"[Cron] 加载失败: {e}")
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
        print(f"[Network] 加载失败: {e}")

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
    status = {}
    try:
        from modules.proxy.services import get_clash_status
        status = await get_clash_status()
    except Exception as e:
        print(f"[Proxy] 加载失败: {e}")
        status = {"running": False, "version": "", "premium": False, "current_config": "unknown", "current_config_name": "未知", "configs": {}}
    ctx = _page_context(request, user, "proxy", status=status)
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
        print(f"[Logs] 加载失败: {e}")
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
    history = []
    try:
        from modules.notifications.services import get_notification_history
        history = await get_notification_history()
    except Exception as e:
        print(f"[Notifications] 加载失败: {e}")
    ctx = _page_context(request, user, "notifications", history=history)
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
        print(f"[Audit] 加载失败: {e}")
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


# ─── AI 助手页面 ───

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

"""仪表盘路由"""

from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from auth.dependencies import get_current_user
from modules.dashboard.collectors import get_system_info, get_extra_disks

router = APIRouter(tags=["仪表盘"])


@router.get("/api/dashboard/overview")
async def dashboard_overview(user=Depends(get_current_user)):
    info = get_system_info()
    info["extra_disks"] = get_extra_disks()
    return info

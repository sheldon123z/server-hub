"""仪表盘兼容 API。"""

import asyncio

from fastapi import APIRouter, Depends

from auth.dependencies import get_current_user
from modules.monitoring.collectors import collect_all

router = APIRouter(tags=["仪表盘"])


@router.get("/api/dashboard/overview")
async def dashboard_overview(user=Depends(get_current_user)):
    return await asyncio.to_thread(collect_all)

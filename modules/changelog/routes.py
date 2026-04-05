"""变更日历 API 路由"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import get_current_user, require_role
from modules.changelog.models import ChangeEventCreate, FreezeWindowCreate
from modules.changelog.services import (
    create_event,
    create_freeze_window,
    delete_event,
    delete_freeze_window,
    get_event,
    get_stats,
    is_frozen_now,
    list_events,
    list_freeze_windows,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/changelog", tags=["变更日历"])


# ---------------------------------------------------------------------------
# 变更事件
# ---------------------------------------------------------------------------


@router.get("/events")
@router.get("/events/")
async def query_events(
    start: str | None = Query(default=None, description="起始时间 ISO 格式"),
    end: str | None = Query(default=None, description="结束时间 ISO 格式"),
    event_type: str | None = Query(default=None, description="事件类型筛选"),
    operator: str | None = Query(default=None, description="操作人筛选"),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_current_user),
):
    """查询变更事件列表"""
    return await list_events(
        start=start,
        end=end,
        event_type=event_type,
        operator=operator,
        limit=limit,
        offset=offset,
    )


@router.post("/events")
@router.post("/events/")
async def add_event(
    body: ChangeEventCreate,
    user=Depends(require_role("admin")),
):
    """创建变更记录"""
    event = await create_event(body.model_dump(), operator=user.get("username"))
    return {"ok": True, "event": event}


@router.get("/events/{event_id}")
async def get_single_event(
    event_id: int,
    user=Depends(get_current_user),
):
    """获取单条变更记录"""
    event = await get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="变更记录不存在")
    return event


@router.delete("/events/{event_id}")
async def remove_event(
    event_id: int,
    user=Depends(require_role("admin")),
):
    """删除变更记录"""
    ok = await delete_event(event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="变更记录不存在")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 冻结窗口
# ---------------------------------------------------------------------------


@router.get("/freeze-windows")
@router.get("/freeze-windows/")
async def query_freeze_windows(
    active_only: bool = Query(default=False, description="仅返回当前生效的冻结窗口"),
    user=Depends(get_current_user),
):
    """查询冻结窗口列表"""
    windows = await list_freeze_windows(active_only=active_only)
    return {"items": windows, "total": len(windows)}


@router.post("/freeze-windows")
@router.post("/freeze-windows/")
async def add_freeze_window(
    body: FreezeWindowCreate,
    user=Depends(require_role("admin")),
):
    """创建冻结窗口"""
    if body.end_time <= body.start_time:
        raise HTTPException(status_code=400, detail="结束时间必须晚于开始时间")
    window = await create_freeze_window(body.model_dump(), created_by=user.get("username"))
    return {"ok": True, "window": window}


@router.delete("/freeze-windows/{window_id}")
async def remove_freeze_window(
    window_id: int,
    user=Depends(require_role("admin")),
):
    """删除冻结窗口"""
    ok = await delete_freeze_window(window_id)
    if not ok:
        raise HTTPException(status_code=404, detail="冻结窗口不存在")
    return {"ok": True}


@router.get("/freeze-windows/active")
async def check_frozen(
    user=Depends(get_current_user),
):
    """检查当前是否处于冻结窗口"""
    window = await is_frozen_now()
    return {"frozen": window is not None, "window": window}


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


@router.get("/stats")
@router.get("/stats/")
async def query_stats(
    start: str | None = Query(default=None, description="起始时间 ISO 格式"),
    end: str | None = Query(default=None, description="结束时间 ISO 格式"),
    user=Depends(get_current_user),
):
    """变更统计 — 按天/按类型/按风险等级聚合"""
    return await get_stats(start=start, end=end)

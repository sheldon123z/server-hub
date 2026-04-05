"""Notification management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth.dependencies import get_current_user, require_role
from modules.notifications.channels import CHANNEL_TYPES
from modules.notifications.services import (
    create_channel,
    delete_channel,
    get_channels,
    get_notification_history,
    get_unread_count,
    list_inapp_notifications,
    mark_all_read,
    mark_read,
    send_notification,
    test_channel,
    update_channel,
)

router = APIRouter(prefix="/api/notifications", tags=["通知管理"])


# ---------------------------------------------------------------------------
# 站内通知 (inapp)
# ---------------------------------------------------------------------------


@router.get("")
@router.get("/")
async def list_inapp(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user),
):
    """站内通知列表（分页，支持 unread_only）"""
    return await list_inapp_notifications(
        user_id=user.username,
        unread_only=unread_only,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count")
async def unread_count(user=Depends(get_current_user)):
    """未读通知数（TopBar badge 用）"""
    count = await get_unread_count(user_id=user.username)
    return {"count": count}


@router.put("/read-all")
async def read_all(user=Depends(get_current_user)):
    """全部标记已读"""
    updated = await mark_all_read(user_id=user.username)
    return {"ok": True, "updated": updated}


@router.put("/{notification_id}/read")
async def read_one(notification_id: int, user=Depends(get_current_user)):
    """标记单条已读"""
    ok = await mark_read(notification_id, user_id=user.username)
    if not ok:
        raise HTTPException(404, "通知不存在")
    return {"ok": True}


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096, description="消息内容")


class ChannelCreate(BaseModel):
    channel_type: str = Field(..., description="渠道类型")
    display_name: str = Field(..., min_length=1, max_length=100)
    config: dict = Field(default_factory=dict, description="渠道配置")
    enabled: bool = True


class ChannelUpdate(BaseModel):
    display_name: str | None = None
    config: dict | None = None
    enabled: bool | None = None
    priority: int | None = None


# --- 渠道类型 ---


@router.get("/channel-types")
async def list_channel_types(user=Depends(require_role("admin"))):
    """返回可用渠道类型和配置 schema"""
    result = {}
    for type_id, cls in CHANNEL_TYPES.items():
        result[type_id] = {
            "display_name": cls.display_name_template,
            "config_schema": cls.config_schema(),
        }
    return result


# --- 渠道 CRUD ---


@router.get("/channels")
async def list_channels(user=Depends(require_role("admin"))):
    """列出所有通知渠道"""
    channels = await get_channels()
    return {"channels": channels}


@router.post("/channels", status_code=201)
async def create_channel_endpoint(body: ChannelCreate, user=Depends(require_role("admin"))):
    """创建通知渠道"""
    try:
        channel = await create_channel(body.channel_type, body.display_name, body.config, body.enabled)
        return channel
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/channels/{channel_id}")
async def update_channel_endpoint(channel_id: str, body: ChannelUpdate, user=Depends(require_role("admin"))):
    """更新渠道配置"""
    kwargs = body.model_dump(exclude_none=True)
    if not kwargs:
        raise HTTPException(400, "没有要更新的字段")
    result = await update_channel(channel_id, **kwargs)
    if not result:
        raise HTTPException(404, "渠道不存在")
    return result


@router.delete("/channels/{channel_id}")
async def delete_channel_endpoint(channel_id: str, user=Depends(require_role("admin"))):
    """删除通知渠道"""
    ok = await delete_channel(channel_id)
    if not ok:
        raise HTTPException(404, "渠道不存在")
    return {"ok": True}


@router.post("/channels/{channel_id}/test")
async def test_channel_endpoint(channel_id: str, user=Depends(require_role("admin"))):
    """测试渠道连通性"""
    result = await test_channel(channel_id)
    return result


# --- 发送与历史 ---


@router.post("/send")
async def send_notification_endpoint(
    body: SendMessageRequest,
    user=Depends(require_role("admin")),
):
    """广播消息到所有启用的通知渠道"""
    results = await send_notification(body.message)
    success_count = sum(1 for r in results if r.get("success"))
    total = len(results)
    return {
        "results": results,
        "summary": f"{success_count}/{total} 个渠道发送成功",
        "all_success": success_count == total,
    }


@router.post("/test")
async def send_test_notification(user=Depends(require_role("admin"))):
    """广播测试通知到所有启用渠道"""
    results = await send_notification("ServerHub 测试通知")
    success_count = sum(1 for r in results if r.get("success"))
    return {
        "results": results,
        "summary": f"{success_count}/{len(results)} 个渠道发送成功",
        "all_success": success_count == len(results),
    }


@router.get("/history")
async def notification_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
    channel_id: str | None = Query(None),
    user=Depends(require_role("admin")),
):
    """查询通知发送历史，支持按渠道筛选"""
    records = await get_notification_history(limit, channel_id)
    return {"notifications": records, "count": len(records)}

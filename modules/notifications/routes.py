"""Notification management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth.dependencies import require_role
from modules.notifications.services import send_telegram, get_notification_history

router = APIRouter(prefix="/api/notifications", tags=["通知管理"])


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4096, description="消息内容")


@router.post("/send")
async def send_notification(
    body: SendMessageRequest,
    user=Depends(require_role("admin")),
):
    """Send a Telegram notification message."""
    try:
        result = await send_telegram(body.message)
        if not result["success"]:
            raise HTTPException(
                status_code=502,
                detail=f"Telegram send failed: {result.get('error', 'unknown error')}",
            )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def send_test_notification(user=Depends(require_role("admin"))):
    """Send a test notification to verify Telegram integration."""
    try:
        result = await send_telegram("ServerHub 测试通知")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def notification_history(
    limit: int = Query(50, ge=1, le=500, description="返回条数"),
    user=Depends(require_role("admin")),
):
    """Get notification send history."""
    try:
        records = await get_notification_history(limit)
        return {"notifications": records, "count": len(records)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

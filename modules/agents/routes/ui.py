"""Agent UI 交互路由 — 处理前端 UI 组件的用户操作回调。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class UIActionRequest(BaseModel):
    component_id: str
    component_type: str
    action_id: str
    action_type: str
    payload: dict = {}
    conversation_id: str = ""
    run_id: str = ""


class UIActionResponse(BaseModel):
    ok: bool = True
    message: str = ""
    data: dict = {}


@router.post("/ui/action")
async def handle_ui_action(body: UIActionRequest, user=Depends(get_current_user)):
    """处理前端 UI 组件的交互事件。

    当前为 MVP 实现，仅记录日志并返回确认。
    后续可扩展为将交互注入 Agent 对话上下文。

    Args:
        body: UI 交互请求体，含 component_id / action_id / action_type 等。
        user: 当前认证用户（依赖注入）。

    Returns:
        UIActionResponse 确认响应。
    """
    logger.info(
        "UI action: user=%s component=%s action=%s type=%s",
        user["username"],
        body.component_id,
        body.action_id,
        body.action_type,
    )

    # MVP: 记录交互，后续可注入 Agent 对话
    return UIActionResponse(
        ok=True,
        message=f"已处理 {body.action_id} 操作",
        data={"component_id": body.component_id, "action_id": body.action_id},
    )

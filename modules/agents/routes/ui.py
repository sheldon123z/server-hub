"""Agent UI 交互路由 — 处理前端 UI 组件的用户操作回调。"""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from auth.dependencies import require_role

logger = logging.getLogger(__name__)

router = APIRouter()

# payload 允许的最大 JSON 序列化大小 (10KB)
_MAX_PAYLOAD_BYTES = 10 * 1024

# 合法的组件类型和操作类型
VALID_COMPONENT_TYPES = ("chart", "table", "form", "card")
VALID_ACTION_TYPES = ("submit", "reset", "agent", "download", "refresh", "navigate")


class UIActionRequest(BaseModel):
    component_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]+$")
    component_type: Literal["chart", "table", "form", "card"]
    action_id: str = Field(..., min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_\-]+$")
    action_type: Literal["submit", "reset", "agent", "download", "refresh", "navigate"]
    payload: dict = Field(default_factory=dict)
    conversation_id: str = Field(default="", max_length=128)
    run_id: str = Field(default="", max_length=128)

    @field_validator("payload")
    @classmethod
    def validate_payload_size(cls, v: dict) -> dict:
        """限制 payload 序列化后不超过 10KB，防止内存滥用。"""
        size = len(json.dumps(v, default=str))
        if size > _MAX_PAYLOAD_BYTES:
            msg = f"payload 过大 ({size} bytes)，最大允许 {_MAX_PAYLOAD_BYTES} bytes"
            raise ValueError(msg)
        return v


class UIActionResponse(BaseModel):
    ok: bool = True
    message: str = ""
    data: dict = {}


@router.post("/ui/action")
async def handle_ui_action(body: UIActionRequest, user=Depends(require_role("admin"))):
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

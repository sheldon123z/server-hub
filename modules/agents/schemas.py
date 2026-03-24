"""Pydantic 请求/响应模型"""

from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    safety_mode: str = "supervised"


class ApprovalAction(BaseModel):
    action: str  # "approve" or "reject"
    reason: str = ""


class PatrolUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = None


class AgentSettingsUpdate(BaseModel):
    default_model: Optional[str] = None
    patrol_model: Optional[str] = None

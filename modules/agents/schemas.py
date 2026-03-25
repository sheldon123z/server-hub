"""Pydantic 请求/响应模型"""

from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    safety_mode: str = "supervised"
    page_context: Optional[str] = None  # 页面上下文标识: "dashboard"/"docker"/"users" 等


class ApprovalAction(BaseModel):
    action: str  # "approve" or "reject"
    reason: str = ""


class PatrolUpdate(BaseModel):
    enabled: Optional[bool] = None
    interval_minutes: Optional[int] = None
    prompt: Optional[str] = None
    check_tools: Optional[str] = None


class AgentSettingsUpdate(BaseModel):
    default_model: Optional[str] = None
    patrol_model: Optional[str] = None


class SubAgentConfig(BaseModel):
    name: str
    description: str
    system_prompt: str
    tools: list[str] = []
    model: Optional[str] = None


class PromptUpdate(BaseModel):
    content: str

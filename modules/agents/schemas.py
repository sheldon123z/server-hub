"""Pydantic 请求/响应模型"""

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None
    safety_mode: str = "supervised"
    page_context: str | None = None  # 页面上下文标识: "dashboard"/"docker"/"users" 等
    skill_id: str | None = None
    run_id: str | None = None


class ApprovalAction(BaseModel):
    action: str  # "approve" or "reject"
    reason: str = ""


class PatrolUpdate(BaseModel):
    enabled: bool | None = None
    interval_minutes: int | None = None
    prompt: str | None = None
    check_tools: str | None = None


class AgentSettingsUpdate(BaseModel):
    default_model: str | None = None
    patrol_model: str | None = None


class SubAgentConfig(BaseModel):
    name: str
    description: str
    system_prompt: str
    tools: list[str] = []
    model: str | None = None
    model_purpose: str | None = None
    middleware_profile: str | None = None
    interrupt_on: dict | None = None


class PromptUpdate(BaseModel):
    content: str


class RunCancelRequest(BaseModel):
    reason: str = ""


class InstallFromRepoRequest(BaseModel):
    repo_path: str


class SkillSourceUpdate(BaseModel):
    roots: list[str] = Field(default_factory=list)

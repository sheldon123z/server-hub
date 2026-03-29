"""Pydantic 请求/响应模型"""

from pydantic import BaseModel


class PlaybookCreateRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "general"
    system_prompt: str
    parameters: str = "[]"  # JSON string
    tools_required: str = ""
    validation_rules: str = "{}"
    trigger_config: str = '{"type":"manual"}'
    safety_mode: str | None = None
    steps_visual: str | None = None
    tags: str = ""


class PlaybookUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    category: str | None = None
    system_prompt: str | None = None
    parameters: str | None = None
    tools_required: str | None = None
    validation_rules: str | None = None
    trigger_config: str | None = None
    safety_mode: str | None = None
    steps_visual: str | None = None
    tags: str | None = None


class PlaybookRunRequest(BaseModel):
    parameters: dict = {}


class CredentialCreateRequest(BaseModel):
    name: str
    value: str
    description: str = ""
    credential_type: str = "generic"

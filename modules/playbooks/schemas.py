"""Pydantic 请求/响应模型"""

from typing import Optional

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
    safety_mode: Optional[str] = None
    steps_visual: Optional[str] = None
    tags: str = ""


class PlaybookUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    system_prompt: Optional[str] = None
    parameters: Optional[str] = None
    tools_required: Optional[str] = None
    validation_rules: Optional[str] = None
    trigger_config: Optional[str] = None
    safety_mode: Optional[str] = None
    steps_visual: Optional[str] = None
    tags: Optional[str] = None


class PlaybookRunRequest(BaseModel):
    parameters: dict = {}


class CredentialCreateRequest(BaseModel):
    name: str
    value: str
    description: str = ""
    credential_type: str = "generic"

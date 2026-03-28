"""多服务器管理 Pydantic 请求模型"""

from typing import Optional, Union

from pydantic import BaseModel, Field, field_validator


def _normalize_tags(v: Union[str, list, None]) -> list[str]:
    """将 tags 统一转换为 list[str]，接受逗号分隔字符串或列表"""
    if v is None:
        return []
    if isinstance(v, list):
        return [t.strip() for t in v if isinstance(t, str) and t.strip()]
    if isinstance(v, str):
        return [t.strip() for t in v.split(",") if t.strip()]
    return []


class ServerCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    hostname: str = Field(default="", max_length=255)
    ip_address: str = Field(..., min_length=1, max_length=45)
    agent_port: int = Field(default=9901, ge=1, le=65535)
    ssh_user: Optional[str] = None
    ssh_port: int = Field(default=22, ge=1, le=65535)
    ssh_key_credential: Optional[str] = None
    tags: Union[str, list[str]] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        return _normalize_tags(v)

    @field_validator("hostname", mode="before")
    @classmethod
    def default_hostname(cls, v, info):
        """hostname 为空时回退到 name"""
        if not v and info.data.get("name"):
            return info.data["name"]
        return v or ""


class ServerUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    hostname: Optional[str] = Field(default=None, max_length=255)
    ip_address: Optional[str] = Field(default=None, min_length=1, max_length=45)
    agent_port: Optional[int] = Field(default=None, ge=1, le=65535)
    ssh_user: Optional[str] = None
    ssh_port: Optional[int] = Field(default=None, ge=1, le=65535)
    ssh_key_credential: Optional[str] = None
    tags: Optional[Union[str, list[str]]] = None

    @field_validator("tags", mode="before")
    @classmethod
    def parse_tags(cls, v):
        if v is None:
            return None
        return _normalize_tags(v)


class ServerGroupCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: Optional[str] = None
    color: str = Field(default="#38bdf8", pattern=r"^#[0-9a-fA-F]{6}$")

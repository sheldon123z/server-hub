"""RBAC 权限矩阵 — Pydantic 数据模型"""

from datetime import datetime

from pydantic import BaseModel, Field


class Permission(BaseModel):
    id: int | None = None
    role_id: str
    resource: str
    action: str
    scope: str = "*"


class Role(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    description: str | None = None
    builtin: bool = False
    created_at: datetime | None = None
    permissions: list[Permission] = []


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field("", max_length=128)
    description: str = Field("", max_length=512)
    permissions: list[dict] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    display_name: str | None = None
    description: str | None = None
    permissions: list[dict] | None = None


class UserRole(BaseModel):
    user_id: str
    role_id: str


class AssignRoleRequest(BaseModel):
    role_id: str


class UserPermissionsResponse(BaseModel):
    user_id: str
    roles: list[str]
    permissions: list[Permission]

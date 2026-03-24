"""认证相关数据模型"""

from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenData(BaseModel):
    username: str
    role: str


class UserInfo(BaseModel):
    id: int
    username: str
    display_name: str
    role: str
    disabled: bool
    created_at: Optional[str] = None
    last_login: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""
    role: str = "user"

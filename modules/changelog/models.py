"""变更日历 Pydantic 模型"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 变更事件
# ---------------------------------------------------------------------------

EventType = Literal["deploy", "config", "restart", "maintenance", "other"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class ChangeEventCreate(BaseModel):
    event_type: EventType = "other"
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    affected_services: str | None = Field(default=None, description="受影响服务，逗号分隔")
    risk_level: RiskLevel = "low"
    duration_minutes: int | None = Field(default=None, ge=0)


class ChangeEvent(BaseModel):
    id: int
    timestamp: datetime
    event_type: EventType
    title: str
    description: str | None = None
    operator: str | None = None
    affected_services: str | None = None
    risk_level: RiskLevel = "low"
    duration_minutes: int | None = None


# ---------------------------------------------------------------------------
# 冻结窗口
# ---------------------------------------------------------------------------


class FreezeWindowCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime
    reason: str | None = None


class FreezeWindow(BaseModel):
    id: int
    title: str
    start_time: datetime
    end_time: datetime
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime | None = None

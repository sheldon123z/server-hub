"""告警规则与历史 Pydantic 模型"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class AlertRule(BaseModel):
    id: str
    name: str
    enabled: bool = True
    resource: str  # system|docker|users|services|gpu
    server_scope: str = "*"
    metric: str  # 指标路径，如 swap.percent / disks./.percent
    operator: Literal[">", ">=", "<", "<=", "==", "!="] = ">"
    threshold: float | None = None
    duration_seconds: int = Field(default=60, ge=0)
    severity: Literal["info", "warning", "critical"] = "warning"
    cooldown_seconds: int = Field(default=300, ge=0)
    auto_action: str | None = None  # kill_user_processes | notify_user | restart_service
    auto_action_config: str | None = None  # JSON 字符串
    notification_channels: str | None = None  # 逗号分隔的 channel_id，None=全部
    notification_template: str | None = None
    created_by: str | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None


class AlertHistory(BaseModel):
    id: int
    rule_id: str | None
    server_id: str = "local"
    status: Literal["firing", "resolved"] = "firing"
    value: float | None = None
    message: str | None = None
    fired_at: datetime
    resolved_at: datetime | None = None
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    # 兼容旧字段
    severity: str | None = None
    rule_name: str | None = None


class AlertRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    enabled: bool = True
    resource: str = Field(..., description="资源类型: system|docker|users|services|gpu")
    server_scope: str = "*"
    metric: str = Field(..., description="指标路径，如 swap.percent")
    operator: Literal[">", ">=", "<", "<=", "==", "!="] = ">"
    threshold: float | None = None
    duration_seconds: int = Field(default=60, ge=0)
    severity: Literal["info", "warning", "critical"] = "warning"
    cooldown_seconds: int = Field(default=300, ge=0)
    auto_action: str | None = None
    auto_action_config: str | None = None
    notification_channels: str | None = None
    notification_template: str | None = None


class AlertRuleUpdate(BaseModel):
    name: str | None = None
    enabled: bool | None = None
    resource: str | None = None
    server_scope: str | None = None
    metric: str | None = None
    operator: Literal[">", ">=", "<", "<=", "==", "!="] | None = None
    threshold: float | None = None
    duration_seconds: int | None = None
    severity: Literal["info", "warning", "critical"] | None = None
    cooldown_seconds: int | None = None
    auto_action: str | None = None
    auto_action_config: str | None = None
    notification_channels: str | None = None
    notification_template: str | None = None

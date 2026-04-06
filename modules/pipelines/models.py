"""Pipeline 编排引擎 — Pydantic 数据模型"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Step 类型常量
# ---------------------------------------------------------------------------

STEP_TYPES = Literal[
    "shell",
    "ssh",
    "playbook",
    "http",
    "agent",
    "approval",
    "condition",
    "parallel",
    "delay",
    "notify",
]

# ---------------------------------------------------------------------------
# 失败策略
# ---------------------------------------------------------------------------

ON_FAILURE_STRATEGIES = Literal[
    "abort",
    "skip",
    "retry",
    "notify_continue",
]
# 注: "goto:{step_id}" 格式在运行时做字符串前缀匹配

# ---------------------------------------------------------------------------
# Step 定义
# ---------------------------------------------------------------------------


class StepDefinition(BaseModel):
    """单个 Pipeline Step 的定义"""

    id: str = Field(..., description="Step 唯一标识")
    type: STEP_TYPES = Field(..., description="Step 类型")
    name: str = Field("", description="Step 显示名")

    # shell / ssh
    command: str | None = Field(None, description="Shell/SSH 命令")
    host: str | None = Field(None, description="SSH 目标主机")

    # playbook
    playbook_id: str | None = Field(None, description="关联的剧本 ID")

    # http
    url: str | None = Field(None, description="HTTP 请求地址")
    method: str | None = Field(None, description="HTTP 方法")
    headers: dict[str, str] | None = Field(None, description="HTTP 请求头")
    body: str | None = Field(None, description="HTTP 请求体")

    # agent
    prompt: str | None = Field(None, description="Agent 提示词")
    model: str | None = Field(None, description="Agent 模型标识")
    output_format: str | None = Field(None, description="Agent 输出格式: json / text")

    # approval
    assignee: str | None = Field(None, description="审批人")

    # condition
    expression: str | None = Field(None, description="条件表达式")
    on_true: str | None = Field(None, description="条件为真时跳转的 step_id")
    on_false: str | None = Field(None, description="条件为假时跳转的 step_id")

    # parallel
    branches: list[StepDefinition] | None = Field(None, description="并行分支列表")

    # delay
    seconds: int | None = Field(None, description="延迟秒数")

    # notify
    channel: str | None = Field(None, description="通知渠道: telegram / email / webhook")
    message: str | None = Field(None, description="通知消息模板")

    # 通用
    params: dict[str, Any] | None = Field(None, description="传递给 step 的额外参数")
    timeout: int | None = Field(None, description="Step 超时（秒）")
    on_failure: str | None = Field("abort", description="失败策略")
    retry_count: int | None = Field(None, description="重试次数")
    retry_delay: int | None = Field(None, description="重试间隔（秒）")


# ---------------------------------------------------------------------------
# 触发配置
# ---------------------------------------------------------------------------


class TriggerConfig(BaseModel):
    """Pipeline 触发配置"""

    type: Literal["manual", "cron", "alert", "api"] = Field("manual", description="触发类型")
    cron: str | None = Field(None, description="Cron 表达式（type=cron 时必填）")
    alert_rule_id: str | None = Field(None, description="告警规则 ID（type=alert 时必填）")


# ---------------------------------------------------------------------------
# 参数定义
# ---------------------------------------------------------------------------


class ParamDefinition(BaseModel):
    """Pipeline 运行参数定义"""

    name: str = Field(..., description="参数名")
    type: Literal["string", "number", "boolean", "secret", "array"] = Field("string", description="参数类型")
    required: bool = Field(False, description="是否必填")
    default: Any = Field(None, description="默认值")
    description: str = Field("", description="参数说明")


# ---------------------------------------------------------------------------
# Pipeline 定义 (从 YAML 解析)
# ---------------------------------------------------------------------------


class PipelineDefinition(BaseModel):
    """Pipeline 完整定义"""

    name: str = Field(..., description="唯一标识名")
    display_name: str = Field("", description="中文显示名")
    description: str = Field("", description="描述")
    version: int = Field(1, description="版本号")
    max_concurrent_runs: int = Field(1, description="最大并发运行数")
    timeout: int | None = Field(None, description="整体超时（秒）")
    trigger: TriggerConfig = Field(default_factory=TriggerConfig, description="触发配置")
    params: list[ParamDefinition] = Field(default_factory=list, description="参数定义列表")
    steps: list[StepDefinition] = Field(default_factory=list, description="步骤列表")


# ---------------------------------------------------------------------------
# Pipeline Run (数据库行映射)
# ---------------------------------------------------------------------------

RUN_STATUS = Literal["pending", "running", "paused", "completed", "failed", "cancelled"]
STEP_STATUS = Literal["pending", "running", "completed", "failed", "skipped"]


class PipelineRun(BaseModel):
    """Pipeline 运行实例"""

    id: str = Field(..., description="运行 ID (UUID)")
    pipeline_id: str = Field(..., description="关联 Pipeline ID")
    pipeline_version: int = Field(1, description="本次运行对应的版本")
    status: RUN_STATUS = Field("pending", description="运行状态")
    params: dict[str, Any] = Field(default_factory=dict, description="运行参数")
    current_step_id: str | None = Field(None, description="当前执行的 step")
    steps_state: dict[str, Any] = Field(default_factory=dict, description="每个 step 的状态和输出")
    trigger_type: str | None = Field(None, description="触发方式")
    started_at: str | None = None
    completed_at: str | None = None
    started_by: str | None = None
    error: str | None = None
    langgraph_thread_id: str | None = None
    summary: str | None = None


# ---------------------------------------------------------------------------
# Pipeline State (LangGraph 运行时状态)
# ---------------------------------------------------------------------------


class PipelineState(TypedDict, total=False):
    """LangGraph StateGraph 的运行时状态"""

    run_id: str
    pipeline_id: str
    params: dict[str, Any]
    step_outputs: dict[str, Any]  # {step_id: output}
    current_step: str
    status: str
    error: str | None

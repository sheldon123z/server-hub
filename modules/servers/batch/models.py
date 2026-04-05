"""Fleet 批量操作 Pydantic 模型"""

from typing import Any, Literal

from pydantic import BaseModel, Field


class BatchJobCreate(BaseModel):
    """创建批量任务的请求体"""

    name: str = Field(..., min_length=1, max_length=200)
    type: Literal["command", "service_action", "docker_action", "script", "playbook"]
    payload: dict[str, Any]
    server_ids: list[str] = Field(..., min_length=1)
    strategy: Literal["parallel", "serial", "rolling"] = "parallel"
    rolling_batch_size: int = Field(default=1, ge=1, le=50)
    stop_on_failure: bool = False


class BatchJobResult(BaseModel):
    """单台服务器的执行结果"""

    id: int
    job_id: str
    server_id: str
    status: str  # success | failed | cancelled
    output: str | None
    error: str | None
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None


class BatchJobProgress(BaseModel):
    """批量任务进度"""

    total: int
    completed: int
    failed: int
    running: int


class BatchJob(BaseModel):
    """批量任务完整信息"""

    id: str
    name: str
    type: str
    payload: dict[str, Any]
    server_ids: list[str]
    strategy: str
    rolling_batch_size: int
    stop_on_failure: bool
    status: str  # pending | running | completed | partial_failure | failed | cancelled
    progress: BatchJobProgress | None
    created_by: str | None
    created_at: str
    completed_at: str | None
    results: list[BatchJobResult] = []


class BatchTemplate(BaseModel):
    """批量操作预置模板"""

    id: str
    name: str
    description: str | None
    type: str
    payload: dict[str, Any]
    strategy: str
    rolling_batch_size: int
    stop_on_failure: bool
    is_builtin: bool
    created_at: str

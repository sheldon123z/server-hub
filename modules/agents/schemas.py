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


# ---------------------------------------------------------------------------
# Skill System — 技能 CRUD / 评测 / 市场 / 版本
# ---------------------------------------------------------------------------


class SkillCreate(BaseModel):
    """创建技能请求体"""

    name: str = Field(..., min_length=1, max_length=64, description="kebab-case 技能标识符")
    skill_md: str = Field(..., description="SKILL.md 全文（含 YAML frontmatter）")
    files: dict[str, str] | None = Field(default=None, description="附属文件 {相对路径: 内容}")


class SkillUpdate(BaseModel):
    """更新技能请求体"""

    skill_md: str | None = Field(default=None, description="SKILL.md 全文")
    files: dict[str, str] | None = Field(default=None, description="附属文件 {相对路径: 内容}")


class SkillFileUpload(BaseModel):
    """上传单个附属文件"""

    content: str


class EvalRunRequest(BaseModel):
    """执行技能评测"""

    eval_id: int | None = Field(default=None, description="指定单个评测用例 ID，为空则执行全部")
    mode: str = Field(default="ab", description="评测模式: ab(A/B对比) 或 single(仅有技能)")


class MarketInstallRequest(BaseModel):
    """从市场安装技能"""

    name: str
    version: str | None = None


class RollbackRequest(BaseModel):
    """回滚技能到指定版本"""

    version: str

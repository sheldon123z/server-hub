"""智能体团队 API 路由 — CRUD + 执行 + 模板

路由前缀: /api/agents/teams
认证: 所有端点需要登录，写操作需要 admin 角色
"""

import contextlib
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from auth.dependencies import get_current_user, require_role
from modules.agents.teams.store import TeamStore, get_team_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/teams", tags=["agent-teams"])


# ─── 请求模型 ───


class TeamCreateRequest(BaseModel):
    """创建团队请求"""

    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(default="", max_length=500)
    topology: str = Field(default="supervisor", pattern=r"^(supervisor|swarm|pipeline)$")
    config: dict = Field(default_factory=dict)
    default_model: str | None = None
    safety_mode: str = Field(default="supervised", pattern=r"^(supervised|autonomous)$")
    max_steps: int = Field(default=50, ge=10, le=200)
    timeout_seconds: int = Field(default=300, ge=30, le=1800)


class TeamUpdateRequest(BaseModel):
    """更新团队请求"""

    name: str | None = Field(default=None, min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    topology: str | None = Field(default=None, pattern=r"^(supervisor|swarm|pipeline)$")
    config: dict | None = None
    default_model: str | None = None
    safety_mode: str | None = Field(default=None, pattern=r"^(supervised|autonomous)$")
    max_steps: int | None = Field(default=None, ge=10, le=200)
    timeout_seconds: int | None = Field(default=None, ge=30, le=1800)
    enabled: int | None = Field(default=None, ge=0, le=1)


class MemberCreateRequest(BaseModel):
    """添加成员请求"""

    name: str = Field(..., min_length=1, max_length=30)
    agent_type: str = Field(default="worker", pattern=r"^(leader|worker|reviewer)$")
    description: str = Field(default="", max_length=200)
    system_prompt: str = Field(..., min_length=1)
    tools: list[str] = Field(default_factory=list)
    model_id: str | None = None
    max_calls: int = Field(default=15, ge=1, le=100)
    handoff_targets: list[str] = Field(default_factory=list)
    position: int = Field(default=0, ge=0, le=20)
    config: dict = Field(default_factory=dict)


class MemberUpdateRequest(BaseModel):
    """更新成员请求"""

    name: str | None = Field(default=None, min_length=1, max_length=30)
    agent_type: str | None = Field(default=None, pattern=r"^(leader|worker|reviewer)$")
    description: str | None = Field(default=None, max_length=200)
    system_prompt: str | None = None
    tools: list[str] | None = None
    model_id: str | None = None
    max_calls: int | None = Field(default=None, ge=1, le=100)
    handoff_targets: list[str] | None = None
    position: int | None = Field(default=None, ge=0, le=20)
    config: dict | None = None


class ExecuteRequest(BaseModel):
    """执行团队任务请求"""

    instruction: str = Field(..., min_length=1, max_length=5000)


# ─── 团队 CRUD ───


@router.get("")
async def list_teams(
    enabled_only: bool = Query(default=False, description="仅返回已启用的团队"),
    user=Depends(get_current_user),
    store: TeamStore = Depends(get_team_store),
):
    """列出所有团队"""
    teams = await store.list_teams(enabled_only=enabled_only)

    # 为每个团队附加成员数量
    result = []
    for team in teams:
        members = await store.get_members(team["id"])
        team["member_count"] = len(members)
        result.append(team)

    return result


@router.post("")
async def create_team(
    body: TeamCreateRequest,
    user=Depends(require_role("admin")),
    store: TeamStore = Depends(get_team_store),
):
    """创建新团队"""
    data = body.model_dump(exclude_none=True)
    data["created_by"] = user["username"]

    try:
        team = await store.create_team(data)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"团队名称 '{body.name}' 已存在",
            )
        logger.exception("创建团队失败: %s", e)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

    return {"ok": True, "team": team}


@router.get("/templates")
async def list_templates(user=Depends(get_current_user)):
    """列出所有内置模板"""
    from modules.agents.teams.templates import get_template_list

    return get_template_list()


@router.post("/templates/{template_id}/instantiate")
async def instantiate_template(
    template_id: str,
    user=Depends(require_role("admin")),
    store: TeamStore = Depends(get_team_store),
):
    """从模板创建团队（复制模板数据到新团队）"""
    from modules.agents.teams.templates import get_template_by_id

    tmpl = get_template_by_id(template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail=f"模板 {template_id} 不存在")

    # 检查同名团队是否已存在
    existing = await store.get_team(tmpl["id"])
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"团队 '{tmpl['name']}' 已存在（来自同一模板）",
        )

    try:
        team = await store.create_team(
            {
                "id": tmpl["id"],
                "name": tmpl["name"],
                "description": tmpl.get("description", ""),
                "topology": tmpl["topology"],
                "config": tmpl.get("config", {}),
                "safety_mode": tmpl.get("safety_mode", "supervised"),
                "max_steps": tmpl.get("max_steps", 50),
                "timeout_seconds": tmpl.get("timeout_seconds", 300),
                "is_builtin": 1,
                "created_by": user["username"],
            }
        )

        for member in tmpl.get("members", []):
            await store.add_member(team["id"], member)

        members = await store.get_members(team["id"])
        return {"ok": True, "team": team, "members": members}

    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="模板团队已存在")
        logger.exception("实例化模板失败: %s", e)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")


@router.get("/executions/{execution_id}")
async def get_execution_detail(
    execution_id: str,
    user=Depends(get_current_user),
    store: TeamStore = Depends(get_team_store),
):
    """获取执行详情 + 消息流"""
    execution = await store.get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")

    messages = await store.get_messages(execution_id)

    # 解析 JSON 字段
    if execution.get("agent_outputs"):
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            execution["agent_outputs"] = json.loads(execution["agent_outputs"])

    return {"execution": execution, "messages": messages}


@router.post("/executions/{execution_id}/cancel")
async def cancel_execution(
    execution_id: str,
    user=Depends(require_role("admin")),
):
    """取消正在运行的执行"""
    from modules.agents.teams.engine import get_team_engine

    engine = get_team_engine()
    cancelled = await engine.cancel_execution(execution_id)

    if not cancelled:
        raise HTTPException(status_code=404, detail="执行不存在或已完成")

    return {"ok": True, "execution_id": execution_id, "status": "cancelled"}


@router.get("/{team_id}")
async def get_team_detail(
    team_id: str,
    user=Depends(get_current_user),
    store: TeamStore = Depends(get_team_store),
):
    """获取团队详情 + 成员列表"""
    team = await store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    members = await store.get_members(team_id)

    # 解析成员的 JSON 字段
    for m in members:
        for field in ("tools_json", "handoff_targets", "config_json"):
            if field in m and isinstance(m[field], str):
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    m[field] = json.loads(m[field])

    return {"team": team, "members": members}


@router.put("/{team_id}")
async def update_team(
    team_id: str,
    body: TeamUpdateRequest,
    user=Depends(require_role("admin")),
    store: TeamStore = Depends(get_team_store),
):
    """更新团队配置"""
    from modules.agents.teams.engine import get_team_engine

    team = await store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="无更新内容")

    try:
        updated = await store.update_team(team_id, data)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="团队名称已存在")
        logger.exception("更新团队失败: %s", e)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

    # 清除图缓存
    engine = get_team_engine()
    engine.invalidate_cache(team_id)

    return {"ok": True, "team": updated}


@router.delete("/{team_id}")
async def delete_team(
    team_id: str,
    user=Depends(require_role("admin")),
    store: TeamStore = Depends(get_team_store),
):
    """删除团队（内置团队不可删除）"""
    from modules.agents.teams.engine import get_team_engine

    team = await store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    if team.get("is_builtin"):
        raise HTTPException(status_code=403, detail="内置团队不可删除")

    await store.delete_team(team_id)

    # 清除图缓存
    engine = get_team_engine()
    engine.invalidate_cache(team_id)

    return {"ok": True, "team_id": team_id}


# ─── 成员 CRUD ───


@router.post("/{team_id}/members")
async def add_member(
    team_id: str,
    body: MemberCreateRequest,
    user=Depends(require_role("admin")),
    store: TeamStore = Depends(get_team_store),
):
    """添加团队成员"""
    from modules.agents.teams.engine import get_team_engine

    team = await store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    data = body.model_dump(exclude_none=True)

    try:
        member = await store.add_member(team_id, data)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(
                status_code=409,
                detail=f"成员名称 '{body.name}' 在该团队中已存在",
            )
        logger.exception("添加成员失败: %s", e)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

    # 清除图缓存
    engine = get_team_engine()
    engine.invalidate_cache(team_id)

    return {"ok": True, "member": member}


@router.put("/members/{member_id}")
async def update_member(
    member_id: str,
    body: MemberUpdateRequest,
    user=Depends(require_role("admin")),
    store: TeamStore = Depends(get_team_store),
):
    """更新团队成员"""
    from modules.agents.teams.engine import get_team_engine

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="无更新内容")

    try:
        member = await store.update_member(member_id, data)
    except Exception as e:
        if "UNIQUE" in str(e):
            raise HTTPException(status_code=409, detail="成员名称已存在")
        logger.exception("更新成员失败: %s", e)
        raise HTTPException(status_code=500, detail="操作失败，请稍后重试")

    if not member:
        raise HTTPException(status_code=404, detail="成员不存在")

    # 清除所属团队的图缓存
    team_id = member.get("team_id")
    if team_id:
        engine = get_team_engine()
        engine.invalidate_cache(team_id)

    return {"ok": True, "member": member}


@router.delete("/members/{member_id}")
async def remove_member(
    member_id: str,
    user=Depends(require_role("admin")),
    store: TeamStore = Depends(get_team_store),
):
    """移除团队成员"""
    from modules.agents.teams.engine import get_team_engine

    # 先通过 Store 查到 team_id 以便清缓存
    team_id = await store.get_member_team_id(member_id)
    if not team_id:
        raise HTTPException(status_code=404, detail="成员不存在")

    await store.remove_member(member_id)

    engine = get_team_engine()
    engine.invalidate_cache(team_id)

    return {"ok": True, "member_id": member_id}


# ─── 执行 ───


@router.post("/{team_id}/execute")
async def execute_team(
    team_id: str,
    body: ExecuteRequest,
    user=Depends(require_role("admin")),
    store: TeamStore = Depends(get_team_store),
):
    """启动团队执行，返回 SSE 事件流

    SSE 事件类型:
    - team_start: 团队开始执行
    - agent_start: 成员开始工作
    - agent_message: 成员 LLM 输出（流式）
    - agent_tool_call: 成员工具调用
    - agent_tool_result: 工具返回结果
    - agent_complete: 成员完成
    - team_error: 执行错误
    - team_complete: 团队完成
    """
    from modules.agents.teams.engine import get_team_engine

    team = await store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    if not team.get("enabled"):
        raise HTTPException(status_code=400, detail="团队已禁用")

    engine = get_team_engine()

    async def event_generator():
        """SSE 事件生成器"""
        try:
            async for event in engine.execute(
                team_id=team_id,
                instruction=body.instruction,
                username=user["username"],
                user_role=user.get("role", "user"),
            ):
                event_type = event.get("event", "message")
                event_data = event.get("data", {})

                yield {
                    "event": event_type,
                    "data": json.dumps(event_data, ensure_ascii=False),
                }

        except Exception as e:
            logger.exception("团队执行 SSE 流异常: %s", e)
            yield {
                "event": "team_error",
                "data": json.dumps({"error": str(e)}, ensure_ascii=False),
            }

        # 结束标记
        yield {
            "event": "done",
            "data": json.dumps({"team_id": team_id}, ensure_ascii=False),
        }

    return EventSourceResponse(event_generator())


@router.get("/{team_id}/executions")
async def list_team_executions(
    team_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    user=Depends(get_current_user),
    store: TeamStore = Depends(get_team_store),
):
    """获取团队的执行历史"""
    team = await store.get_team(team_id)
    if not team:
        raise HTTPException(status_code=404, detail="团队不存在")

    executions = await store.list_executions(team_id=team_id, limit=limit)

    # 解析 JSON 字段
    for ex in executions:
        if ex.get("agent_outputs"):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                ex["agent_outputs"] = json.loads(ex["agent_outputs"])

    return executions

"""Pipeline 专属 AI Agent — 独立于主 Agent 系统

直接使用 create_deep_agent() 底层 API，不走 build_agent() 缓存层。
原因：
1. build_agent() 签名是 (safety_mode, purpose, user_role, user)，
   不支持自定义 prompt / tool subset / middleware
2. build_agent() 有全局缓存，Pipeline Agent 需要 per-run 实例
3. Pipeline Agent 使用精简 middleware（无 Filesystem / HumanInTheLoop / Memory）
"""

import contextlib
import logging
from pathlib import Path

import aiosqlite
from deepagents import create_deep_agent
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from modules.agents.llm import get_chat_model
from modules.agents.sandbox import SafeLocalShellBackend
from modules.agents.tools.registry import get_registered_tools
from modules.pipelines.steps.agent import SAFE_TOOLS
from modules.pipelines.tools.pipeline_tools import get_pipeline_tools

logger = logging.getLogger(__name__)

PIPELINE_SYSTEM_PROMPT = """你是 ServerHub Pipeline 执行助手。

## 当前任务
Pipeline: {pipeline_name}
运行 ID: {run_id}
{task_description}

## 你的角色

你是这条流水线的 AI 只读顾问。你的职责：
1. 在 AI 审查节点执行分析任务（安全审计、健康检查等）
2. 回答运维人员关于当前流水线的任何问题
3. 基于步骤输出提供专业建议

## 当前执行状态

{step_context}

## 行为准则

- 你只有只读查询权限，不能执行写入操作（不能重启服务、修改文件、管理容器）
- 危险操作必须通过 Pipeline 步骤本身执行，你不能代替
- 回答要简洁专业，优先给结论
- 分析结果用结构化格式呈现（表格、列表）
"""

_active_checkpointers: dict[str, AsyncSqliteSaver] = {}


def _load_safe_tools() -> list:
    """加载 SAFE_TOOLS 白名单中的工具对象"""
    registry = get_registered_tools()
    tools = []
    for name in SAFE_TOOLS:
        meta = registry.get(name)
        if meta:
            tools.append(meta.tool)
        else:
            logger.debug("SAFE_TOOLS 中的工具未注册: %s", name)
    return tools


async def create_pipeline_agent(
    run_id: str,
    pipeline_context: dict,
    thread_id: str,
    purpose: str = "patrol",
):
    """创建 Pipeline 专属 Agent 实例

    Args:
        run_id: 运行实例 ID
        pipeline_context: {pipeline_name, task_description, step_context}
        thread_id: LangGraph checkpoint thread ID
        purpose: "chat" 或 "patrol"（控制模型选择）

    Returns:
        (agent, invoke_config) 元组
    """
    model = get_chat_model(purpose)

    system_prompt = PIPELINE_SYSTEM_PROMPT.format(
        pipeline_name=pipeline_context.get("pipeline_name", ""),
        run_id=run_id,
        task_description=pipeline_context.get("task_description", ""),
        step_context=pipeline_context.get("step_context", "无"),
    )

    tools = _load_safe_tools() + get_pipeline_tools()
    backend = SafeLocalShellBackend(root_dir="~")

    middleware = [
        ModelRetryMiddleware(max_retries=3),
        ToolRetryMiddleware(max_retries=2),
        ModelCallLimitMiddleware(max_calls=50),
        ContextEditingMiddleware(
            edit=ClearToolUsesEdit(threshold_tokens=60000, keep_last_n=5),
        ),
    ]

    data_dir = Path("data")
    cp_path = data_dir / "pipeline-checkpoints.db"
    conn = await aiosqlite.connect(str(cp_path))
    checkpointer = AsyncSqliteSaver(conn)
    _active_checkpointers[run_id] = checkpointer

    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        interrupt_on=None,
        checkpointer=checkpointer,
        backend=backend,
        subagents=[],
        middleware=middleware,
        memory=None,
        skills=None,
        store=None,
    )

    invoke_config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }

    logger.info(
        "PipelineAgent 已创建: run=%s, thread=%s, tools=%d",
        run_id,
        thread_id,
        len(tools),
    )
    return agent, invoke_config


async def cleanup_pipeline_agent(run_id: str):
    """清理 Pipeline Agent 资源（run 结束时调用）"""
    cp = _active_checkpointers.pop(run_id, None)
    if cp and hasattr(cp, "conn") and cp.conn:
        with contextlib.suppress(Exception):
            await cp.conn.close()
    logger.debug("PipelineAgent 资源已清理: run=%s", run_id)

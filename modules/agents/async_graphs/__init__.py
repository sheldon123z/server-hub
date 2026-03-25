"""异步 SubAgent Graph 工厂 — 为 AsyncSubAgentMiddleware 编译独立运行的 graph

每个异步 SubAgent 被编译为独立的 LangGraph StateGraph，由 lg_compat.py
的 LG 兼容 API Server 在后台 asyncio.Task 中执行。

与同步 SubAgent 的区别:
- 同步 SubAgent: 由主 agent 的 SubAgentMiddleware 在 task() 工具中内联执行
- 异步 SubAgent: 由 LG Compat Server 在独立 thread 上执行，主 agent 可继续对话
"""

import logging
import os

import aiosqlite
from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    ToolRetryMiddleware,
    ModelCallLimitMiddleware,
)
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pathlib import Path

from config import settings
from modules.agents.llm import get_chat_model
from modules.agents.sandbox import SafeLocalShellBackend

# 各 graph 的 SPEC + get_tools
from .researcher import SPEC as RESEARCHER_SPEC, get_tools as researcher_tools
from .security_auditor import SPEC as SECURITY_AUDITOR_SPEC, get_tools as security_auditor_tools
from .correlation_analyzer import SPEC as CORRELATION_ANALYZER_SPEC, get_tools as correlation_analyzer_tools

# 向后兼容: deep_agent.py 可能从 subagents 导入，这里也 re-export
from modules.agents.subagents._async_specs import get_async_subagent_specs

logger = logging.getLogger(__name__)

# 所有 graph spec 注册表
ALL_SPECS = [
    (RESEARCHER_SPEC, researcher_tools),
    (SECURITY_AUDITOR_SPEC, security_auditor_tools),
    (CORRELATION_ANALYZER_SPEC, correlation_analyzer_tools),
]

# 异步 graph 共享的 checkpointer 连接
_async_checkpointer: AsyncSqliteSaver | None = None


async def _get_async_checkpointer() -> AsyncSqliteSaver:
    """获取异步 SubAgent 专用 checkpointer（独立于主 agent 的 checkpoint DB）"""
    global _async_checkpointer
    if _async_checkpointer is None:
        cp_path = str(Path(settings.db_path).parent / "async-checkpoints.db")
        Path(cp_path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(cp_path)
        _async_checkpointer = AsyncSqliteSaver(conn)
        logger.info(f"异步 SubAgent checkpointer: {cp_path}")
    return _async_checkpointer


def _create_backend() -> SafeLocalShellBackend:
    """创建安全后端（复用主 agent 同款配置）"""
    return SafeLocalShellBackend(
        root_dir=os.path.expanduser("~"),
        virtual_mode=False,
        timeout=120,
        max_output_bytes=200_000,
        inherit_env=True,
    )


def _build_middleware(profile: str, call_limit: int) -> list:
    """按 profile 构建 middleware"""
    mw = [ModelRetryMiddleware(max_retries=2, backoff_factor=1.0)]
    if profile in ("heavy", "ops"):
        mw.append(ToolRetryMiddleware(max_retries=2 if profile == "heavy" else 1, backoff_factor=1.0))
    mw.append(ModelCallLimitMiddleware(run_limit=call_limit))
    return mw


async def build_all_async_graphs() -> dict:
    """编译所有异步 SubAgent graph

    Returns:
        {graph_id: compiled_graph} 字典，传给 lg_compat.register_graph()
    """
    checkpointer = await _get_async_checkpointer()
    graphs = {}

    for spec, tools_fn in ALL_SPECS:
        graph_id = spec["graph_id"]
        try:
            model = get_chat_model(spec["model_purpose"])
            tools = tools_fn()
            middleware = _build_middleware(spec["middleware_profile"], spec["call_limit"])

            graph = create_agent(
                model=model,
                system_prompt=spec["system_prompt"],
                tools=tools,
                middleware=middleware,
                checkpointer=checkpointer,
            )
            graphs[graph_id] = graph
            logger.info(f"异步 graph '{graph_id}' 编译完成 (model={spec['model_purpose']}, tools={len(tools)})")
        except Exception as e:
            logger.error(f"异步 graph '{graph_id}' 编译失败: {e}")

    return graphs


__all__ = [
    "build_all_async_graphs",
    "get_async_subagent_specs",
    "ALL_SPECS",
]

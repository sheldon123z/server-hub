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
from modules.agents.subagents import (
    web_search, think, _get_tools_by_names,
    RESEARCHER_PROMPT, SECURITY_AUDITOR_PROMPT, CORRELATION_ANALYZER_PROMPT,
)

logger = logging.getLogger(__name__)

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


# ─── Graph 定义 ───

ASYNC_GRAPH_SPECS = {
    "researcher": {
        "system_prompt": RESEARCHER_PROMPT,
        "tools_fn": lambda: [web_search, think],
        "model_purpose": "chat",
        "middleware_profile": "light",
        "call_limit": 20,
    },
    "security-auditor": {
        "system_prompt": SECURITY_AUDITOR_PROMPT,
        "tools_fn": lambda: _get_tools_by_names(["get_system_overview", "check_compliance"]),
        "model_purpose": "patrol",
        "middleware_profile": "ops",
        "call_limit": 25,
    },
    "correlation-analyzer": {
        "system_prompt": CORRELATION_ANALYZER_PROMPT,
        "tools_fn": lambda: _get_tools_by_names([
            "analyze_resource_trend", "get_system_overview",
            "list_docker_containers", "get_container_logs",
            "list_systemd_services", "get_service_logs",
            "search_fault_cases", "get_user_login_history_tool",
            "get_active_sessions_tool", "list_docker_networks",
            "get_service_dependencies_tool",
        ]),
        "model_purpose": "chat",
        "middleware_profile": "heavy",
        "call_limit": 35,
    },
}


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

    for graph_id, spec in ASYNC_GRAPH_SPECS.items():
        try:
            model = get_chat_model(spec["model_purpose"])
            tools = spec["tools_fn"]()
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

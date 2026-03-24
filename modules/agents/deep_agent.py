"""Deep Agent 工厂 — 基于 deepagents 框架构建运维智能体

使用 create_deep_agent 获得的内置能力:
- 持久化 Shell 会话 (execute) — SafeLocalShellBackend
- 文件系统操作 (read_file/write_file/edit_file/ls/glob/grep)
- 任务规划 (write_todos) — TodoListMiddleware
- 子智能体委派 (task) — SubAgentMiddleware
- 人工审批 (interrupt_on) — HumanInTheLoopMiddleware
- 上下文压缩 (summarization) — SummarizationMiddleware

额外注入的 middleware:
- ModelRetryMiddleware — LLM 调用失败自动重试
- ToolRetryMiddleware — 工具调用失败自动重试
- ModelCallLimitMiddleware — 防止无限循环消耗 token
- ContextEditingMiddleware — 对话过长时清理旧工具输出
- ModelFallbackMiddleware — 主模型失败时切换备用模型（仅 chat）
"""

import logging
import os
import aiosqlite
from pathlib import Path

from deepagents import create_deep_agent
from langchain.agents.middleware import (
    ModelRetryMiddleware,
    ToolRetryMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ContextEditingMiddleware,
)
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config import settings
from modules.agents.llm import get_chat_model
from modules.agents.tools import get_server_tools
from modules.agents.safety import build_interrupt_config
from modules.agents.prompts import SYSTEM_PROMPT
from modules.agents.subagents import get_subagents
from modules.agents.sandbox import SafeLocalShellBackend

logger = logging.getLogger(__name__)

# 单例
_agent_cache: dict = {}


def _create_backend() -> SafeLocalShellBackend:
    """创建 SafeLocalShellBackend — 安全增强的 Shell 执行 + 文件系统能力"""
    return SafeLocalShellBackend(
        root_dir=os.path.expanduser("~"),
        virtual_mode=False,
        timeout=120,
        max_output_bytes=200_000,
        inherit_env=True,
    )


def _build_extra_middleware(purpose: str = "chat") -> list:
    """构建额外的 middleware 栈

    这些 middleware 通过 create_deep_agent(middleware=...) 参数注入，
    会被插入到框架自动注入的 middleware 之后、Anthropic 缓存之前。

    框架已自动注入: TodoList, Filesystem, SubAgent, Summarization, PatchToolCalls
    我们额外添加: ModelRetry, ToolRetry, ModelCallLimit, ContextEditing, ModelFallback
    """
    extra = []

    # 1. 模型调用重试 — 网络抖动、API 限流时自动重试
    extra.append(ModelRetryMiddleware(
        max_retries=3,
        backoff_factor=1.0,  # 1s → 2s → 4s 指数退避
    ))

    # 2. 工具调用重试 — 工具偶发失败时自动重试
    extra.append(ToolRetryMiddleware(
        max_retries=2,
        backoff_factor=0.5,
    ))

    # 3. 模型调用次数限制 — 防止 agent 陷入无限循环
    extra.append(ModelCallLimitMiddleware(
        run_limit=50,  # 单次对话最多 50 轮 LLM 调用
    ))

    # 4. 上下文编辑 — 对话过长时清理旧的工具输出，保留最近 5 个
    extra.append(ContextEditingMiddleware(
        edits=[ClearToolUsesEdit(
            trigger=80_000,  # 超过 80K token 时触发清理
            keep=5,          # 保留最近 5 个工具结果
        )],
    ))

    # 5. 模型降级 — 仅 chat 模式，主模型失败时尝试备用模型
    if purpose == "chat":
        fallback_model = settings.agent_patrol_model  # 用巡检模型作为备用
        if fallback_model != settings.agent_default_model:
            try:
                from modules.agents.llm import get_chat_model as _get_model
                fallback = _get_model("patrol")
                extra.append(ModelFallbackMiddleware(fallback))
                logger.info(f"ModelFallback 已配置: 备用模型 {fallback_model}")
            except Exception as e:
                logger.warning(f"ModelFallback 配置失败: {e}")

    return extra


async def build_agent(safety_mode: str = "supervised", purpose: str = "chat"):
    """构建 Deep Agent 实例

    Args:
        safety_mode: "supervised"(危险操作需审批) 或 "autonomous"(全自动)
        purpose: "chat"(对话) 或 "patrol"(巡检, 用便宜模型)
    """
    cache_key = f"{safety_mode}:{purpose}"
    if cache_key in _agent_cache:
        return _agent_cache[cache_key]

    model = get_chat_model(purpose)
    tools = get_server_tools()
    interrupt_config = build_interrupt_config(safety_mode)
    backend = _create_backend()
    subagents = get_subagents()
    extra_middleware = _build_extra_middleware(purpose)

    # Checkpoint 持久化
    checkpoint_path = settings.agent_checkpoint_db
    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    checkpointer = AsyncSqliteSaver(
        await aiosqlite.connect(checkpoint_path)
    )

    system_prompt = SYSTEM_PROMPT.format(safety_mode=safety_mode)

    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        interrupt_on=interrupt_config if interrupt_config else None,
        checkpointer=checkpointer,
        backend=backend,
        subagents=subagents,
        middleware=extra_middleware,
    )

    mw_names = [type(m).__name__ for m in extra_middleware]
    _agent_cache[cache_key] = agent
    logger.info(f"Deep Agent 已创建: mode={safety_mode}, purpose={purpose}, middleware={mw_names}")
    return agent


def reset_agent_cache():
    """重置 agent 缓存（模型切换后调用）"""
    global _agent_cache
    _agent_cache.clear()
    logger.info("Agent cache cleared")

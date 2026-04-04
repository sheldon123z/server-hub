"""Deep Agent 工厂 — 基于 deepagents 框架构建运维智能体

Middleware 栈 (13 个):
  框架自动注入: TodoList, Filesystem, SubAgent, Summarization, PatchToolCalls,
                AnthropicPromptCaching, HumanInTheLoop, Memory
  手动注入:     LoopDetection, ModelRetry, ToolRetry, ModelCallLimit, ContextEditing,
                [ModelFallback]

记忆系统:
  短期: AsyncSqliteSaver checkpoint（per-conversation state 持久化）
  长期: data/agent-memory.md（MemoryMiddleware 注入系统提示词，agent 通过 edit_file 更新）
  存储: AsyncSqliteStore（namespace+key-value 结构化数据）
"""

import logging
import os
from pathlib import Path

import aiosqlite
from deepagents import create_deep_agent
from langchain.agents.middleware import (
    ContextEditingMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    ToolRetryMiddleware,
)
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.store.sqlite import AsyncSqliteStore

from config import settings
from modules.agents.deferred_tools import (
    DeferredToolRegistry,
    set_deferred_registry,
    tool_search,
)
from modules.agents.llm import get_chat_model
from modules.agents.loop_detection import LoopDetectionMiddleware
from modules.agents.prompts import get_system_prompt
from modules.agents.safety import build_interrupt_config
from modules.agents.sandbox import SafeLocalShellBackend
from modules.agents.subagents import load_subagents
from modules.agents.deferred_tools import (
    DeferredToolRegistry,
    set_deferred_registry,
    tool_search,
)
from modules.agents.tools import get_server_tools, get_tools_split

logger = logging.getLogger(__name__)

# 单例
_agent_cache: dict = {}
_store: AsyncSqliteStore | None = None


def get_memory_path() -> Path:
    """运行时长期记忆文件路径。与仓库根 AGENTS.md 分离。"""
    return Path(settings.db_path).parent / "agent-memory.md"


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

    通过 create_deep_agent(middleware=...) 注入，插入到框架 base stack 之后、
    AnthropicPromptCaching 和 MemoryMiddleware 之前。

    框架自动注入: TodoList, Filesystem, SubAgent, Summarization, PatchToolCalls
    我们额外添加: LoopDetection, ModelRetry, ToolRetry, ModelCallLimit, ContextEditing, [ModelFallback]
    """
    extra = []

    # 0. 循环检测 — 检测重复工具调用，3 次警告 5 次强停
    extra.append(
        LoopDetectionMiddleware(
            window_size=20,
            warn_threshold=3,
            stop_threshold=5,
        )
    )

    # 1. 模型调用重试 — 网络抖动、API 限流时自动重试（3 次，1s → 2s → 4s）
    extra.append(ModelRetryMiddleware(max_retries=3, backoff_factor=1.0))

    # 2. 工具调用重试 — 工具偶发失败时自动重试（2 次，1s → 2s）
    extra.append(ToolRetryMiddleware(max_retries=2, backoff_factor=1.0))

    # 3. 模型调用次数限制 — 防止 agent 无限循环
    #    chat: 50 轮（交互式对话足够）
    #    patrol: 100 轮（巡检需要调多个工具 + 分析）
    run_limit = 100 if purpose == "patrol" else 50
    extra.append(ModelCallLimitMiddleware(run_limit=run_limit))

    # 4. 上下文编辑 — 超 60K token 时清理旧工具输出（保留最近 5 个）
    #    与 SummarizationMiddleware 互补：ContextEditing 清理工具输出，
    #    Summarization 压缩消息历史，先清理减轻 Summarization 压力
    extra.append(
        ContextEditingMiddleware(
            edits=[ClearToolUsesEdit(trigger=60_000, keep=5)],
        )
    )

    # 5. 模型降级 — chat 模式且主备不同时，失败自动切换备用模型
    if purpose == "chat":
        fallback_model = settings.agent_patrol_model
        if fallback_model != settings.agent_default_model:
            try:
                fallback = get_chat_model("patrol")
                extra.append(ModelFallbackMiddleware(fallback))
                logger.info("ModelFallback: 备用模型 %s", fallback_model)
            except Exception as e:
                logger.warning("ModelFallback 配置失败: %s", e)

    return extra


async def _get_store() -> AsyncSqliteStore:
    """获取或创建 AsyncSqliteStore 单例 — 结构化长期存储"""
    global _store
    if _store is None:
        store_path = str(Path(settings.db_path).parent / "agent-store.db")
        Path(store_path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(store_path)
        _store = AsyncSqliteStore(conn)
        logger.info("AsyncSqliteStore 已创建: %s", store_path)
    return _store


async def build_agent(safety_mode: str = "supervised", purpose: str = "chat", user_role: str = "admin"):
    """构建 Deep Agent 实例

    Args:
        safety_mode: "supervised"(危险操作需审批) 或 "autonomous"(全自动)
        purpose: "chat"(对话) 或 "patrol"(巡检, 用便宜模型)
        user_role: "admin"(完全控制) 或 "user"(只读)
    """
    cache_key = f"{safety_mode}:{purpose}:{user_role}"
    if cache_key in _agent_cache:
        logger.debug("Agent cache hit: %s", cache_key)
        return _agent_cache[cache_key]

    model = get_chat_model(purpose)

    # 工具加载 — 核心工具始终绑定，领域工具延迟加载
    core_tools, deferred_tools_list = get_tools_split(user_role)

    if deferred_tools_list:
        registry = DeferredToolRegistry()
        for t in deferred_tools_list:
            registry.register(t)
        set_deferred_registry(registry)
        # tool_search 工具允许 agent 按需发现延迟工具
        tools = [*core_tools, tool_search]
        # 生成延迟工具描述注入提示词
        deferred_section = (
            "\n## 可用的延迟加载工具\n"
            "以下工具可通过 tool_search 按需加载（输入工具名或描述关键词）：\n"
            + registry.get_deferred_tool_descriptions()
        )
        logger.info(
            "延迟工具加载: core=%d, deferred=%d",
            len(core_tools),
            len(deferred_tools_list),
        )
    else:
        tools = core_tools
        deferred_section = ""

    interrupt_config = build_interrupt_config(safety_mode, user_role)
    backend = _create_backend()
    extra_middleware = _build_extra_middleware(purpose)

    # 普通用户：不提供子智能体和结构化存储
    if user_role != "admin":
        subagents = []
        store = None
    else:
        subagents = load_subagents()
        # 异步 SubAgent — 框架按 graph_id 自动路由到 AsyncSubAgentMiddleware
        try:
            from modules.agents.subagents import load_async_subagent_specs

            async_specs = load_async_subagent_specs()
            subagents = subagents + async_specs
        except Exception as e:
            logger.warning("异步 SubAgent 配置加载失败 (非致命): %s", e)
        store = await _get_store()

    # Checkpoint — 短期记忆（per-conversation state 持久化）
    checkpoint_path = settings.agent_checkpoint_db
    Path(checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    checkpointer = AsyncSqliteSaver(await aiosqlite.connect(checkpoint_path))

    # Memory — 核心身份 + 长期记忆
    data_dir = Path(settings.db_path).parent
    memory_paths = []
    core_memory = data_dir / "agents-core.md"
    if core_memory.exists():
        memory_paths.append(str(core_memory))
    memory_path = get_memory_path()
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    if memory_path.exists():
        memory_paths.append(str(memory_path))

    # Skills — 按需加载的专业工作流
    skills_dir = data_dir / "skills"
    skills_paths = [str(skills_dir)] if skills_dir.is_dir() else []

    system_prompt = get_system_prompt(safety_mode, user_role)
    # 注入延迟工具列表到系统提示词
    if deferred_section:
        system_prompt = system_prompt + "\n" + deferred_section

    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        interrupt_on=interrupt_config if interrupt_config else None,
        checkpointer=checkpointer,
        backend=backend,
        subagents=subagents,
        middleware=extra_middleware,
        memory=memory_paths if memory_paths else None,
        skills=skills_paths if skills_paths else None,
        store=store,
    )

    mw_names = [type(m).__name__ for m in extra_middleware]
    _agent_cache[cache_key] = agent
    logger.info(
        f"Deep Agent 已创建: mode={safety_mode}, purpose={purpose}, role={user_role}, "
        f"middleware={mw_names}, memory={[Path(p).name for p in memory_paths]}, "
        f"skills={len(skills_paths)} dirs, store={'AsyncSqliteStore' if store else 'None'}"
    )
    return agent


def reset_agent_cache():
    """重置 agent 缓存（模型切换后调用）"""
    global _agent_cache
    _agent_cache.clear()
    logger.info("Agent cache cleared")

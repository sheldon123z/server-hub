"""Deep Agent 工厂 — 基于 deepagents 框架构建运维智能体

Middleware 栈 (13 个):
  框架自动注入: TodoList, Filesystem, SubAgent, Summarization, PatchToolCalls,
                AnthropicPromptCaching, HumanInTheLoop, Memory
  手动注入:     LoopDetection, ModelRetry, ToolRetry, ModelCallLimit, ContextEditing,
                [ModelFallback]

记忆系统:
  短期: AsyncSqliteSaver checkpoint（per-conversation state 持久化）
  长期全局: data/agent-memory.md（MemoryMiddleware 注入系统提示词，管理员维护的运维知识）
  长期用户: data/agent-memory-{user_id}.md（按用户隔离，防止多用户记忆污染）
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
from modules.agents.memory.injection import format_memory_for_prompt
from modules.agents.memory.storage import MemoryStorage
from modules.agents.prompts import get_system_prompt
from modules.agents.safety import build_interrupt_config
from modules.agents.sandbox import SafeLocalShellBackend
from modules.agents.subagents import load_subagents
from modules.agents.tools import get_tools_split

logger = logging.getLogger(__name__)

# 单例
_agent_cache: dict = {}
_store: AsyncSqliteStore | None = None


def get_memory_path() -> Path:
    """全局运行时长期记忆文件路径。与仓库根 AGENTS.md 分离。"""
    return Path(settings.db_path).parent / "agent-memory.md"


def get_user_memory_path(user_id: str) -> Path:
    """用户专属长期记忆文件路径。

    Args:
        user_id: 用户标识（username）

    Returns:
        Path to data/agent-memory-{user_id}.md
    """
    return Path(settings.db_path).parent / f"agent-memory-{user_id}.md"


def load_user_memory_context(user_id: str) -> str:
    """加载用户专属记忆，格式化为可注入的系统消息。

    Args:
        user_id: 用户标识（username）

    Returns:
        格式化的用户记忆文本，为空时返回空字符串
    """
    if not user_id:
        return ""
    user_mem_path = get_user_memory_path(user_id)
    if not user_mem_path.exists():
        return ""
    try:
        content = user_mem_path.read_text(encoding="utf-8").strip()
        if not content:
            return ""
        return (
            f"## 个人记忆（用户: {user_id}）\n"
            f"以下是你与当前用户的历史交互记忆，请结合这些信息提供个性化服务。\n\n"
            f"{content}\n\n"
            f"**注意**: 当你通过 edit_file 更新记忆时，请写入用户专属文件 "
            f"`{user_mem_path}` 而非全局记忆文件。"
        )
    except Exception as e:
        logger.warning("加载用户记忆失败 (user=%s): %s", user_id, e)
        return ""


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


async def _get_skill_sources(user: dict | None, data_dir: Path) -> list[str]:
    """按用户身份返回技能目录列表。

    Args:
        user: 当前用户信息 dict（含 username），为 None 时仅返回系统+共享目录
        data_dir: data/ 目录路径

    Returns:
        技能目录路径列表
    """
    skills_dir = data_dir / "skills"
    sources: list[str] = []

    # 系统内置技能
    system_dir = skills_dir / "system"
    if system_dir.is_dir():
        sources.append(str(system_dir))

    # 共享已安装技能
    installed_dir = skills_dir / "installed"
    if installed_dir.is_dir():
        sources.append(str(installed_dir))

    # 兜底：如果 system/installed 都不存在，回退到 skills 根目录
    if not sources and skills_dir.is_dir():
        sources.append(str(skills_dir))

    # 用户私有技能
    if user:
        username = user.get("username", "")
        if username:
            user_skills = skills_dir / "users" / username
            if user_skills.is_dir():
                sources.append(str(user_skills))

    return sources


async def build_agent(
    safety_mode: str = "supervised",
    purpose: str = "chat",
    user_role: str = "admin",
    user: dict | None = None,
):
    """构建 Deep Agent 实例

    Args:
        safety_mode: "supervised"(危险操作需审批) 或 "autonomous"(全自动)
        purpose: "chat"(对话) 或 "patrol"(巡检, 用便宜模型)
        user_role: "admin"(完全控制) 或 "user"(只读)
        user: 当前用户信息（含 username），用于加载用户私有技能
    """
    username = user.get("username", "") if user else ""
    cache_key = f"{safety_mode}:{purpose}:{user_role}:{username}"
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

    # Skills — 按需加载的专业工作流（按用户身份动态获取目录列表）
    skills_paths = await _get_skill_sources(user, data_dir)

    system_prompt = get_system_prompt(safety_mode, user_role)
    # 注入延迟工具列表到系统提示词
    if deferred_section:
        system_prompt = system_prompt + "\n" + deferred_section

    # Smart Memory — LLM-powered 结构化记忆注入
    smart_memory_dir = data_dir / "smart-memory"
    smart_memory_storage = MemoryStorage(smart_memory_dir)
    memory_context = format_memory_for_prompt(smart_memory_storage.load(), token_budget=2000)
    if memory_context:
        system_prompt = system_prompt + "\n" + memory_context

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

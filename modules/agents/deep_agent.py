"""Deep Agent 工厂 — 基于 deepagents 框架构建运维智能体

替代旧的 graph.py (自定义 StateGraph)，使用 create_deep_agent 获得：
- 持久化 Shell 会话 (execute) — 通过 LocalShellBackend 实现
- 文件系统操作 (read_file/write_file/edit_file/ls/glob/grep)
- 任务规划 (write_todos)
- 子智能体委派 (task)
- 人工审批 (interrupt_on)
"""

import logging
import os
import aiosqlite
from pathlib import Path

from deepagents import create_deep_agent
from modules.agents.sandbox import SafeLocalShellBackend, SANDBOX_DIR
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from config import settings
from modules.agents.llm import get_chat_model
from modules.agents.tools import get_server_tools
from modules.agents.safety import build_interrupt_config
from modules.agents.prompts import SYSTEM_PROMPT
from modules.agents.subagents import get_subagents

logger = logging.getLogger(__name__)

# 单例
_agent_cache: dict = {}


def _create_backend() -> SafeLocalShellBackend:
    """创建 SafeLocalShellBackend — 安全增强的 Shell 执行 + 文件系统能力

    基于 Deep Agents 的 LocalShellBackend，增加：
    - 敏感环境变量剥离（API Key 不泄露到 execute 子进程）
    - 沙箱代码执行时自动 ulimit 资源限制
    - 固定临时代码目录 /tmp/serverhub-sandbox/
    """
    return SafeLocalShellBackend(
        root_dir=os.path.expanduser("~"),  # 以用户主目录为工作根目录
        virtual_mode=False,  # 允许访问任意路径（通过 interrupt_on 控制安全）
        timeout=120,  # Shell 命令超时 120 秒
        max_output_bytes=200_000,  # 最大输出 200KB
        inherit_env=True,  # 继承环境变量（PATH, conda 等）
    )


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
    )

    _agent_cache[cache_key] = agent
    logger.info(f"Deep Agent 已创建: mode={safety_mode}, purpose={purpose}, backend=LocalShellBackend")
    return agent


def reset_agent_cache():
    """重置 agent 缓存（模型切换后调用）"""
    global _agent_cache
    _agent_cache.clear()
    logger.info("Agent cache cleared")

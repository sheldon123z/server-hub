"""团队工具安全层 — 工具解析 + 危险工具日志包装

团队成员直接通过 create_react_agent 执行，不经过 Deep Agents 的
SafeLocalShellBackend，因此需要独立的安全包装。

安全机制:
1. execute 类工具调用前检查 Shell 黑名单 (check_shell_command)
2. supervised 模式下 DANGER 工具阻止执行并记录审批请求
3. 剥离敏感环境变量 (*API_KEY*/*SECRET*/*TOKEN*)，防止泄露到子进程
"""

import logging
import os
import re
from copy import deepcopy

from langchain_core.tools import BaseTool, StructuredTool

from modules.agents.safety import TOOL_RISK_MAP, RiskLevel, check_shell_command

logger = logging.getLogger(__name__)

# 需要检查 Shell 命令安全性的工具名 (execute 类)
_EXECUTE_TOOLS = {"execute", "execute_ops_script", "ssh_execute_command", "docker_container_exec"}

# 敏感环境变量模式 — 与 sandbox.py 保持一致
_SENSITIVE_ENV_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r".*API_KEY.*", r".*SECRET.*", r".*TOKEN.*", r".*PASSWORD.*",
        r"OPENROUTER_.*", r"VOLCENGINE_.*", r"ZHIPU_.*", r"MOONSHOT_.*",
        r"MINIMAX_.*", r"DEEPSEEK_.*", r"OPENAI_.*", r"TAVILY_.*",
        r"SERVERHUB_SECRET.*", r"SERVERHUB_ADMIN_PASSWORD",
    ]
]


def _strip_sensitive_env() -> dict[str, str]:
    """从当前环境变量中剥离敏感信息，返回安全的环境副本"""
    safe = {}
    for key, value in os.environ.items():
        if any(p.match(key) for p in _SENSITIVE_ENV_PATTERNS):
            continue
        safe[key] = value
    return safe


def resolve_tools(tool_names: list[str], user_role: str = "admin") -> list[BaseTool]:
    """从工具名列表解析为实际 Tool 对象

    优先从主工具集 (get_server_tools) 查找，未命中则查找 SubAgent 工具注册表。
    未找到的工具名会记录警告并跳过。

    Args:
        tool_names: 工具名字符串列表，如 ["get_system_overview", "web_search"]
        user_role: 用户角色，影响主工具集的过滤策略
    """
    from modules.agents.tools import get_server_tools
    from modules.agents.subagents._tools import TOOL_REGISTRY

    # 构建名称到工具的映射
    all_tools: dict[str, BaseTool] = {t.name: t for t in get_server_tools(user_role)}
    all_tools.update(TOOL_REGISTRY)

    resolved: list[BaseTool] = []
    for name in tool_names:
        if name in all_tools:
            resolved.append(all_tools[name])
        else:
            logger.warning("工具 '%s' 未找到，跳过", name)
    return resolved


def wrap_tools_for_team(
    tools: list[BaseTool],
    safety_mode: str,
    member_name: str,
) -> list[BaseTool]:
    """为团队成员的工具添加安全层

    supervised 模式下，DANGER 级别工具会被包装以记录审计日志。
    所有 MODERATE 级别工具也会添加调用日志（不阻止执行）。

    Args:
        tools: 原始工具列表
        safety_mode: "supervised" 或 "autonomous"
        member_name: 成员名称，用于日志标识
    """
    wrapped: list[BaseTool] = []
    for tool in tools:
        risk = TOOL_RISK_MAP.get(tool.name, RiskLevel.SAFE)

        if risk == RiskLevel.DANGER:
            # DANGER 工具始终包装（supervised 模式下会阻止执行）
            wrapped.append(_make_logged_tool(tool, member_name, risk, safety_mode))
        elif risk == RiskLevel.MODERATE:
            wrapped.append(_make_logged_tool(tool, member_name, risk, safety_mode))
        elif tool.name in _EXECUTE_TOOLS:
            # execute 类工具即使标记为 SAFE 也需要 Shell 黑名单检查
            wrapped.append(_make_logged_tool(tool, member_name, risk, safety_mode))
        else:
            wrapped.append(tool)
    return wrapped


def _make_logged_tool(
    original: BaseTool,
    member_name: str,
    risk: RiskLevel,
    safety_mode: str = "supervised",
) -> BaseTool:
    """包装工具：执行前记录审计日志 + 安全检查，保持 name/description/schema 不变

    安全检查:
    1. execute 类工具 — 调用 check_shell_command() 检查黑名单
    2. DANGER 级别 + supervised 模式 — 阻止执行，返回审批提示
    3. 所有调用剥离敏感环境变量
    """

    original_func = original.func
    original_coroutine = original.coroutine
    tool_name = original.name

    def _pre_check(kwargs: dict) -> str | None:
        """执行前安全检查，返回 None 表示放行，返回字符串表示拦截原因"""
        # 1. execute 类工具：检查 Shell 黑名单
        if tool_name in _EXECUTE_TOOLS:
            command = kwargs.get("command", "") or kwargs.get("cmd", "") or str(kwargs)
            is_safe, reason = check_shell_command(command)
            if not is_safe:
                logger.warning(
                    "[Team/BLOCKED] %s 的 %s 被黑名单拦截: %s",
                    member_name, tool_name, reason,
                )
                return f"安全拦截: {reason}"

        # 2. DANGER 级别 + supervised 模式：阻止执行
        if risk == RiskLevel.DANGER and safety_mode == "supervised":
            logger.warning(
                "[Team/BLOCKED] %s 的 %s (DANGER) 在 supervised 模式下被阻止，需管理员审批",
                member_name, tool_name,
            )
            return f"操作被阻止: {tool_name} 为高危工具，需管理员在 supervised 模式下审批后方可执行"

        return None

    async def async_wrapper(*args, **kwargs):
        logger.info(
            "[Team] %s 调用 %s (risk=%s) args=%s",
            member_name, tool_name, risk.value, kwargs,
        )
        # 安全检查
        block_reason = _pre_check(kwargs)
        if block_reason:
            return block_reason

        # 剥离敏感环境变量（通过临时替换 os.environ）
        original_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ.update(_strip_sensitive_env())
            if original_coroutine is not None:
                return await original_coroutine(*args, **kwargs)
            if original_func is not None:
                return original_func(*args, **kwargs)
            return await original.ainvoke(*args, **kwargs)
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    def sync_wrapper(*args, **kwargs):
        logger.info(
            "[Team] %s 调用 %s (risk=%s) args=%s",
            member_name, tool_name, risk.value, kwargs,
        )
        # 安全检查
        block_reason = _pre_check(kwargs)
        if block_reason:
            return block_reason

        # 剥离敏感环境变量
        original_env = os.environ.copy()
        try:
            os.environ.clear()
            os.environ.update(_strip_sensitive_env())
            if original_func is not None:
                return original_func(*args, **kwargs)
            return original.invoke(*args, **kwargs)
        finally:
            os.environ.clear()
            os.environ.update(original_env)

    return StructuredTool(
        name=original.name,
        description=original.description,
        args_schema=original.args_schema,
        func=sync_wrapper,
        coroutine=async_wrapper,
        return_direct=getattr(original, "return_direct", False),
    )

"""团队工具安全层 — 工具解析 + 危险工具日志包装

团队成员直接通过 create_react_agent 执行，不经过 Deep Agents 的
SafeLocalShellBackend，因此需要独立的安全包装。
"""

import logging
from copy import deepcopy

from langchain_core.tools import BaseTool, StructuredTool

from modules.agents.safety import TOOL_RISK_MAP, RiskLevel

logger = logging.getLogger(__name__)


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

        if safety_mode == "supervised" and risk == RiskLevel.DANGER:
            wrapped.append(_make_logged_tool(tool, member_name, risk))
        elif risk == RiskLevel.MODERATE:
            wrapped.append(_make_logged_tool(tool, member_name, risk))
        else:
            wrapped.append(tool)
    return wrapped


def _make_logged_tool(
    original: BaseTool,
    member_name: str,
    risk: RiskLevel,
) -> BaseTool:
    """包装工具：执行前记录审计日志，保持 name/description/schema 不变"""

    original_func = original.func
    original_coroutine = original.coroutine

    async def async_wrapper(*args, **kwargs):
        logger.info(
            "[Team] %s 调用 %s (risk=%s) args=%s",
            member_name, original.name, risk.value, kwargs,
        )
        if original_coroutine is not None:
            return await original_coroutine(*args, **kwargs)
        # 回退到同步调用
        if original_func is not None:
            return original_func(*args, **kwargs)
        return await original.ainvoke(*args, **kwargs)

    def sync_wrapper(*args, **kwargs):
        logger.info(
            "[Team] %s 调用 %s (risk=%s) args=%s",
            member_name, original.name, risk.value, kwargs,
        )
        if original_func is not None:
            return original_func(*args, **kwargs)
        return original.invoke(*args, **kwargs)

    return StructuredTool(
        name=original.name,
        description=original.description,
        args_schema=original.args_schema,
        func=sync_wrapper,
        coroutine=async_wrapper,
        return_direct=getattr(original, "return_direct", False),
    )

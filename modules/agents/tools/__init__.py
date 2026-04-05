"""运维工具集 — 通过 @register_tool 自动注册到全局注册表"""

import importlib
import logging

logger = logging.getLogger(__name__)

# 所有工具子模块（导入即触发 @register_tool 注册）
_TOOL_MODULES = [
    "modules.agents.tools.alerts",
    "modules.agents.tools.assets",
    "modules.agents.tools.clarification",
    "modules.agents.tools.cron",
    "modules.agents.tools.docker",
    "modules.agents.tools.knowledge",
    "modules.agents.tools.notifications",
    "modules.agents.tools.page_context_tool",
    "modules.agents.tools.playbook",
    "modules.agents.tools.scripts",
    "modules.agents.tools.security",
    "modules.agents.tools.servers",
    "modules.agents.tools.services",
    "modules.agents.tools.system",
    "modules.agents.tools.ui_tools",
    "modules.agents.tools.users",
]

_tools_loaded = False


def _ensure_tools_loaded() -> None:
    """确保所有工具子模块已导入（触发 @register_tool 注册）。"""
    global _tools_loaded
    if _tools_loaded:
        return
    for mod_name in _TOOL_MODULES:
        try:
            importlib.import_module(mod_name)
        except Exception:
            logger.warning("工具模块 %s 导入失败", mod_name, exc_info=True)
    _tools_loaded = True


def get_server_tools(user_role: str = "admin") -> list:
    """返回服务器管理工具列表

    Args:
        user_role: "admin" 返回全部工具，"user" 只返回只读安全工具
    """
    _ensure_tools_loaded()

    from modules.agents.tools.registry import RiskLevel, get_registered_tools

    all_tools = [meta.tool for meta in get_registered_tools().values()]

    if user_role == "admin":
        return all_tools

    # 普通用户：只返回 SAFE 级别工具
    excluded = {"send_notification", "save_fault_case"}
    return [
        meta.tool
        for meta in get_registered_tools().values()
        if meta.risk == RiskLevel.SAFE and meta.tool.name not in excluded
    ]


async def get_server_tools_for_user(user_id: str, fallback_role: str = "user") -> list:
    """基于 RBAC 权限为指定用户返回可用工具列表。

    检查 has_permission("*", "*") 判断是否拥有完整管理权限；
    RBAC 不可用时降级使用 fallback_role。
    """
    try:
        from modules.rbac.services import has_permission as _has_perm

        effective_role = "admin" if await _has_perm(user_id, "*", "*") else fallback_role
    except Exception:
        logger.debug("RBAC 不可用，工具列表使用 fallback_role=%s", fallback_role, exc_info=True)
        effective_role = fallback_role
    return get_server_tools(effective_role)


# 向后兼容
get_all_tools = get_server_tools


def get_tools_split(user_role: str = "admin") -> tuple[list, list]:
    """返回 (core_tools, deferred_tools) 分组

    core_tools: 始终绑定到 LLM 的高频工具
    deferred_tools: 按需通过 tool_search 加载的领域工具
    """
    from modules.agents.deferred_tools import CORE_TOOL_NAMES

    all_tools = get_server_tools(user_role)
    core = [t for t in all_tools if t.name in CORE_TOOL_NAMES]
    deferred = [t for t in all_tools if t.name not in CORE_TOOL_NAMES]
    return core, deferred

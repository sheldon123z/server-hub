"""延迟工具加载 -- 核心工具始终绑定，领域工具按需发现

参考 DeerFlow DeferredToolRegistry + tool_search:
- 核心工具 (~15) 始终发送给 LLM
- 领域工具 (~35) 注册到 Registry，LLM 通过 tool_search 按需加载
"""

import logging
import re
from contextvars import ContextVar

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 核心工具: 最常用的，始终绑定到 LLM
CORE_TOOL_NAMES = {
    # 系统监控 (最高频)
    "get_system_overview",
    "get_disk_info",
    "analyze_resource_trend",
    # Docker 常用
    "list_docker_containers",
    "get_container_logs",
    # 服务常用
    "list_systemd_services",
    "get_service_logs",
    # 用户常用
    "get_user_resources",
    # 知识库
    "retrieve_knowledge",
    # UI 渲染
    "render_chart",
    "render_table",
    # 页面上下文
    "get_page_data",
    # 服务器管理
    "server_list",
}


class DeferredToolRegistry:
    """延迟工具注册表 -- 存储工具元数据，按需返回完整 schema"""

    def __init__(self):
        self._tools: dict[str, object] = {}  # name -> BaseTool

    def register(self, tool_obj) -> None:
        self._tools[tool_obj.name] = tool_obj

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def search(self, query: str) -> list:
        """搜索延迟工具

        支持三种查询模式:
        - "select:name1,name2" -- 精确选择
        - "+keyword rest" -- 名称必须含 keyword
        - "keyword" -- 模糊匹配 name + description
        """
        if query.startswith("select:"):
            names = {n.strip() for n in query[7:].split(",")}
            return [t for n, t in self._tools.items() if n in names]

        if query.startswith("+"):
            parts = query[1:].split(None, 1)
            keyword = parts[0] if parts else ""
            return [t for n, t in self._tools.items() if keyword.lower() in n.lower()]

        # Fuzzy: match against name + description
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []
        for name, t in self._tools.items():
            desc = getattr(t, "description", "") or ""
            if pattern.search(name) or pattern.search(desc):
                results.append(t)
        return results[:10]  # Max 10 results

    def promote(self, names: set[str]) -> None:
        """将工具从延迟注册表中移除 (已被发现后不再需要延迟加载)"""
        for name in names:
            self._tools.pop(name, None)

    def get_deferred_tool_descriptions(self) -> str:
        """生成延迟工具列表文本 (用于系统提示词)"""
        if not self._tools:
            return ""
        lines = []
        for name, t in self._tools.items():
            desc = getattr(t, "description", "") or ""
            # Take first sentence
            short_desc = desc.split("\u3002")[0].split("\n")[0][:60]
            lines.append(f"- {name}: {short_desc}")
        return "\n".join(lines)


# ContextVar for per-request isolation
_registry_var: ContextVar[DeferredToolRegistry | None] = ContextVar("deferred_registry", default=None)


def get_deferred_registry() -> DeferredToolRegistry | None:
    return _registry_var.get()


def set_deferred_registry(registry: DeferredToolRegistry) -> None:
    _registry_var.set(registry)


def reset_deferred_registry() -> None:
    _registry_var.set(None)


@tool
def tool_search(query: str) -> str:
    """搜索并加载可用的运维工具。当你需要使用某个工具但当前未加载时，调用此工具发现它。

    支持的查询格式:
    - "select:tool_name1,tool_name2" -- 按名称精确加载
    - "+docker" -- 搜索名称包含 docker 的工具
    - "清理资源" -- 模糊搜索工具描述

    Args:
        query: 搜索查询字符串
    """
    registry = get_deferred_registry()
    if registry is None:
        return "延迟工具注册表未初始化。所有工具已直接可用。"

    matched = registry.search(query)
    if not matched:
        available = registry.get_tool_names()
        return f"未找到匹配的工具。可用的延迟工具: {', '.join(available[:20])}"

    # Format results with tool schema info
    results = []
    for t in matched:
        schema = getattr(t, "args_schema", None)
        if schema:
            try:
                schema_info = str(schema.schema())
            except Exception:
                schema_info = "schema unavailable"
        else:
            schema_info = "no schema"
        results.append(f"\u2705 {t.name}: {getattr(t, 'description', '')[:200]}\n   \u53c2\u6570: {schema_info}")

    # Promote discovered tools
    registry.promote({t.name for t in matched})

    return f"\u5df2\u53d1\u73b0 {len(matched)} \u4e2a\u5de5\u5177:\n\n" + "\n\n".join(results)

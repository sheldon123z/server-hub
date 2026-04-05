"""工具注册中心 — 统一管理工具元数据与自动注册

通过 @register_tool 装饰器声明工具时携带元数据（风险等级、分组、图标)，
工具自动注册到全局注册表,无需手动维护工具列表。

用法:
    from modules.agents.tools.registry import register_tool, RiskLevel

    @register_tool(risk=RiskLevel.DANGER, group="docker:write", icon="Trash2")
    async def docker_prune(...): ...
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from langchain_core.tools import StructuredTool


class RiskLevel(StrEnum):
    """工具风险等级"""

    SAFE = "safe"  # 只读、无副作用
    MODERATE = "moderate"  # 可逆操作、影响有限
    DANGER = "danger"  # 不可逆操作、高风险


@dataclass
class ToolMeta:
    """工具元数据"""

    tool: StructuredTool  # LangChain 工具实例
    risk: RiskLevel = RiskLevel.SAFE  # 风险等级
    group: str = "other"  # 工具分组 (如 docker:read, users:write, system)
    icon: str = "Wrench"  # Lucide 图标名
    label: str = ""  # 中文显示名(默认使用工具名)
    category: str = "其他"  # 前端分类展示


# 全局工具注册表：{tool_name: ToolMeta}
_TOOL_REGISTRY: dict[str, ToolMeta] = {}


def register_tool(
    risk: RiskLevel = RiskLevel.SAFE,
    group: str = "other",
    icon: str = "Wrench",
    label: str = "",
    category: str = "其他",
) -> Callable[[Callable], StructuredTool]:
    """装饰器：声明工具元数据并自动注册

    Args:
        risk: 风险等级 (safe/moderate/danger)
        group: 工具分组，格式为 "领域:操作类型" (如 docker:read, users:write)
        icon: Lucide 图标名 (https://lucide.dev/icons/)
        label: 中文显示名，默认使用工具名
        category: 前端分类展示用

    Returns:
        LangChain @tool 装饰后的工具

    Example:
        @register_tool(risk=RiskLevel.DANGER, group="docker:write", icon="Trash2")
        async def docker_prune(...): ...
    """

    def decorator(func: Callable) -> StructuredTool:
        from langchain_core.tools import tool as lc_tool

        # 应用 LangChain @tool 装饰器
        tool_instance = lc_tool(func)

        # 生成显示名
        display_label = label or _tool_name_to_label(tool_instance.name)

        # 创建元数据并注册
        meta = ToolMeta(
            tool=tool_instance,
            risk=risk,
            group=group,
            icon=icon,
            label=display_label,
            category=category,
        )
        _TOOL_REGISTRY[tool_instance.name] = meta

        return tool_instance

    return decorator


def _tool_name_to_label(name: str) -> str:
    """将工具名转换为中文显示标签"""
    # 常见词汇映射
    label_map = {
        "list": "列表",
        "get": "获取",
        "check": "检查",
        "validate": "验证",
        "create": "创建",
        "update": "更新",
        "modify": "修改",
        "delete": "删除",
        "toggle": "切换",
        "execute": "执行",
        "kill": "终止",
        "send": "发送",
        "save": "保存",
        "search": "搜索",
        "retrieve": "检索",
        "reindex": "重建索引",
        "analyze": "分析",
        "acknowledge": "确认",
        "auto_fix": "自动修复",
        "render": "渲染",
        "test": "测试",
        "prune": "清理",
        "manage": "管理",
        "docker": "Docker",
        "container": "容器",
        "compose": "Compose",
        "network": "网络",
        "service": "服务",
        "systemd": "Systemd",
        "user": "用户",
        "quota": "配额",
        "process": "进程",
        "cron": "定时任务",
        "job": "任务",
        "log": "日志",
        "disk": "磁盘",
        "resource": "资源",
        "trend": "趋势",
        "compliance": "合规",
        "alert": "告警",
        "notification": "通知",
        "knowledge": "知识",
        "fault": "故障",
        "case": "案例",
        "asset": "资产",
        "topology": "拓扑",
        "inventory": "清单",
        "page": "页面",
        "data": "数据",
        "playbook": "剧本",
        "ssh": "SSH",
        "server": "服务器",
        "connectivity": "连通",
        "chart": "图表",
        "table": "表格",
        "form": "表单",
        "card": "卡片",
        "single": "单个",
        "full": "完整",
        "active": "活跃",
        "login": "登录",
        "history": "历史",
        "session": "会话",
        "violation": "违规",
        "overview": "概览",
        "info": "信息",
        "action": "操作",
        "control": "控制",
        "enable": "启用",
        "disable": "禁用",
        "dependencies": "依赖",
        "web": "网络",
        "content": "内容",
        "think": "思考",
    }

    # 分词并转换
    parts = name.replace("_tool", "").split("_")
    label_parts = []
    for part in parts:
        label_parts.append(label_map.get(part, part))
    return "".join(label_parts)


def get_registered_tools() -> dict[str, ToolMeta]:
    """获取所有已注册的工具及其元数据"""
    return _TOOL_REGISTRY.copy()


def get_tool_meta(tool_name: str) -> ToolMeta | None:
    """获取指定工具的元数据"""
    return _TOOL_REGISTRY.get(tool_name)


def get_tools_by_risk(risk: RiskLevel) -> list[StructuredTool]:
    """按风险等级获取工具"""
    return [meta.tool for meta in _TOOL_REGISTRY.values() if meta.risk == risk]


def get_tools_by_group(group_prefix: str) -> list[StructuredTool]:
    """按分组前缀获取工具(如 'docker' 匹配 'docker:read' 和 'docker:write')"""
    return [meta.tool for meta in _TOOL_REGISTRY.values() if meta.group.startswith(group_prefix)]


def build_tool_risk_map() -> dict[str, RiskLevel]:
    """从注册表构建工具风险映射表(用于 safety.py)"""
    return {name: meta.risk for name, meta in _TOOL_REGISTRY.items()}


def build_tool_display_map() -> dict[str, dict[str, str]]:
    """构建前端工具显示映射(用于 API 返回给前端)"""
    return {
        name: {
            "icon": meta.icon,
            "color": _risk_to_color(meta.risk),
            "label": meta.label,
            "category": meta.category,
            "risk": meta.risk.value,
            "group": meta.group,
        }
        for name, meta in _TOOL_REGISTRY.items()
    }


def _risk_to_color(risk: RiskLevel) -> str:
    """风险等级对应的 Tailwind 颜色"""
    colors = {
        RiskLevel.SAFE: "text-green-400",
        RiskLevel.MODERATE: "text-yellow-400",
        RiskLevel.DANGER: "text-red-400",
    }
    return colors.get(risk, "text-text3")

"""SubAgent 定义 — 专业化子智能体

遵循 LangChain 官方 SubAgent 规范 (https://docs.langchain.com/oss/python/deepagents/subagents):
- name/description/system_prompt/tools 四个 Required 字段必须显式指定
- tools 保持 minimal 集合
- system_prompt 包含输出格式和长度限制
- description 具体且 action-oriented
"""

import json
import logging
import os
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ─── SubAgent 专属工具 ───

_tavily_client = None


def _get_tavily_client():
    global _tavily_client
    if _tavily_client is None:
        api_key = os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            return None
        from tavily import TavilyClient
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


@tool
def web_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
) -> str:
    """Search the web for up-to-date information on any topic."""
    client = _get_tavily_client()
    if client is None:
        return "Error: TAVILY_API_KEY not configured"
    try:
        results = client.search(
            query=query,
            search_depth="advanced",
            max_results=min(max_results, 10),
            topic=topic,
            include_answer=True,
        )
    except Exception as e:
        return f"Search failed: {e}"

    output = f"Search: {query}\n"
    if results.get("answer"):
        output += f"\nSummary: {results['answer']}\n"
    for i, r in enumerate(results.get("results", []), 1):
        content = r.get("content", "")[:300]
        output += f"\n[{i}] {r.get('title', 'Untitled')}\n    URL: {r.get('url', '')}\n    {content}\n"
    return output


@tool
def think(thought: str) -> str:
    """Pause and reflect on research progress before deciding next steps."""
    return f"Reflected: {thought}"


# ─── 需要从主 agent 工具集中引用的工具 ───

def _get_tools_by_names(names: list[str]) -> list:
    """从主 agent 的工具集中按名称提取工具对象"""
    from modules.agents.tools import get_server_tools
    server_tools = {t.name: t for t in get_server_tools()}
    result = []
    for name in names:
        if name in server_tools:
            result.append(server_tools[name])
        elif name in TOOL_REGISTRY:
            result.append(TOOL_REGISTRY[name])
    return result


# ─── SubAgent 定义 ───

def get_subagents() -> list[dict]:
    """返回所有 SubAgent 配置"""
    return [
        # 1. 联网研究员
        {
            "name": "researcher",
            "description": "Conducts web research to find technical documentation and error solutions.",
            "system_prompt": (
                "你是一个专业的互联网研究员，使用中文回复。\n\n"
                "工作流程：\n"
                "1. 使用 web_search 搜索相关信息\n"
                "2. 使用 think 评估是否继续\n"
                "3. 综合给出报告，标注 [1][2] 来源\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": [web_search, think],
        },
        # 2. 日志分析师
        {
            "name": "log-analyzer",
            "description": "Analyzes service logs and system logs to diagnose crashes and error patterns.",
            "system_prompt": (
                "你是一个专业的日志分析师，使用中文回复。\n\n"
                "可用工具：execute, read_file, grep, get_container_logs, get_service_logs\n\n"
                "工作流程：定位日志 -> 提取错误 -> 分析模式 -> 给出方案\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": _get_tools_by_names(["get_container_logs", "get_service_logs"]),
        },
        # 3. 安全审计员
        {
            "name": "security-auditor",
            "description": "Audits server security configuration (SSH, ports, users, firewall).",
            "system_prompt": (
                "你是一个服务器安全审计专家，使用中文回复。\n\n"
                "审计范围：SSH、端口、用户权限、防火墙、文件权限。\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": _get_tools_by_names(["get_system_overview"]),
        },
        # 4. 多源关联分析
        {
            "name": "correlation-analyzer",
            "description": "Cross-dimensional correlation analysis of metrics, logs, and historical cases.",
            "system_prompt": (
                "你是多源关联分析专家，使用中文回复。跨维度关联多种数据源找出根因。\n\n"
                "工作流程：资源趋势 -> 系统状态 -> 容器状态 -> 容器日志 -> 历史案例 -> 综合分析\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": _get_tools_by_names([
                "analyze_resource_trend", "get_system_overview",
                "list_docker_containers", "get_container_logs",
                "list_systemd_services", "get_service_logs",
                "search_fault_cases", "get_user_login_history_tool",
                "get_active_sessions_tool", "list_docker_networks",
                "get_service_dependencies_tool",
            ]),
        },
        # 5. 定时任务调度专家
        {
            "name": "ops-scheduler",
            "description": "Manages cron scheduled tasks (create, modify, delete, toggle).",
            "system_prompt": (
                "你是定时任务管理专家，使用中文回复。\n\n"
                "工作流程：验证表达式 -> 检查冲突 -> 创建/修改任务 -> 提供摘要\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": _get_tools_by_names([
                "list_cron_jobs", "validate_cron_expr",
                "create_cron_job", "modify_cron_schedule",
                "delete_cron_job_tool", "toggle_cron_job_tool",
            ]),
        },
        # 6. 知识检索专家
        {
            "name": "knowledge-retriever",
            "description": "Deep knowledge retrieval specialist using semantic, keyword, and web search.",
            "system_prompt": (
                "你是知识检索专家，使用中文回复。\n\n"
                "工作流程：分析查询 -> 检索本地库 -> 搜索故障案例 -> 补充互联网搜索 -> 综合回答\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": _get_tools_by_names([
                "retrieve_knowledge", "search_fault_cases",
            ]) + [web_search, think],
        },
    ]


TOOL_REGISTRY = {
    "web_search": web_search,
    "think": think,
}


def _build_subagents_from_config(configs: list[dict]) -> list[dict]:
    result = []
    for cfg in configs:
        agent_def = {
            "name": cfg["name"],
            "description": cfg["description"],
            "system_prompt": cfg["system_prompt"],
        }
        tool_names = cfg.get("tools", [])
        if tool_names:
            agent_def["tools"] = _get_tools_by_names(tool_names)
        if cfg.get("model"):
            agent_def["model"] = cfg["model"]
        result.append(agent_def)
    return result


def load_subagents() -> list[dict]:
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    if custom_path.exists():
        try:
            configs = json.loads(custom_path.read_text(encoding="utf-8"))
            return _build_subagents_from_config(configs)
        except Exception as e:
            logger.warning(f"自定义 SubAgent 配置加载失败: {e}")
    return get_subagents()


def save_subagents_config(configs: list[dict]):
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    custom_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for cfg in configs:
        serializable.append({
            "name": cfg["name"],
            "description": cfg["description"],
            "system_prompt": cfg["system_prompt"],
            "tools": [t.name if hasattr(t, 'name') else str(t) for t in cfg.get("tools", [])],
            "model": cfg.get("model"),
        })
    custom_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def get_subagents_config() -> list[dict]:
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    if custom_path.exists():
        try:
            return json.loads(custom_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    defaults = get_subagents()
    return [
        {
            "name": d["name"],
            "description": d["description"],
            "system_prompt": d["system_prompt"],
            "tools": [t.name for t in d.get("tools", [])],
            "model": d.get("model"),
        }
        for d in defaults
    ]


def get_available_tools() -> list[dict]:
    from modules.agents.tools import get_server_tools
    from modules.agents.safety import TOOL_RISK_MAP
    tools = []
    for t in get_server_tools():
        tools.append({
            "name": t.name,
            "description": (t.description or "")[:100],
            "risk": TOOL_RISK_MAP.get(t.name, "safe"),
            "source": "custom",
        })
    for name, t in TOOL_REGISTRY.items():
        tools.append({"name": name, "description": (t.description or "")[:100], "risk": "safe", "source": "subagent"})
    builtins = [("execute","danger"),("read_file","safe"),("write_file","moderate"),
                ("edit_file","moderate"),("ls","safe"),("glob","safe"),("grep","safe")]
    for name, risk in builtins:
        tools.append({"name": name, "description": f"内置: {name}", "risk": risk, "source": "builtin"})
    return tools

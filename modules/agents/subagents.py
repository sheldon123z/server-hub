"""SubAgent 定义 — 专业化子智能体

遵循 LangChain 官方 SubAgent 规范 (https://docs.langchain.com/oss/python/deepagents/subagents):
- name/description/system_prompt/tools 四个 Required 字段必须显式指定
- tools 保持最小集合（"Keep this minimal and include only what's needed"）
- system_prompt 包含输出格式和长度限制（防止 context bloat）
- description 具体且 action-oriented（帮助主 agent 精准委派）
"""

import json
import logging
import os
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ─── SubAgent 专属工具 ───

# Tavily 客户端单例（避免每次调用创建新实例）
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
    """Search the web for up-to-date information on any topic.

    Args:
        query: Search query string
        max_results: Maximum number of results (1-10)
        topic: Search topic filter
    """
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
    """Pause and reflect on research progress before deciding next steps.

    Args:
        thought: Current assessment of gathered information and next actions
    """
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


# ─── SubAgent 定义（遵循官方规范）───

def get_subagents() -> list[dict]:
    """返回所有 SubAgent 配置（遵循 LangChain 官方 SubAgent 规范）

    每个 SubAgent 必须包含:
        name: str           — 唯一标识，主 agent 通过 task(subagent_type="name") 调用
        description: str    — action-oriented 描述，帮助主 agent 决定何时委派
        system_prompt: str  — 详细工作流指令 + 输出格式 + 长度限制
        tools: list         — 最小工具集（仅包含完成任务所需的工具）

    可选:
        model: str          — 覆盖模型 "provider:model"（默认继承主 agent）
    """
    return [
        # 1. 联网研究员 — 专属工具，不继承主 agent 工具
        {
            "name": "researcher",
            "description": (
                "Conducts web research to find technical documentation, error solutions, "
                "software version info, and best practices. Delegate ONE topic at a time."
            ),
            "system_prompt": (
                "你是一个专业的互联网研究员，使用中文回复。\n\n"
                "工作流程：\n"
                "1. 使用 web_search 搜索相关信息（2-3 次搜索即可，复杂问题最多 5 次）\n"
                "2. 每次搜索后用 think 工具评估是否需要继续搜索\n"
                "3. 综合所有搜索结果，给出结构化的中文报告\n"
                "4. 报告中使用 [1][2][3] 标注信息来源\n\n"
                "停止搜索的条件：已有 3+ 相关来源，或最近两次搜索结果相似。\n\n"
                "输出格式：\n"
                "- 结论摘要（2-3 句）\n"
                "- 详细发现（要点列表）\n"
                "- 来源列表（URL）\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": [web_search, think],
        },
        # 2. 日志分析师 — 最小工具集：仅日志相关
        {
            "name": "log-analyzer",
            "description": (
                "Analyzes service logs and system logs to diagnose crashes, identify error "
                "patterns, trace performance issues, and investigate security incidents."
            ),
            "system_prompt": (
                "你是一个专业的日志分析师，使用中文回复。\n\n"
                "可用工具：\n"
                "- execute: 运行 journalctl、docker logs、tail、awk 等命令\n"
                "- read_file: 直接读取日志文件\n"
                "- grep: 搜索日志中的关键词和模式\n"
                "- get_container_logs: 获取 Docker 容器日志\n"
                "- get_service_logs: 获取 systemd 服务日志\n\n"
                "工作流程：\n"
                "1. 定位相关日志文件或服务\n"
                "2. 使用 grep/execute 提取错误和异常条目\n"
                "3. 分析错误模式、时间线、频率\n"
                "4. 给出根因分析和修复建议\n\n"
                "输出格式：\n"
                "- 问题摘要（一句话）\n"
                "- 关键日志条目（带时间戳，最多 10 条）\n"
                "- 根因分析\n"
                "- 推荐解决方案（附具体命令）\n\n"
                "IMPORTANT: Do NOT include raw log dumps. Summarize findings concisely. "
                "Keep your response under 500 words."
            ),
            "tools": _get_tools_by_names([
                "get_container_logs", "get_service_logs",
            ]),
        },
        # 3. 安全审计员 — 最小工具集：仅安全相关
        {
            "name": "security-auditor",
            "description": (
                "Audits server security configuration including SSH settings, open ports, "
                "user permissions, firewall rules, and file permissions. Returns risk-graded findings."
            ),
            "system_prompt": (
                "你是一个服务器安全审计专家，使用中文回复。\n\n"
                "可用工具：\n"
                "- execute: 运行 ss、iptables、ufw、last 等安全检查命令\n"
                "- read_file: 读取配置文件（sshd_config, /etc/passwd 等）\n"
                "- grep: 搜索配置文件中的安全相关设置\n"
                "- get_system_overview: 获取系统基本信息\n\n"
                "审计范围：\n"
                "1. SSH 配置 — root 登录、密码认证、端口\n"
                "2. 开放端口 — ss -tlnp 检查不必要的监听端口\n"
                "3. 用户权限 — sudo 配置、/etc/passwd 异常用户\n"
                "4. 防火墙 — iptables/ufw 规则\n"
                "5. 文件权限 — /etc/shadow、SSH key 权限\n\n"
                "NEVER read: ~/.api_keys, ~/.telegram_config, ~/config.yaml\n\n"
                "输出格式（按风险分级）：\n"
                "- HIGH: 需要立即修复（附修复命令）\n"
                "- MEDIUM: 建议修复（附修复命令）\n"
                "- OK: 配置正常\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": _get_tools_by_names([
                "get_system_overview",
            ]),
        },
        # 4. 多源关联分析 — 跨维度关联系统指标/容器/日志/案例
        {
            "name": "correlation-analyzer",
            "description": (
                "Cross-dimensional correlation analysis. Correlates system metrics timeline, "
                "container status changes, log anomalies, and historical fault cases to identify "
                "root causes. Delegate when complex multi-component anomalies need investigation."
            ),
            "system_prompt": (
                "你是多源关联分析专家，使用中文回复。你的任务是跨维度关联多种数据源，找出问题的根本原因。\n\n"
                "工作流程：\n"
                "1. 调用 analyze_resource_trend 获取最近的资源趋势（CPU/内存/GPU/磁盘）\n"
                "2. 调用 get_system_overview 获取当前系统状态\n"
                "3. 调用 list_docker_containers 检查容器状态（重启/停止）\n"
                "4. 对异常容器调用 get_container_logs 查看日志\n"
                "5. 调用 search_fault_cases 搜索历史类似案例\n"
                "6. 综合分析时间线上的关联性\n\n"
                "关联分析要点：\n"
                "- 时间维度：异常事件发生的先后顺序\n"
                "- 因果维度：哪些事件可能导致了其他事件\n"
                "- 资源维度：资源变化与服务异常的关联\n"
                "- 历史维度：是否有类似的历史案例\n\n"
                "输出格式：\n"
                "- 时间线关联：按时间顺序列出各维度的异常事件\n"
                "- 关联推理：哪些事件可能有因果关系\n"
                "- 根因判断：最可能的根本原因\n"
                "- 建议：处置建议\n\n"
                "IMPORTANT: Keep your response under 500 words."
            ),
            "tools": _get_tools_by_names([
                "analyze_resource_trend", "get_system_overview",
                "list_docker_containers", "get_container_logs",
                "list_systemd_services", "get_service_logs",
                "search_fault_cases",
            ]),
        },
    ]


# ─── 工具注册表（name → tool 对象映射，供前端管理和 JSON 配置反序列化）───

TOOL_REGISTRY = {
    "web_search": web_search,
    "think": think,
}


def _build_subagents_from_config(configs: list[dict]) -> list[dict]:
    """从 JSON 配置构建 SubAgent 列表，将工具名称映射为实际工具对象"""
    result = []
    for cfg in configs:
        agent_def = {
            "name": cfg["name"],
            "description": cfg["description"],
            "system_prompt": cfg["system_prompt"],
        }
        # 映射工具名称到实际对象（从 server_tools + TOOL_REGISTRY 中查找）
        tool_names = cfg.get("tools", [])
        if tool_names:
            agent_def["tools"] = _get_tools_by_names(tool_names)
        # 不指定 tools 则继承主 agent 全部工具
        if cfg.get("model"):
            agent_def["model"] = cfg["model"]
        result.append(agent_def)
    return result


def load_subagents() -> list[dict]:
    """加载 SubAgent 配置 — 优先读取自定义 JSON，不存在则用硬编码默认"""
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    if custom_path.exists():
        try:
            configs = json.loads(custom_path.read_text(encoding="utf-8"))
            return _build_subagents_from_config(configs)
        except Exception as e:
            logger.warning(f"自定义 SubAgent 配置加载失败，使用默认: {e}")
    return get_subagents()


def save_subagents_config(configs: list[dict]):
    """保存 SubAgent 配置到 JSON（只存序列化字段，不存工具对象）"""
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    custom_path.parent.mkdir(parents=True, exist_ok=True)
    # 转换为可序列化格式
    serializable = []
    for cfg in configs:
        serializable.append({
            "name": cfg["name"],
            "description": cfg["description"],
            "system_prompt": cfg["system_prompt"],
            "tools": cfg.get("tools", []),
            "model": cfg.get("model"),
        })
    custom_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def get_subagents_config() -> list[dict]:
    """获取 SubAgent 配置（序列化格式，供 API 返回）"""
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    if custom_path.exists():
        try:
            return json.loads(custom_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 从硬编码默认值生成序列化格式
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
    """返回所有可用工具的元信息（供前端多选绑定）"""
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
    # SubAgent 专属工具
    for name, t in TOOL_REGISTRY.items():
        tools.append({
            "name": name,
            "description": (t.description or "")[:100],
            "risk": "safe",
            "source": "subagent",
        })
    # Deep Agents 内置
    builtins = [("execute","danger"),("read_file","safe"),("write_file","moderate"),
                ("edit_file","moderate"),("ls","safe"),("glob","safe"),("grep","safe")]
    for name, risk in builtins:
        tools.append({"name": name, "description": f"内置: {name}", "risk": risk, "source": "builtin"})
    return tools

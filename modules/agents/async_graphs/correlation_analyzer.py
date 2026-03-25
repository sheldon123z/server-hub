"""异步 Graph 定义 — 多源关联分析专家"""

from modules.agents.subagents.correlation_analyzer import PROMPT
from modules.agents.subagents._tools import _get_tools_by_names

SPEC = {
    "graph_id": "correlation-analyzer",
    "system_prompt": PROMPT,
    "model_purpose": "chat",
    "middleware_profile": "heavy",
    "call_limit": 35,
}


def get_tools():
    return _get_tools_by_names([
        "analyze_resource_trend", "get_system_overview",
        "list_docker_containers", "get_container_logs",
        "list_systemd_services", "get_service_logs",
        "search_fault_cases", "get_user_login_history_tool",
        "get_active_sessions_tool", "list_docker_networks",
        "get_service_dependencies_tool",
    ])

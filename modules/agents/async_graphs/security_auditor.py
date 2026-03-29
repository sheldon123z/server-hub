"""异步 Graph 定义 — 安全审计员"""

from modules.agents.subagents._tools import _get_tools_by_names
from modules.agents.subagents.security_auditor import PROMPT

SPEC = {
    "graph_id": "security-auditor",
    "system_prompt": PROMPT,
    "model_purpose": "patrol",
    "middleware_profile": "ops",
    "call_limit": 25,
}


def get_tools():
    return _get_tools_by_names(["get_system_overview", "check_compliance"])

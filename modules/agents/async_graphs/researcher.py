"""异步 Graph 定义 — 深度研究员"""

from modules.agents.subagents._shared_context import read_shared_findings, share_finding
from modules.agents.subagents._tools import fetch_webpage_content, think, web_search
from modules.agents.subagents.researcher import PROMPT

SPEC = {
    "graph_id": "researcher",
    "system_prompt": PROMPT,
    "model_purpose": "chat",
    "middleware_profile": "light",
    "call_limit": 25,
}


def get_tools():
    return [web_search, fetch_webpage_content, think, share_finding, read_shared_findings]

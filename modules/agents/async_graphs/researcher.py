"""异步 Graph 定义 — 联网研究员"""

from modules.agents.subagents.researcher import PROMPT
from modules.agents.subagents._tools import web_search, think

SPEC = {
    "graph_id": "researcher",
    "system_prompt": PROMPT,
    "model_purpose": "chat",
    "middleware_profile": "light",
    "call_limit": 20,
}


def get_tools():
    return [web_search, think]

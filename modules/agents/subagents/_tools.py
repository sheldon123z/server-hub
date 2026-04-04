"""SubAgent 专属工具 — web_search, think, 工具注册表"""

import os
from typing import Literal

from langchain_core.tools import tool

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


@tool
def fetch_webpage_content(url: str, max_length: int = 50000) -> str:
    """Fetch full webpage content and convert to markdown for deep analysis.

    Use this after web_search to get complete content from high-value URLs.
    """
    try:
        import httpx
        from markdownify import markdownify as md
    except ImportError:
        return "Error: httpx or markdownify not installed"

    try:
        resp = httpx.get(
            url,
            timeout=30,
            follow_redirects=True,
            headers={"User-Agent": "ServerHub-Research/1.0"},
        )
        resp.raise_for_status()
        content = md(resp.text, strip=["script", "style", "nav", "footer", "header"])
        # 清理多余空行
        import re

        content = re.sub(r"\n{3,}", "\n\n", content).strip()
        return content[:max_length]
    except Exception as e:
        return f"Failed to fetch {url}: {e}"


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


TOOL_REGISTRY = {
    "web_search": web_search,
    "think": think,
    "fetch_webpage_content": fetch_webpage_content,
}

"""异步 SubAgent 配置 — AsyncSubAgentMiddleware 使用"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_async_subagent_specs() -> list[dict]:
    """返回 AsyncSubAgent 配置（供 AsyncSubAgentMiddleware 使用）

    这些 spec 包含 graph_id 字段，create_deep_agent() 会自动识别并
    路由到 AsyncSubAgentMiddleware。
    """
    from config import settings
    port = getattr(settings, "port", 9900)
    base_url = f"http://127.0.0.1:{port}/lg"

    return [
        {
            "name": "deep-researcher",
            "description": (
                "Deep web research with multi-round search and synthesis. "
                "Use for long-running research tasks that require multiple search rounds, "
                "source cross-referencing, and comprehensive analysis."
            ),
            "graph_id": "researcher",
            "url": base_url,
        },
        {
            "name": "deep-security-audit",
            "description": (
                "Comprehensive security audit covering SSH config, firewall rules, "
                "user permissions, open ports, and CIS Benchmark compliance. "
                "Use for thorough security assessments that take several minutes."
            ),
            "graph_id": "security-auditor",
            "url": base_url,
        },
        {
            "name": "deep-correlation",
            "description": (
                "Deep cross-dimensional root cause analysis correlating system metrics, "
                "container health, service logs, user activity, and historical cases. "
                "Use for complex multi-component failures that require extensive investigation."
            ),
            "graph_id": "correlation-analyzer",
            "url": base_url,
        },
    ]


def load_async_subagent_specs() -> list[dict]:
    """加载异步 SubAgent 配置（优先自定义文件）"""
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_async_subagents.json"
    if custom_path.exists():
        try:
            return json.loads(custom_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("自定义异步 SubAgent 配置加载失败: %s", e)
    return get_async_subagent_specs()

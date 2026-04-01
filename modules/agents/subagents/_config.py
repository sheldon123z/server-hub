"""SubAgent 配置基础设施 — middleware/model 构建、持久化读写"""

import json
import logging
from pathlib import Path

from ._tools import _get_tools_by_names

logger = logging.getLogger(__name__)


# ─── Per-SubAgent Middleware 配置 ───

MIDDLEWARE_PROFILES = {"heavy", "light", "ops"}


def _build_subagent_middleware(profile: str) -> list:
    """根据 profile 构建 SubAgent 专属 middleware 栈

    Args:
        profile: "heavy"(工具密集) / "light"(轻量) / "ops"(操作型)
    """
    from langchain.agents.middleware import (
        ModelCallLimitMiddleware,
        ModelRetryMiddleware,
        ToolRetryMiddleware,
    )

    if profile == "heavy":
        return [
            ModelRetryMiddleware(max_retries=2, backoff_factor=1.0),
            ToolRetryMiddleware(max_retries=2, backoff_factor=1.0),
            ModelCallLimitMiddleware(run_limit=30),
        ]
    elif profile == "light":
        return [
            ModelRetryMiddleware(max_retries=2, backoff_factor=1.0),
            ModelCallLimitMiddleware(run_limit=15),
        ]
    else:  # ops
        return [
            ModelRetryMiddleware(max_retries=2, backoff_factor=1.0),
            ToolRetryMiddleware(max_retries=1, backoff_factor=1.0),
            ModelCallLimitMiddleware(run_limit=20),
        ]


def _get_subagent_model(purpose: str):
    """获取 SubAgent 模型实例，失败返回 None（由框架回退到主模型）"""
    try:
        from modules.agents.llm import get_chat_model

        return get_chat_model(purpose)
    except Exception:
        logger.debug("获取 SubAgent 模型失败 (purpose=%s)，将回退到主模型", purpose, exc_info=True)
        return None


def _get_subagent_model_by_id(model_id: str):
    """通过 provider:model 格式直接获取模型实例，失败返回 None"""
    try:
        from modules.agents.llm import get_chat_model_by_id

        return get_chat_model_by_id(model_id)
    except Exception:
        logger.debug("通过 ID 获取模型失败 (model_id=%s)，将回退到主模型", model_id, exc_info=True)
        return None


# ─── 模型 purpose / middleware profile 反向映射 ───

_MODEL_PURPOSE_MAP = {
    "researcher": "chat",
    "log-analyzer": "patrol",
    "security-auditor": "patrol",
    "correlation-analyzer": "chat",
    "ops-scheduler": "patrol",
    "knowledge-retriever": "patrol",
}

_MIDDLEWARE_PROFILE_MAP = {
    "researcher": "light",
    "log-analyzer": "heavy",
    "security-auditor": "ops",
    "correlation-analyzer": "heavy",
    "ops-scheduler": "ops",
    "knowledge-retriever": "light",
}


# ─── 持久化 ───


def _build_subagents_from_config(configs: list[dict]) -> list[dict]:
    """从 JSON 配置重建 SubAgent 对象列表"""
    result = []
    for cfg in configs:
        agent_def = {
            "name": cfg["name"],
            "description": cfg["description"],
            "system_prompt": cfg["system_prompt"],
        }
        # 工具
        tool_names = cfg.get("tools", [])
        if tool_names:
            agent_def["tools"] = _get_tools_by_names(tool_names)
        # 模型 — 优先使用直接指定的 model，否则按 purpose 获取
        direct_model = cfg.get("model")
        if direct_model:
            model = _get_subagent_model_by_id(direct_model)
            if model:
                agent_def["model"] = model
        else:
            model_purpose = cfg.get("model_purpose")
            if model_purpose:
                model = _get_subagent_model(model_purpose)
                if model:
                    agent_def["model"] = model
        # Middleware — 按 profile 构建
        mw_profile = cfg.get("middleware_profile")
        if mw_profile and mw_profile in MIDDLEWARE_PROFILES:
            agent_def["middleware"] = _build_subagent_middleware(mw_profile)
        # interrupt_on
        interrupt_on = cfg.get("interrupt_on")
        if interrupt_on:
            agent_def["interrupt_on"] = interrupt_on
        result.append(agent_def)
    return result


def save_subagents_config(configs: list[dict]):
    from config import settings

    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    custom_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for cfg in configs:
        name = cfg["name"]
        entry: dict = {
            "name": name,
            "description": cfg["description"],
            "system_prompt": cfg["system_prompt"],
            "tools": [t.name if hasattr(t, "name") else str(t) for t in cfg.get("tools", [])],
            "model_purpose": cfg.get("model_purpose", _MODEL_PURPOSE_MAP.get(name)),
            "middleware_profile": cfg.get("middleware_profile", _MIDDLEWARE_PROFILE_MAP.get(name)),
            "interrupt_on": cfg.get("interrupt_on"),
        }
        if cfg.get("model"):
            entry["model"] = cfg["model"]
        serializable.append(entry)
    custom_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def get_subagents_config() -> list[dict]:
    """返回可序列化的 SubAgent 配置（供 admin API 使用）"""
    from config import settings

    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    if custom_path.exists():
        try:
            return json.loads(custom_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("自定义 SubAgent 配置加载失败: %s", e)
    # 延迟导入避免循环
    from . import get_subagents

    defaults = get_subagents()
    return [
        {
            "name": d["name"],
            "description": d["description"],
            "system_prompt": d["system_prompt"],
            "tools": [t.name for t in d.get("tools", [])],
            "model_purpose": _MODEL_PURPOSE_MAP.get(d["name"]),
            "middleware_profile": _MIDDLEWARE_PROFILE_MAP.get(d["name"]),
            "interrupt_on": d.get("interrupt_on"),
        }
        for d in defaults
    ]


def get_available_tools() -> list[dict]:
    from modules.agents.safety import TOOL_RISK_MAP
    from modules.agents.tools import get_server_tools

    from ._tools import TOOL_REGISTRY

    tools = []
    for t in get_server_tools():
        tools.append(
            {
                "name": t.name,
                "description": (t.description or "")[:100],
                "risk": TOOL_RISK_MAP.get(t.name, "safe"),
                "source": "custom",
            }
        )
    for name, t in TOOL_REGISTRY.items():
        tools.append({"name": name, "description": (t.description or "")[:100], "risk": "safe", "source": "subagent"})
    builtins = [
        ("execute", "danger"),
        ("read_file", "safe"),
        ("write_file", "moderate"),
        ("edit_file", "moderate"),
        ("ls", "safe"),
        ("glob", "safe"),
        ("grep", "safe"),
    ]
    for name, risk in builtins:
        tools.append({"name": name, "description": f"内置: {name}", "risk": risk, "source": "builtin"})
    return tools

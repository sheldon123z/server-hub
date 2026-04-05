"""SubAgent 定义 — 专业化子智能体

遵循 LangChain 官方 SubAgent 规范 (https://docs.langchain.com/oss/python/deepagents/subagents):
- name/description/system_prompt/tools 四个 Required 字段必须显式指定
- tools 保持 minimal 集合
- system_prompt 包含输出格式和长度限制
- description 具体且 action-oriented

Per-SubAgent 高级配置 (https://docs.langchain.com/oss/python/deepagents/context-engineering):
- model: 按任务复杂度分配不同成本的模型
- middleware: 重试策略和调用次数限制
- interrupt_on: 危险操作审批拦截
"""

import json
import logging
from pathlib import Path

from config import settings

from ._async_specs import get_async_subagent_specs, load_async_subagent_specs
from ._config import (
    _build_subagent_middleware,
    _build_subagents_from_config,
    _get_subagent_model,
    get_available_tools,
    get_subagents_config,
    save_subagents_config,
)
from ._tools import TOOL_REGISTRY, _get_tools_by_names, think, web_search
from .correlation_analyzer import DEFINITION as _CORRELATION_ANALYZER_DEF
from .correlation_analyzer import PROMPT as CORRELATION_ANALYZER_PROMPT
from .knowledge_retriever import DEFINITION as _KNOWLEDGE_RETRIEVER_DEF
from .knowledge_retriever import PROMPT as KNOWLEDGE_RETRIEVER_PROMPT
from .log_analyzer import DEFINITION as _LOG_ANALYZER_DEF
from .log_analyzer import PROMPT as LOG_ANALYZER_PROMPT
from .ops_scheduler import DEFINITION as _OPS_SCHEDULER_DEF
from .ops_scheduler import PROMPT as OPS_SCHEDULER_PROMPT

# SubAgent 定义
from .researcher import DEFINITION as _RESEARCHER_DEF
from .researcher import PROMPT as RESEARCHER_PROMPT
from .security_auditor import DEFINITION as _SECURITY_AUDITOR_DEF
from .security_auditor import PROMPT as SECURITY_AUDITOR_PROMPT

logger = logging.getLogger(__name__)

# ---------- SubAgent Prompt 加载 ----------

_PROMPTS_DIR = Path(settings.db_path).parent / "subagent_prompts"


def load_subagent_prompt(name: str, default: str) -> str:
    """从 data/subagent_prompts/{name}.md 加载提示词，不存在则回退到默认值。"""
    prompt_file = _PROMPTS_DIR / f"{name}.md"
    if prompt_file.exists():
        try:
            content = prompt_file.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception as e:
            logger.warning("加载 SubAgent 提示词文件失败 (%s): %s", prompt_file, e)
    return default


# SubAgent name → prompt 文件名映射（name 中的 - 转为 _ 作为文件名）
_PROMPT_FILE_MAP = {
    "researcher": "researcher",
    "log-analyzer": "log_analyzer",
    "security-auditor": "security_auditor",
    "correlation-analyzer": "correlation_analyzer",
    "ops-scheduler": "ops_scheduler",
    "knowledge-retriever": "knowledge_retriever",
}

_ALL_DEFINITIONS_RAW = [
    _RESEARCHER_DEF,
    _LOG_ANALYZER_DEF,
    _SECURITY_AUDITOR_DEF,
    _CORRELATION_ANALYZER_DEF,
    _OPS_SCHEDULER_DEF,
    _KNOWLEDGE_RETRIEVER_DEF,
]

# 构建最终定义列表：用文件提示词覆盖源码默认值
_ALL_DEFINITIONS = []
for _defn in _ALL_DEFINITIONS_RAW:
    _file_key = _PROMPT_FILE_MAP.get(_defn["name"])
    if _file_key:
        _loaded = load_subagent_prompt(_file_key, _defn["system_prompt"])
        if _loaded != _defn["system_prompt"]:
            _defn = {**_defn, "system_prompt": _loaded}
    _ALL_DEFINITIONS.append(_defn)


def get_subagents() -> list[dict]:
    """返回所有 SubAgent 配置（含 per-subagent model/middleware/interrupt_on）

    从各 DEFINITION dict 构建完整配置，解析 tools_fn、model、middleware。
    """
    chat_model = _get_subagent_model("chat")
    patrol_model = _get_subagent_model("patrol")
    model_map = {"chat": chat_model, "patrol": patrol_model}

    result = []
    for defn in _ALL_DEFINITIONS:
        agent_def = {
            "name": defn["name"],
            "description": defn["description"],
            "system_prompt": defn["system_prompt"],
        }
        # 解析 tools_fn → tools
        tools_fn = defn.get("tools_fn")
        if tools_fn:
            agent_def["tools"] = tools_fn()
        # 模型
        model_purpose = defn.get("model_purpose")
        if model_purpose and model_purpose in model_map:
            agent_def["model"] = model_map[model_purpose]
        # Middleware
        mw_profile = defn.get("middleware_profile")
        if mw_profile:
            agent_def["middleware"] = _build_subagent_middleware(mw_profile)
        # interrupt_on
        interrupt_on = defn.get("interrupt_on")
        if interrupt_on:
            agent_def["interrupt_on"] = interrupt_on
        result.append(agent_def)
    return result


def load_subagents() -> list[dict]:
    """加载 SubAgent 配置（优先自定义文件）"""
    from config import settings

    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    if custom_path.exists():
        try:
            configs = json.loads(custom_path.read_text(encoding="utf-8"))
            return _build_subagents_from_config(configs)
        except Exception as e:
            logger.warning("自定义 SubAgent 配置加载失败: %s", e)
    return get_subagents()


__all__ = [
    "CORRELATION_ANALYZER_PROMPT",
    "KNOWLEDGE_RETRIEVER_PROMPT",
    "LOG_ANALYZER_PROMPT",
    "OPS_SCHEDULER_PROMPT",
    "RESEARCHER_PROMPT",
    "SECURITY_AUDITOR_PROMPT",
    "TOOL_REGISTRY",
    "_get_tools_by_names",
    "get_async_subagent_specs",
    "get_available_tools",
    "get_subagents",
    "get_subagents_config",
    "load_async_subagent_specs",
    "load_subagent_prompt",
    "load_subagents",
    "save_subagents_config",
    "think",
    "web_search",
]

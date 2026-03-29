"""多服务商 LLM 配置 — 支持 OpenRouter / 火山引擎 / 智谱 / Kimi / MiniMax 等

所有服务商都提供 OpenAI 兼容 API，统一使用 ChatOpenAI 接入。
模型 ID 格式: "provider:model_name"，如 "openrouter:deepseek/deepseek-chat"
"""

import logging
import os

from langchain_openai import ChatOpenAI

from config import settings

logger = logging.getLogger(__name__)


# ─── 服务商注册表 ───

PROVIDERS = {
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "description": "聚合平台，接入 OpenAI/Anthropic/Google/DeepSeek 等数百个模型",
        "models_api": "https://openrouter.ai/api/v1/models",
        "default_models": [
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3"},
            {"id": "deepseek/deepseek-reasoner", "name": "DeepSeek R1"},
            {"id": "openai/gpt-4.1-mini", "name": "GPT-4.1 Mini"},
            {"id": "openai/gpt-4.1-nano", "name": "GPT-4.1 Nano"},
            {"id": "openai/gpt-4.1", "name": "GPT-4.1"},
            {"id": "anthropic/claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
            {"id": "google/gemini-2.5-flash", "name": "Gemini 2.5 Flash"},
            {"id": "google/gemini-2.5-pro", "name": "Gemini 2.5 Pro"},
        ],
    },
    "volcengine": {
        "name": "火山引擎 (豆包)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key_env": "VOLCENGINE_API_KEY",
        "description": "字节跳动旗下，提供豆包大模型",
        "default_models": [
            {"id": "doubao-1.5-pro-32k", "name": "豆包 1.5 Pro 32K"},
            {"id": "doubao-1.5-pro-256k", "name": "豆包 1.5 Pro 256K"},
            {"id": "doubao-1.5-thinking-pro-250415", "name": "豆包 1.5 Thinking Pro"},
            {"id": "deepseek-v3-250324", "name": "DeepSeek V3 (火山)"},
            {"id": "deepseek-r1-250120", "name": "DeepSeek R1 (火山)"},
        ],
    },
    "zhipu": {
        "name": "智谱 AI (GLM)",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "ZHIPU_API_KEY",
        "description": "清华系，GLM 系列模型",
        "default_models": [
            {"id": "glm-4-plus", "name": "GLM-4 Plus"},
            {"id": "glm-4-long", "name": "GLM-4 Long (1M)"},
            {"id": "glm-4-flash", "name": "GLM-4 Flash (免费)"},
            {"id": "glm-4-flashx", "name": "GLM-4 FlashX"},
        ],
    },
    "moonshot": {
        "name": "Kimi (月之暗面)",
        "base_url": "https://api.moonshot.cn/v1",
        "api_key_env": "MOONSHOT_API_KEY",
        "description": "月之暗面出品，长上下文能力强",
        "default_models": [
            {"id": "moonshot-v1-auto", "name": "Kimi Auto"},
            {"id": "moonshot-v1-8k", "name": "Kimi 8K"},
            {"id": "moonshot-v1-32k", "name": "Kimi 32K"},
            {"id": "moonshot-v1-128k", "name": "Kimi 128K"},
        ],
    },
    "minimax": {
        "name": "MiniMax",
        "base_url": "https://api.minimax.chat/v1",
        "api_key_env": "MINIMAX_API_KEY",
        "description": "MiniMax 出品，擅长对话和生成",
        "default_models": [
            {"id": "MiniMax-Text-01", "name": "MiniMax Text 01"},
            {"id": "MiniMax-Text-01-128K", "name": "MiniMax Text 01 128K"},
        ],
    },
    "deepseek": {
        "name": "DeepSeek (直连)",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "description": "DeepSeek 官方 API，无中间商",
        "default_models": [
            {"id": "deepseek-chat", "name": "DeepSeek V3"},
            {"id": "deepseek-reasoner", "name": "DeepSeek R1"},
        ],
    },
    "openai": {
        "name": "OpenAI (直连)",
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "description": "OpenAI 官方 API",
        "default_models": [
            {"id": "gpt-4.1-mini", "name": "GPT-4.1 Mini"},
            {"id": "gpt-4.1-nano", "name": "GPT-4.1 Nano"},
            {"id": "gpt-4.1", "name": "GPT-4.1"},
            {"id": "gpt-4o", "name": "GPT-4o"},
        ],
    },
    "ollama": {
        "name": "Ollama (本地)",
        "base_url": "http://localhost:11434/v1",
        "api_key_env": "",
        "description": "本地部署，零成本，需要先下载模型",
        "default_models": [
            {"id": "qwen3:32b", "name": "Qwen3 32B"},
            {"id": "qwen3:8b", "name": "Qwen3 8B"},
            {"id": "llama3.1:8b", "name": "Llama 3.1 8B"},
        ],
    },
}


def parse_model_id(model_id: str) -> tuple[str, str]:
    """解析 'provider:model' 格式，返回 (provider, model)

    如果没有冒号前缀，按旧格式走 OpenRouter。
    """
    if ":" in model_id and model_id.split(":")[0] in PROVIDERS:
        provider, model = model_id.split(":", 1)
        return provider, model
    # 向后兼容：无前缀的旧格式走 openrouter
    return "openrouter", model_id


def get_chat_model(purpose: str = "chat") -> ChatOpenAI:
    """获取 LLM 实例，自动根据 provider:model 格式选择服务商

    Args:
        purpose: "chat" 对话 | "patrol" 巡检 | "complex" 复杂分析
    """
    model_map = {
        "chat": settings.agent_default_model,
        "patrol": settings.agent_patrol_model,
    }
    full_model_id = model_map.get(purpose, model_map["chat"])
    provider_key, model_name = parse_model_id(full_model_id)

    provider = PROVIDERS.get(provider_key)
    if not provider:
        logger.warning("Unknown provider '%s', falling back to openrouter", provider_key)
        provider = PROVIDERS["openrouter"]

    # 获取 API Key
    api_key_env = provider.get("api_key_env", "")
    api_key = os.getenv(api_key_env, "") if api_key_env else "not-needed"

    if not api_key and provider_key != "ollama":
        logger.warning("Provider %s has no API key (%s), may fail", provider_key, api_key_env)

    return ChatOpenAI(
        model=model_name,
        base_url=provider["base_url"],
        api_key=api_key or "not-needed",
        temperature=0.1,
        max_tokens=4096,
        streaming=True,
    )


def get_chat_model_by_id(model_id: str | None = None) -> ChatOpenAI:
    """根据 provider:model 格式返回 ChatOpenAI 实例

    供团队系统使用，允许每个团队成员指定不同模型。
    如果 model_id 为空，回退到全局默认模型。
    """
    if not model_id:
        return get_chat_model("chat")

    provider_key, model_name = parse_model_id(model_id)
    provider = PROVIDERS.get(provider_key)
    if not provider:
        logger.warning("Unknown provider '%s' in model_id '%s', falling back to default", provider_key, model_id)
        return get_chat_model("chat")

    api_key_env = provider.get("api_key_env", "")
    api_key = os.getenv(api_key_env, "") if api_key_env else "not-needed"

    return ChatOpenAI(
        model=model_name,
        base_url=provider["base_url"],
        api_key=api_key or "not-needed",
        temperature=0.3,
        max_tokens=4096,
        streaming=True,
    )


def get_provider_status() -> list[dict]:
    """获取所有服务商的状态（是否配置了 API Key）"""
    result = []
    for key, provider in PROVIDERS.items():
        api_key_env = provider.get("api_key_env", "")
        has_key = bool(os.getenv(api_key_env, "")) if api_key_env else (key == "ollama")
        result.append(
            {
                "id": key,
                "name": provider["name"],
                "description": provider["description"],
                "has_key": has_key,
                "api_key_env": api_key_env,
                "models": provider.get("default_models", []),
            }
        )
    return result

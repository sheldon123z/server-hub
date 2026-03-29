"""配置 + Agent 管理 API 路由"""

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from auth.dependencies import require_role

router = APIRouter()

logger = logging.getLogger(__name__)


# ─── 配置 ───


@router.get("/settings")
async def get_agent_settings(user=Depends(require_role("admin"))):
    from config import settings
    from modules.agents.llm import get_provider_status

    return {
        "default_model": settings.agent_default_model,
        "patrol_model": settings.agent_patrol_model,
        "shell_timeout": settings.agent_shell_timeout,
        "shell_max_output": settings.agent_shell_max_output,
        "providers": get_provider_status(),
    }


@router.put("/settings")
async def update_agent_settings(request: Request, user=Depends(require_role("admin"))):
    from config import BASE_DIR, settings

    body = await request.json()

    changed = []
    if "default_model" in body:
        settings.agent_default_model = body["default_model"]
        changed.append(f"SERVERHUB_AGENT_MODEL={body['default_model']}")
    if "patrol_model" in body:
        settings.agent_patrol_model = body["patrol_model"]
        changed.append(f"SERVERHUB_PATROL_MODEL={body['patrol_model']}")

    if changed:
        env_path = BASE_DIR / ".env"
        try:
            lines = env_path.read_text().splitlines() if env_path.exists() else []
            for kv in changed:
                key = kv.split("=", 1)[0]
                found = False
                for i, line in enumerate(lines):
                    if line.startswith(key + "="):
                        lines[i] = kv
                        found = True
                        break
                if not found:
                    lines.append(kv)
            env_path.write_text("\n".join(lines) + "\n")
        except Exception as e:
            logger.error(".env 写入失败，设置未持久化: %s", e)

        from modules.agents.deep_agent import reset_agent_cache

        reset_agent_cache()

    return {"ok": True, "default_model": settings.agent_default_model, "patrol_model": settings.agent_patrol_model}


@router.post("/settings/refresh-models/{provider_id}")
async def refresh_provider_models(provider_id: str, user=Depends(require_role("admin"))):
    import os

    import httpx

    from modules.agents.llm import PROVIDERS

    if provider_id not in PROVIDERS:
        raise HTTPException(404, f"未知服务商: {provider_id}")

    provider = PROVIDERS[provider_id]

    if provider_id == "openrouter":
        api_key = os.getenv(provider.get("api_key_env", ""), "")
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
                resp = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
                resp.raise_for_status()
                data = resp.json()
            models = [
                {"id": m["id"], "name": m.get("name", m["id"])}
                for m in data.get("data", [])
                if m.get("id") and ":free" not in m["id"]
            ]
            models.sort(key=lambda x: x["name"])
            provider["default_models"] = models[:200]
            return {"ok": True, "count": len(models[:200]), "models": models[:20]}
        except Exception as e:
            raise HTTPException(500, f"刷新失败: {e!s}")

    elif provider_id == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("http://localhost:11434/api/tags")
                data = resp.json()
            models = [{"id": m["name"], "name": m["name"]} for m in data.get("models", [])]
            provider["default_models"] = models
            return {"ok": True, "count": len(models), "models": models}
        except Exception as e:
            raise HTTPException(500, f"Ollama 连接失败: {e!s}")

    return {"ok": False, "message": f"服务商 {provider_id} 不支持动态刷新"}


@router.put("/settings/api-key/{provider_id}")
async def update_provider_api_key(provider_id: str, request: Request, user=Depends(require_role("admin"))):
    import os

    from config import BASE_DIR
    from modules.agents.llm import PROVIDERS

    if provider_id not in PROVIDERS:
        raise HTTPException(404, f"未知服务商: {provider_id}")

    body = await request.json()
    api_key = body.get("api_key", "").strip()
    if not api_key:
        raise HTTPException(400, "API Key 不能为空")

    provider = PROVIDERS[provider_id]
    env_var = provider.get("api_key_env", "")
    if not env_var:
        raise HTTPException(400, f"服务商 {provider_id} 不需要 API Key")

    os.environ[env_var] = api_key

    env_path = BASE_DIR / ".env"
    try:
        lines = env_path.read_text().splitlines() if env_path.exists() else []
        kv = f"{env_var}={api_key}"
        found = False
        for i, line in enumerate(lines):
            if line.startswith(env_var + "="):
                lines[i] = kv
                found = True
                break
        if not found:
            lines.append(kv)
        env_path.write_text("\n".join(lines) + "\n")
    except Exception as e:
        raise HTTPException(500, f"写入 .env 失败: {e!s}")

    from modules.agents.deep_agent import reset_agent_cache

    reset_agent_cache()
    return {"ok": True, "provider": provider_id, "env_var": env_var}


# ─── Agent 管理 API ───


@router.get("/admin/prompt")
async def get_prompt(user=Depends(require_role("admin"))):
    """获取当前系统提示词"""
    from pathlib import Path

    from config import settings
    from modules.agents.prompts import SYSTEM_PROMPT

    custom_path = Path(settings.db_path).parent / "custom_prompt.txt"
    is_custom = custom_path.exists()
    content = custom_path.read_text(encoding="utf-8") if is_custom else SYSTEM_PROMPT
    return {"content": content, "prompt": content, "is_custom": is_custom}


@router.put("/admin/prompt")
async def update_prompt(request: Request, user=Depends(require_role("admin"))):
    """保存自定义系统提示词"""
    from pathlib import Path

    from config import settings

    body = await request.json()
    content = body.get("content", body.get("prompt", ""))
    custom_path = Path(settings.db_path).parent / "custom_prompt.txt"
    if body.get("reset") or body.get("prompt") is None:
        custom_path.unlink(missing_ok=True)
        from modules.agents.deep_agent import reset_agent_cache

        reset_agent_cache()
        return {"ok": True, "message": "已重置为默认提示词"}
    custom_path.write_text(content, encoding="utf-8")
    from modules.agents.deep_agent import reset_agent_cache

    reset_agent_cache()
    return {"ok": True, "message": "提示词已保存"}


@router.get("/admin/subagents")
async def list_subagents(user=Depends(require_role("admin"))):
    """获取所有 SubAgent 配置 + 可用工具列表"""
    from modules.agents.llm import get_provider_status
    from modules.agents.subagents import get_available_tools, get_subagents_config

    subagents = get_subagents_config()
    available_tools = get_available_tools()
    for item in subagents:
        if "model" not in item:
            model_purpose = item.get("model_purpose")
            item["model"] = model_purpose if model_purpose else None
    for tool in available_tools:
        tool["risk_level"] = tool.get("risk")
    return {
        "subagents": subagents,
        "available_tools": available_tools,
        "providers": get_provider_status(),
    }


@router.put("/admin/subagents")
async def save_subagents(request: Request, user=Depends(require_role("admin"))):
    """保存全部 SubAgent 配置"""
    from modules.agents.subagents import save_subagents_config

    body = await request.json()
    configs = body.get("subagents", [])
    if body.get("reset"):
        from pathlib import Path

        from config import settings

        custom_path = Path(settings.db_path).parent / "custom_subagents.json"
        custom_path.unlink(missing_ok=True)
        from modules.agents.deep_agent import reset_agent_cache

        reset_agent_cache()
        return {"ok": True, "message": "已重置为默认 SubAgent"}
    save_subagents_config(configs)
    from modules.agents.deep_agent import reset_agent_cache

    reset_agent_cache()
    return {"ok": True, "message": f"已保存 {len(configs)} 个 SubAgent"}


@router.get("/admin/memory")
async def get_memory(user=Depends(require_role("admin"))):
    """获取运行时长期记忆文件内容"""
    from modules.agents.deep_agent import get_memory_path

    memory_path = get_memory_path()
    content = memory_path.read_text(encoding="utf-8") if memory_path.exists() else ""
    return {"content": content, "path": str(memory_path)}


@router.put("/admin/memory")
async def update_memory(request: Request, user=Depends(require_role("admin"))):
    """保存运行时长期记忆文件"""
    from modules.agents.deep_agent import get_memory_path, reset_agent_cache

    body = await request.json()
    content = body.get("content", "")
    memory_path = get_memory_path()
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text(content, encoding="utf-8")
    reset_agent_cache()
    return {"ok": True, "message": "记忆已保存"}


# ─── RAG 知识库管理 ───


@router.get("/admin/rag")
async def get_rag_stats(user=Depends(require_role("admin"))):
    """获取 RAG 知识库统计信息"""
    try:
        from modules.agents.rag import get_index_stats

        stats = get_index_stats()
        return {"ok": True, "stats": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/admin/rag/reindex")
async def trigger_reindex(user=Depends(require_role("admin"))):
    """手动触发 RAG 知识库全量重建"""
    try:
        from modules.agents.rag import build_full_index, get_index_stats

        await asyncio.to_thread(build_full_index, True)
        stats = get_index_stats()
        return {"ok": True, "stats": stats}
    except Exception as e:
        return {"ok": False, "error": str(e)}

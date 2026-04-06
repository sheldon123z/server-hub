"""Pipeline Step 执行器注册表 — 实际执行器在后续 PR 中实现"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)

# step_type → executor 函数的注册表
_REGISTRY: dict[str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]] = {}


def register_step(step_type: str):
    """装饰器: 注册 step 执行器"""

    def decorator(func: Callable[..., Coroutine[Any, Any, dict[str, Any]]]):
        _REGISTRY[step_type] = func
        return func

    return decorator


def get_step_executor(step_type: str) -> Callable[..., Coroutine[Any, Any, dict[str, Any]]]:
    """获取指定类型的 step 执行器，未注册则返回占位函数"""
    if step_type in _REGISTRY:
        return _REGISTRY[step_type]

    async def _placeholder(**kwargs: Any) -> dict[str, Any]:
        logger.warning("Step 类型 '%s' 的执行器尚未注册，使用占位实现", step_type)
        return {"status": "skipped", "message": f"executor for '{step_type}' not implemented"}

    return _placeholder

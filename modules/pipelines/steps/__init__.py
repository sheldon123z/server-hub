"""Step 执行器注册表 — 10 种 step 类型的统一注册与查找"""

import importlib
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class StepExecutor(Protocol):
    """Step 执行器协议 — 所有 step 类型必须实现此接口"""

    async def execute(self, config: dict, state: dict) -> dict:
        """执行 step，返回 {output, exit_code?, error?}"""
        ...


_STEP_REGISTRY: dict[str, Any] = {}

# 所有内置 step 模块（导入时自动注册）
_STEP_MODULES = [
    "modules.pipelines.steps.shell",
    "modules.pipelines.steps.ssh",
    "modules.pipelines.steps.playbook_step",
    "modules.pipelines.steps.http",
    "modules.pipelines.steps.agent",
    "modules.pipelines.steps.approval",
    "modules.pipelines.steps.decision",
    "modules.pipelines.steps.condition",
    "modules.pipelines.steps.parallel",
    "modules.pipelines.steps.notify",
    "modules.pipelines.steps.delay",
]


def register_step(step_type: str):
    """装饰器：注册 step 执行器类"""

    def decorator(cls):
        _STEP_REGISTRY[step_type] = cls()
        logger.debug("注册 step 执行器: %s -> %s", step_type, cls.__name__)
        return cls

    return decorator


def get_step_executor(step_type: str) -> StepExecutor:
    """获取 step 执行器实例，不存在则抛出 ValueError"""
    if step_type not in _STEP_REGISTRY:
        raise ValueError(f"未知的 step 类型: {step_type}")
    return _STEP_REGISTRY[step_type]


def get_registered_types() -> list[str]:
    """返回所有已注册的 step 类型名"""
    return list(_STEP_REGISTRY.keys())


def load_all_steps():
    """导入所有内置 step 模块，触发 @register_step 注册"""
    for mod_name in _STEP_MODULES:
        try:
            importlib.import_module(mod_name)
        except Exception:
            logger.exception("加载 step 模块失败: %s", mod_name)

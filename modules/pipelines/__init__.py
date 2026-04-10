"""Pipeline 编排模块 — 可编排的多步骤工作流引擎"""

from modules.pipelines.routes import router

MODULE_INFO = {
    "name": "pipelines",
    "display_name": "Pipeline 编排",
    "icon": "git-merge",
    "category": "智能",
    "required_role": "admin",
    "order": 8,
}

__all__ = ["MODULE_INFO", "router"]

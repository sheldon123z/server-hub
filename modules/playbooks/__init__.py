"""运维剧本模块 — 可复用运维工作流模板"""

from modules.playbooks.routes import router

MODULE_INFO = {
    "name": "playbooks",
    "display_name": "运维剧本",
    "icon": "script",
    "category": "自动化",
    "required_role": "admin",
    "order": 55,
}

__all__ = ["router", "MODULE_INFO"]

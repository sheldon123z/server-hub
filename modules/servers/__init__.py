"""多服务器管理模块 — 服务器注册、分组、连通性测试"""

from modules.servers.routes import router

MODULE_INFO = {
    "name": "servers",
    "display_name": "服务器",
    "icon": "server-2",
    "category": "基础设施",
    "required_role": "admin",
    "order": 2,
}

__all__ = ["MODULE_INFO", "router"]

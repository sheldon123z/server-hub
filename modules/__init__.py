"""模块自动发现与注册"""

import importlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
_modules = []


def discover_modules():
    """自动发现 modules/ 下的所有子模块"""
    global _modules
    _modules = []
    package_dir = Path(__file__).parent

    for item in sorted(package_dir.iterdir()):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        init_file = item / "__init__.py"
        if not init_file.exists():
            continue

        try:
            mod = importlib.import_module(f"modules.{item.name}")
            info = getattr(mod, "MODULE_INFO", None)
            router = getattr(mod, "router", None)
            if info and router:
                _modules.append({**info, "router": router})
        except Exception as e:
            logger.exception("加载模块 %s 失败: %s", item.name, e)

    _modules.sort(key=lambda m: m.get("order", 99))
    return _modules


def get_modules():
    return _modules


def get_sidebar_items(user_role: str = "user"):
    """获取侧边栏菜单项（根据角色过滤）"""
    role_level = {"admin": 2, "user": 1}
    user_level = role_level.get(user_role, 0)

    items = []
    for m in _modules:
        if m.get("hidden"):
            continue
        required = role_level.get(m.get("required_role", "user"), 1)
        if user_level >= required:
            items.append({
                "name": m["name"],
                "display_name": m["display_name"],
                "icon": m.get("icon", "circle"),
                "category": m.get("category", "其他"),
            })
    return items

"""通知模板引擎 — 支持 {{变量}} 替换"""

import re

_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def render(template: str, variables: dict) -> str:
    """将模板中的 {{key}} 替换为 variables[key]，未找到的变量保持原样。"""
    return _VAR_PATTERN.sub(lambda m: str(variables.get(m.group(1), m.group(0))), template)

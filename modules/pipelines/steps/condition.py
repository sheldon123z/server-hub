"""Condition Step 执行器 — 条件分支路由"""

import logging
import operator
import re

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)

# 支持的比较操作符
_OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "contains": lambda a, b: str(b) in str(a),
    "not_contains": lambda a, b: str(b) not in str(a),
}

# 匹配表达式: left op right
_EXPR_PATTERN = re.compile(r"^(.+?)\s+(==|!=|>=|<=|>|<|contains|not_contains)\s+(.+)$")


def _coerce_value(val: str):
    """尝试将字符串转为数值类型"""
    val = val.strip().strip("'\"")
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    if val.lower() == "true":
        return True
    if val.lower() == "false":
        return False
    return val


@register_step("condition")
class ConditionStepExecutor:
    """解析条件表达式，返回分支方向"""

    async def execute(self, config: dict, state: dict) -> dict:
        expression = config.get("expression", "")
        on_true = config.get("on_true", "")
        on_false = config.get("on_false", "")

        if not expression:
            return {"output": "", "branch": on_false, "error": "缺少 expression 参数"}

        match = _EXPR_PATTERN.match(expression.strip())
        if not match:
            # 直接当布尔值处理
            result = bool(_coerce_value(expression))
            branch = on_true if result else on_false
            return {"output": str(result), "branch": branch, "evaluated": result}

        left_raw, op_str, right_raw = match.groups()
        left = _coerce_value(left_raw)
        right = _coerce_value(right_raw)
        op_func = _OPERATORS.get(op_str)

        if not op_func:
            return {"output": "", "branch": on_false, "error": f"不支持的操作符: {op_str}"}

        try:
            result = op_func(left, right)
        except Exception as e:
            logger.warning("条件表达式求值失败: %s — %s", expression, e)
            result = False

        branch = on_true if result else on_false
        logger.debug("条件求值: %s => %s, 分支: %s", expression, result, branch)
        return {"output": str(result), "branch": branch, "evaluated": result}

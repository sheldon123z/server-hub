"""结构化澄清工具 — 让 Agent 在信息不足时主动向用户提问

参考 DeerFlow ask_clarification_tool:
- 4 种澄清类型分类
- 可附带选项列表
- SSE 事件前端差异化渲染
"""

import json
from typing import Literal

from modules.agents.tools.registry import RiskLevel, register_tool


@register_tool(risk=RiskLevel.SAFE, group="core:interaction", icon="HelpCircle", label="结构化澄清")
def ask_clarification(
    question: str,
    clarification_type: Literal[
        "missing_info",
        "ambiguous_requirement",
        "approach_choice",
        "risk_confirmation",
    ],
    context: str = "",
    options: list[str] | None = None,
) -> str:
    """向用户请求澄清信息。当信息不足、需求模糊、需要用户选择方案或确认风险时使用。

    Args:
        question: 要问用户的问题
        clarification_type: 澄清类型
            - missing_info: 缺少执行所需的必要信息
            - ambiguous_requirement: 用户需求模糊，需要明确
            - approach_choice: 有多种方案，需要用户选择
            - risk_confirmation: 高风险操作前的确认
        context: 为什么需要澄清的背景说明
        options: 可选项列表（适用于 approach_choice 类型）
    """
    result = {
        "_clarification": True,
        "question": question,
        "clarification_type": clarification_type,
        "context": context,
    }
    if options:
        result["options"] = options

    return json.dumps(result, ensure_ascii=False)

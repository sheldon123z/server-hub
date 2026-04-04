"""Token 感知的记忆注入 — 将结构化记忆格式化为系统提示词片段"""

import logging

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 2 字符/token，英文约 4 字符/token）"""
    # Simple heuristic: count characters, mix of Chinese and English
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


def format_memory_for_prompt(memory_data: dict, token_budget: int = 2000) -> str:
    """将结构化记忆格式化为系统提示词注入片段

    Args:
        memory_data: MemoryStorage.load() 返回的字典
        token_budget: 最大 token 预算

    Returns:
        格式化的记忆文本，可直接注入系统提示词
    """
    if not memory_data:
        return ""

    parts = []
    used_tokens = 0

    # 1. Context sections (highest priority)
    context = memory_data.get("context", {})
    for key, label in [
        ("topOfMind", "当前关注"),
        ("workContext", "工作上下文"),
        ("userPreferences", "用户偏好"),
    ]:
        section = context.get(key, {})
        summary = section.get("summary", "")
        if summary:
            line = f"- {label}: {summary}"
            tokens = _estimate_tokens(line)
            if used_tokens + tokens > token_budget:
                break
            parts.append(line)
            used_tokens += tokens

    # 2. Facts (sorted by confidence, highest first)
    facts = memory_data.get("facts", [])
    facts_sorted = sorted(facts, key=lambda f: f.get("confidence", 0), reverse=True)

    if facts_sorted and used_tokens < token_budget:
        fact_lines = []
        for fact in facts_sorted:
            content = fact.get("content", "")
            category = fact.get("category", "")
            if not content:
                continue
            # Correction facts get special annotation
            if category == "correction":
                line = f"- \u26a0 {content}"
            else:
                line = f"- {content}"
            tokens = _estimate_tokens(line)
            if used_tokens + tokens > token_budget:
                break
            fact_lines.append(line)
            used_tokens += tokens

        if fact_lines:
            parts.append("记忆事实:")
            parts.extend(fact_lines)

    # 3. History (lowest priority, fill remaining budget)
    history = memory_data.get("history", {})
    recent = history.get("recentActivity", {}).get("summary", "")
    if recent and used_tokens < token_budget - 50:
        line = f"最近活动: {recent[:200]}"
        parts.append(line)

    if not parts:
        return ""

    return "\n## 记忆上下文\n" + "\n".join(parts)

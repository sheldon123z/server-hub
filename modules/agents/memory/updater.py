"""LLM 驱动的记忆更新器 — 对话结束后自动提取事实和更新摘要"""

import json
import logging
import time

from langchain_core.messages import AIMessage, HumanMessage

logger = logging.getLogger(__name__)

MEMORY_UPDATE_PROMPT = """你是一个记忆管理助手。分析以下对话，提取需要记住的信息。

## 当前记忆状态
{current_memory}

## 最近对话
{conversation}

## 任务
分析对话内容，返回 JSON 格式的更新指令：

```json
{{
  "context_updates": {{
    "workContext": "更新后的工作上下文摘要（如无变化则为空字符串）",
    "userPreferences": "更新后的用户偏好摘要（如无变化则为空字符串）",
    "topOfMind": "当前最需要关注的事项（如无变化则为空字符串）"
  }},
  "new_facts": [
    {{
      "content": "需要记住的事实",
      "category": "preference|knowledge|context|behavior|correction",
      "confidence": 0.8
    }}
  ],
  "remove_fact_ids": ["需要删除的过时事实 ID"],
  "correction_detected": false
}}
```

## 规则
1. 只提取对未来对话有价值的信息（用户偏好、常用操作、服务器特殊配置等）
2. 不要记录临时性的操作细节（如具体的 CPU 数值、某次查询结果）
3. correction 类别用于用户纠正 AI 错误的场景，confidence >= 0.95
4. 如果对话中没有值得记忆的内容，所有字段返回空
5. 直接输出 JSON，不要包含其他文字"""


async def update_memory(
    storage,
    conversation_messages: list,
    conversation_id: str = "",
) -> None:
    """分析对话并更新记忆

    Args:
        storage: MemoryStorage 实例
        conversation_messages: 对话消息列表 (LangChain Message 对象)
        conversation_id: 对话 ID (用作事实 source)
    """
    # Filter to only human and AI messages with content
    formatted_parts = []
    for msg in conversation_messages:
        if isinstance(msg, HumanMessage) and msg.content:
            formatted_parts.append(f"用户: {msg.content}")
        elif isinstance(msg, AIMessage) and msg.content:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content.strip():
                formatted_parts.append(f"助手: {content[:500]}")

    if len(formatted_parts) < 2:
        return  # Too short to extract meaningful memory

    conversation_text = "\n".join(formatted_parts[-20:])  # Last 20 messages max

    current_data = storage.load()
    # Format current memory for the prompt
    current_summary = json.dumps(
        {
            "context": current_data.get("context", {}),
            "history": current_data.get("history", {}),
            "facts": [
                {
                    "id": f["id"],
                    "content": f["content"],
                    "category": f.get("category", ""),
                }
                for f in current_data.get("facts", [])[-10:]
            ],  # Last 10 facts
        },
        ensure_ascii=False,
        indent=2,
    )

    prompt = MEMORY_UPDATE_PROMPT.format(
        current_memory=current_summary,
        conversation=conversation_text,
    )

    try:
        from modules.agents.llm import get_chat_model

        model = get_chat_model("fast")
        response = await model.ainvoke([HumanMessage(content=prompt)])

        # Parse JSON from response
        response_text = response.content if isinstance(response.content, str) else str(response.content)
        # Extract JSON block
        json_str = response_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        updates = json.loads(json_str.strip())
    except Exception as e:
        logger.warning("记忆更新 LLM 调用失败: %s", e)
        return

    # Apply updates
    try:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Context updates
        ctx_updates = updates.get("context_updates", {})
        for key in ("workContext", "userPreferences", "topOfMind"):
            value = ctx_updates.get(key, "")
            if value and isinstance(value, str) and value.strip():
                current_data.setdefault("context", {})[key] = {
                    "summary": value.strip(),
                    "updatedAt": now,
                }

        # New facts
        for fact in updates.get("new_facts", []):
            if isinstance(fact, dict) and fact.get("content"):
                storage.add_fact(
                    content=fact["content"],
                    category=fact.get("category", "knowledge"),
                    confidence=fact.get("confidence", 0.8),
                    source=conversation_id,
                )

        # Remove old facts
        for fact_id in updates.get("remove_fact_ids", []):
            if isinstance(fact_id, str):
                storage.remove_fact(fact_id)

        # Update history
        current_data.setdefault("history", {})["recentActivity"] = {
            "summary": conversation_text[:200],
            "updatedAt": now,
        }

        storage.save(current_data)
        logger.info(
            "记忆更新完成: conv=%s, new_facts=%d",
            conversation_id,
            len(updates.get("new_facts", [])),
        )
    except Exception as e:
        logger.warning("记忆更新应用失败: %s", e)

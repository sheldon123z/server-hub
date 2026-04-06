"""Agent Step 执行器 — 调用 Deep Agent 进行 AI 分析与决策"""

import json
import logging

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("agent")
class AgentStepExecutor:
    """调用 Deep Agent 执行 AI 分析任务"""

    async def execute(self, config: dict, state: dict) -> dict:
        from modules.agents.deep_agent import build_agent

        prompt = config.get("prompt", "")
        _model = config.get("model", "fast")  # 预留给未来模型选择
        output_format = config.get("output_format")

        if not prompt:
            return {"output": "", "error": "缺少 prompt 参数"}

        # 如果要求 JSON 输出，在提示词中追加格式约束
        if output_format == "json":
            prompt += "\n\n请严格以 JSON 格式输出结果，不要包含其他文字。"

        try:
            agent, agent_config = await build_agent(mode="patrol")
            # 使用唯一线程 ID 防止与其他对话冲突
            run_id = state.get("run_id", "pipeline")
            step_id = config.get("id", "agent")
            thread_id = f"pipeline-{run_id}-{step_id}"

            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config={"configurable": {"thread_id": thread_id}, **agent_config},
            )

            # 提取最后一条 AI 消息
            messages = result.get("messages", [])
            ai_output = ""
            for msg in reversed(messages):
                content = getattr(msg, "content", None) or msg.get("content", "")
                if isinstance(content, list):
                    content = "".join(item.get("text", "") for item in content if isinstance(item, dict))
                if content:
                    ai_output = content
                    break

            # 如果要求 JSON 输出，尝试解析
            if output_format == "json" and ai_output:
                try:
                    parsed = json.loads(ai_output)
                    return {"output": parsed}
                except json.JSONDecodeError:
                    # 尝试从文本中提取 JSON 块
                    import re

                    match = re.search(r"\{[\s\S]*\}", ai_output)
                    if match:
                        try:
                            parsed = json.loads(match.group())
                            return {"output": parsed}
                        except json.JSONDecodeError:
                            pass

            return {"output": ai_output}
        except Exception as e:
            logger.exception("Agent step 执行失败")
            return {"output": "", "error": str(e)}

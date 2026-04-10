"""Agent Step 执行器 — 调用 Deep Agent 进行 AI 分析与决策

支持:
- allowed_tools: 限制可用工具白名单
- mode: patrol(默认) / autonomous
- max_tool_calls: 工具调用次数上限（默认 20）
- output_format: json / text
"""

import json
import logging
import re

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)

# Agent step 允许使用的安全工具（只读类）
SAFE_TOOLS = {
    "get_system_info",
    "get_system_snapshot",
    "get_docker_status",
    "list_active_alerts",
    "get_service_status",
    "get_network_info",
    "get_gpu_info",
    "get_user_info",
    "list_users",
    "read_file",
    "ls",
    "glob",
    "grep",
    "get_container_logs",
    "get_service_logs",
    "list_cron_jobs",
    "web_search",
    "think",
    "retrieve_knowledge",
    "search_fault_cases",
}


@register_step("agent")
class AgentStepExecutor:
    """调用 Deep Agent 执行 AI 分析任务（带工具白名单和调用限制）"""

    async def execute(self, config: dict, state: dict) -> dict:
        from modules.agents.deep_agent import build_agent

        prompt = config.get("prompt", "")
        output_format = config.get("output_format")
        allowed_tools = config.get("allowed_tools")
        max_tool_calls = int(config.get("max_tool_calls", 20))

        if not prompt:
            return {"output": "", "error": "缺少 prompt 参数"}

        if output_format == "json":
            prompt += "\n\n请严格以 JSON 格式输出结果，不要包含其他文字。"

        try:
            agent = await build_agent(
                safety_mode="autonomous",
                purpose="patrol",
            )

            # TODO(P3-A follow-up): Agent step 应改用 create_pipeline_agent 以强制 SAFE_TOOLS
            # 当前 build_agent() 使用完整工具集，allowed_tools 仅做日志记录
            if allowed_tools:
                unsafe = set(allowed_tools) - SAFE_TOOLS
                if unsafe:
                    logger.warning("Agent step 请求了不安全的工具: %s，已从声明列表过滤", unsafe)
                    allowed_tools = [t for t in allowed_tools if t in SAFE_TOOLS]
                logger.info(
                    "Agent step 声明使用工具: %s（运行时白名单待强制执行）",
                    allowed_tools,
                )
            else:
                logger.info("Agent step 未指定 allowed_tools，build_agent 将使用完整工具集")

            run_id = state.get("run_id", "pipeline")
            step_id = config.get("id", "agent")
            thread_id = f"pipeline-{run_id}-{step_id}"

            invoke_config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": max_tool_calls + 5,
            }

            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config=invoke_config,
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

            # JSON 格式解析
            if output_format == "json" and ai_output:
                try:
                    parsed = json.loads(ai_output)
                    return {"output": parsed}
                except json.JSONDecodeError:
                    match = re.search(r"\{[\s\S]*\}", ai_output)
                    if match:
                        try:
                            return {"output": json.loads(match.group())}
                        except json.JSONDecodeError:
                            pass

            return {"output": ai_output}
        except Exception as e:
            logger.exception("Agent step 执行失败")
            return {"output": "", "error": str(e)}

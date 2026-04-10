"""Decision Step 执行器 — 多选项人类决策点

返回 requires_decision=True 信号，executor 检测后暂停运行、
发布 decision_request 事件、等待人类选择，然后路由到对应步骤。
"""

import json
import logging
import uuid

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("decision")
class DecisionStepExecutor:
    """多选项决策步骤 — 暂停等待人类选择后路由"""

    async def execute(self, config: dict, state: dict) -> dict:
        prompt = config.get("prompt", "请做出决策")
        options = config.get("options", [])
        timeout = int(config.get("timeout", 3600))
        on_timeout = config.get("on_timeout")
        assignee = config.get("assignee", "admin")
        context_from = config.get("context_from")

        if not options:
            return {"output": "", "error": "decision 步骤缺少 options 定义"}

        # 验证 options 格式
        for opt in options:
            if not opt.get("id") or not opt.get("label"):
                return {"output": "", "error": f"option 缺少 id 或 label: {opt}"}

        # 构建上下文（引用前序步骤输出）
        context = None
        if context_from:
            step_outputs = state.get("step_outputs", {})
            prev_output = step_outputs.get(context_from, {})
            context = json.dumps(prev_output, ensure_ascii=False, default=str)[:2000]

        decision_request_id = f"dr-{uuid.uuid4().hex[:12]}"

        return {
            "requires_decision": True,
            "decision_request_id": decision_request_id,
            "decision_prompt": prompt,
            "options": options,
            "context": context,
            "timeout": timeout,
            "on_timeout": on_timeout,
            "assignee": assignee,
            "output": f"等待 {assignee} 决策: {prompt}",
        }

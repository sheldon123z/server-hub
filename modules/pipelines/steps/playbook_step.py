"""Playbook Step 执行器 — 调用运维剧本执行引擎"""

import json
import logging

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("playbook")
class PlaybookStepExecutor:
    """执行已保存的运维剧本"""

    async def execute(self, config: dict, state: dict) -> dict:
        from modules.playbooks.services import execute_playbook

        playbook_id = config.get("playbook_id", "")
        params = config.get("params", {})
        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                return {"output": "", "error": "params JSON 格式错误"}

        if not playbook_id:
            return {"output": "", "error": "缺少 playbook_id 参数"}

        try:
            exec_id, status, report = await execute_playbook(
                playbook_id=playbook_id,
                parameters=params,
                triggered_by="pipeline",
                trigger_type="pipeline",
            )
            return {
                "output": report or f"剧本执行完成: {status}",
                "execution_id": exec_id,
                "status": status,
            }
        except Exception as e:
            logger.exception("Playbook step 执行失败: %s", playbook_id)
            return {"output": "", "error": str(e)}

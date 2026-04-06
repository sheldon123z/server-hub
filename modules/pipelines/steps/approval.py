"""Approval Step 执行器 — 人工审批节点，触发 LangGraph interrupt"""

import logging
import time

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("approval")
class ApprovalStepExecutor:
    """人工审批节点 — 写入审批请求到数据库并返回中断标记

    编排引擎在遇到 approval step 时使用 LangGraph interrupt_before 机制暂停，
    此执行器负责创建审批记录并返回等待标记。
    """

    async def execute(self, config: dict, state: dict) -> dict:
        from database import get_db

        run_id = state.get("run_id", "")
        step_id = config.get("id", "approval")
        assignee = config.get("assignee", "admin")
        timeout = int(config.get("timeout", 3600))
        on_timeout = config.get("on_timeout", "abort")

        try:
            db = await get_db()
            await db.execute(
                """INSERT OR REPLACE INTO pipeline_step_logs
                   (run_id, step_id, step_type, status, input_json, started_at)
                   VALUES (?, ?, 'approval', 'waiting_approval', ?, datetime('now'))""",
                (
                    run_id,
                    step_id,
                    f'{{"assignee":"{assignee}","timeout":{timeout},"on_timeout":"{on_timeout}"}}',
                ),
            )
            await db.commit()
        except Exception:
            logger.exception("写入审批记录失败")

        return {
            "output": f"等待 {assignee} 审批",
            "requires_approval": True,
            "assignee": assignee,
            "timeout": timeout,
            "on_timeout": on_timeout,
            "requested_at": time.time(),
        }

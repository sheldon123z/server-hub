"""Pipeline 专属工具 — 只在 PipelineAgent 上下文中可用

提供步骤输出查询和运行概要能力，让 AI 能感知当前 Pipeline 执行状态。
"""

import json
import logging

from langchain_core.tools import tool

from database import get_db

logger = logging.getLogger(__name__)


@tool
async def get_pipeline_step_output(run_id: str, step_id: str) -> str:
    """获取指定运行中指定步骤的执行输出内容。

    Args:
        run_id: 运行实例 ID
        step_id: 步骤 ID（如 "check-connectivity", "install-docker"）

    Returns:
        步骤输出的 JSON 字符串，包含 status/output/error/duration_ms
    """
    db = await get_db()
    row = await db.execute_fetchone(
        "SELECT step_id, step_type, status, output_json, error, duration_ms "
        "FROM pipeline_step_logs WHERE run_id = ? AND step_id = ? ORDER BY started_at DESC LIMIT 1",
        (run_id, step_id),
    )
    if not row:
        return json.dumps({"error": f"未找到运行 {run_id} 中步骤 {step_id} 的执行记录"}, ensure_ascii=False)

    result = dict(row)
    if result.get("output_json"):
        try:
            result["output"] = json.loads(result["output_json"])
        except (json.JSONDecodeError, TypeError):
            result["output"] = result["output_json"]
    result.pop("output_json", None)
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
async def get_pipeline_run_summary(run_id: str) -> str:
    """获取当前运行的全局概要：所有步骤状态 + 输出摘要。

    Args:
        run_id: 运行实例 ID

    Returns:
        运行概要的 JSON 字符串
    """
    db = await get_db()
    run_row = await db.execute_fetchone(
        "SELECT id, pipeline_id, status, current_step_id, error, started_at, completed_at "
        "FROM pipeline_runs WHERE id = ?",
        (run_id,),
    )
    if not run_row:
        return json.dumps({"error": f"未找到运行 {run_id}"}, ensure_ascii=False)

    run_info = dict(run_row)
    rows = await db.execute_fetchall(
        "SELECT step_id, step_type, status, duration_ms, error "
        "FROM pipeline_step_logs WHERE run_id = ? ORDER BY started_at",
        (run_id,),
    )
    steps = []
    for r in rows:
        step = dict(r)
        if step.get("error") and len(step["error"]) > 200:
            step["error"] = step["error"][:200] + "..."
        steps.append(step)

    run_info["steps"] = steps
    run_info["total_steps"] = len(steps)
    run_info["completed_steps"] = sum(1 for s in steps if s["status"] == "completed")
    run_info["failed_steps"] = sum(1 for s in steps if s["status"] == "failed")

    return json.dumps(run_info, ensure_ascii=False, default=str)


@tool
def request_human_intervention(
    prompt: str,
    options: list[dict],
    timeout_seconds: int = 3600,
) -> str:
    """请求人类介入决策。Pipeline 将暂停直到人类做出选择。

    Args:
        prompt: 决策描述（展示给运维人员）
        options: 选项列表，每项包含 {id, label, description}
        timeout_seconds: 超时秒数（默认 3600）

    Returns:
        人类选择的选项 ID
    """
    from langgraph.types import interrupt

    result = interrupt(
        {
            "type": "decision",
            "prompt": prompt,
            "options": options,
            "timeout": timeout_seconds,
        }
    )
    return result


def get_pipeline_tools() -> list:
    """返回 pipeline 专属工具列表"""
    return [get_pipeline_step_output, get_pipeline_run_summary, request_human_intervention]

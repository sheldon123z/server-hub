"""Parallel Step 执行器 — 并行分支汇合（join）函数

并行 step 的 Send() 逻辑在编译器 (compiler.py) 中处理，
此模块提供分支结果合并功能。
"""

import logging

from modules.pipelines.steps import register_step

logger = logging.getLogger(__name__)


@register_step("parallel")
class ParallelStepExecutor:
    """汇合并行分支输出 — 合并所有分支的结果"""

    async def execute(self, config: dict, state: dict) -> dict:
        branches = config.get("branches", [])
        step_outputs = state.get("step_outputs", {})

        merged: dict = {}
        errors: list[str] = []
        all_success = True

        for branch in branches:
            branch_id = branch.get("id", "")
            if not branch_id:
                continue

            branch_output = step_outputs.get(branch_id, {})
            merged[branch_id] = branch_output

            # 检查分支是否有错误
            if branch_output.get("error"):
                errors.append(f"{branch_id}: {branch_output['error']}")
                all_success = False
            elif branch_output.get("exit_code", 0) != 0:
                all_success = False

        result = {
            "output": merged,
            "all_success": all_success,
            "branch_count": len(branches),
        }
        if errors:
            result["errors"] = errors
        return result

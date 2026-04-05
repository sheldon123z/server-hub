"""技能评测引擎 — A/B 对比评测 + Assertion 检查 + 触发率测试

提供三个核心函数:
  run_skill_eval()    — 对技能执行有/无技能上下文的 A/B 对比评测
  check_assertion()   — 5 种 check 语法的断言检查器
  check_trigger_rate() — description 触发准确率测试 (precision/recall)
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Assertion 检查器
# ---------------------------------------------------------------------------


def check_assertion(assertion: dict, tool_calls: list[dict], output: str) -> bool:
    """检查单个断言是否通过。

    Args:
        assertion: {"name": "...", "check": "check_type:value"}
        tool_calls: [{"name": "tool_name", "args": {...}}, ...]
        output: agent 最终输出文本

    Returns:
        True 表示断言通过

    支持 5 种 check 语法:
      - tool_used:工具名
      - output_contains:关键词|关键词
      - output_not_contains:关键词
      - subagent_used:子智能体名
      - status:ok|warning|critical
    """
    check = assertion.get("check", "")
    if ":" not in check:
        logger.warning("无效的 assertion check 语法: %s", check)
        return False

    check_type, value = check.split(":", 1)

    if check_type == "tool_used":
        return any(tc.get("name") == value for tc in tool_calls)

    if check_type == "output_contains":
        keywords = value.split("|")
        pattern = "|".join(re.escape(kw) for kw in keywords)
        return bool(re.search(pattern, output))

    if check_type == "output_not_contains":
        keywords = value.split("|")
        pattern = "|".join(re.escape(kw) for kw in keywords)
        return not bool(re.search(pattern, output))

    if check_type == "subagent_used":
        # SubAgent 委派通过 task 工具调用，agent_name 在 args 中
        for tc in tool_calls:
            if tc.get("name") == "task":
                args = tc.get("args", {})
                agent_name = args.get("agent") or args.get("agent_name") or ""
                if agent_name == value:
                    return True
        return False

    if check_type == "status":
        expected_statuses = {s.strip() for s in value.split("|")}
        # 尝试从输出中提取 JSON 块并匹配 status 字段
        json_blocks = re.findall(r"\{[^{}]*\}", output)
        for block in json_blocks:
            try:
                data = json.loads(block)
                if data.get("status") in expected_statuses:
                    return True
            except (json.JSONDecodeError, TypeError):
                continue
        # 也检查纯文本中的 status 关键词
        return any(s in output.lower() for s in expected_statuses)

    logger.warning("未知的 assertion check 类型: %s", check_type)
    return False


# ---------------------------------------------------------------------------
# 内部辅助: 执行单次 agent 调用并收集结果
# ---------------------------------------------------------------------------


def _extract_content(content: Any) -> str:
    """统一提取 AIMessage.content — 可能是 str 或 list[dict]"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content) if content else ""


async def _run_single_eval(
    prompt: str,
    *,
    skill_context: str | None = None,
) -> dict[str, Any]:
    """执行单次 agent 调用，收集 tool_calls、output、tokens、duration。

    使用临时 thread_id，不创建真实对话记录。

    Args:
        prompt: 用户提示词
        skill_context: 可选的技能上下文（SKILL.md 全文），注入后 agent 会遵循技能工作流

    Returns:
        {
            "tool_calls": [{"name": ..., "args": ...}, ...],
            "output": "最终输出文本",
            "tokens_used": int,
            "duration_ms": int,
        }
    """
    from langchain_core.messages import AIMessage, ToolMessage

    from modules.agents.deep_agent import build_agent

    agent = await build_agent(safety_mode="autonomous", purpose="chat", user_role="admin")
    thread_id = f"eval-{uuid.uuid4().hex[:12]}"
    config = {"configurable": {"thread_id": thread_id}}

    input_messages = []
    if skill_context:
        input_messages.append({"role": "system", "content": skill_context})
    input_messages.append({"role": "user", "content": prompt})

    tool_calls_collected: list[dict] = []
    final_output = ""
    emitted_ids: set[str] = set()

    start_time = time.monotonic()

    try:
        async for step in agent.astream(
            {"messages": input_messages},
            config,
            stream_mode="values",
        ):
            messages = step.get("messages", [])
            for msg in messages:
                msg_id = getattr(msg, "id", None)
                if msg_id and msg_id in emitted_ids:
                    continue
                if msg_id:
                    emitted_ids.add(msg_id)

                if isinstance(msg, AIMessage):
                    if getattr(msg, "tool_calls", None):
                        for tc in msg.tool_calls:
                            tc_id = tc.get("id", "")
                            if tc_id and tc_id in emitted_ids:
                                continue
                            if tc_id:
                                emitted_ids.add(tc_id)
                            tool_calls_collected.append(
                                {
                                    "name": tc.get("name", ""),
                                    "args": tc.get("args", {}),
                                }
                            )
                    elif msg.content:
                        final_output = _extract_content(msg.content)

                elif isinstance(msg, ToolMessage):
                    pass  # 工具结果不计入最终输出

    except Exception as exc:
        logger.error("评测执行出错: %s", exc)
        final_output = f"[评测执行出错: {exc}]"

    duration_ms = int((time.monotonic() - start_time) * 1000)

    # 估算 token 使用量 — 基于输出长度的粗略估算
    # 实际 token 数需要从 LLM 回调中获取，这里用字符数 / 2 近似
    tokens_estimate = (len(final_output) + sum(len(str(tc)) for tc in tool_calls_collected)) // 2

    return {
        "tool_calls": tool_calls_collected,
        "output": final_output,
        "tokens_used": tokens_estimate,
        "duration_ms": duration_ms,
    }


# ---------------------------------------------------------------------------
# 核心: 技能评测
# ---------------------------------------------------------------------------


async def run_skill_eval(
    skill_id: str,
    eval_id: int | None = None,
    mode: str = "ab",
) -> dict[str, Any]:
    """执行技能评测。

    Args:
        skill_id: 技能 ID
        eval_id: 可选，只运行指定 ID 的测试用例
        mode: "ab" = 有/无技能对比, "skill_only" = 仅有技能

    Returns:
        {
            "skill_id": str,
            "mode": str,
            "results": [
                {
                    "eval_id": int,
                    "prompt": str,
                    "with_skill": {
                        "tool_calls": [...],
                        "output": str,
                        "tokens_used": int,
                        "duration_ms": int,
                        "assertions": [{"name": ..., "passed": bool}, ...],
                        "pass_rate": float,
                    },
                    "without_skill": { ... } | None,
                }
            ],
            "summary": {
                "total": int,
                "with_skill_pass_rate": float,
                "without_skill_pass_rate": float | None,
                "improvement": float | None,
            },
            "trigger_eval": { ... } | None,
        }
    """
    from modules.agents.skill_service import get_skill, load_skill_context

    # 加载评测用例
    skill = await get_skill(skill_id)
    if not skill:
        raise ValueError(f"技能 {skill_id} 不存在")

    install_path = Path(skill["install_path"])
    evals_path = install_path / "evals" / "evals.json"
    if not evals_path.exists():
        raise FileNotFoundError(f"评测文件不存在: {evals_path}")

    evals_data = json.loads(evals_path.read_text(encoding="utf-8"))
    eval_cases: list[dict] = evals_data.get("evals", [])
    trigger_evals: list[dict] = evals_data.get("trigger_evals", [])

    if eval_id is not None:
        eval_cases = [c for c in eval_cases if c.get("id") == eval_id]
        if not eval_cases:
            raise ValueError(f"未找到 eval_id={eval_id} 的测试用例")

    # 加载技能上下文
    skill_context = await load_skill_context(skill_id)

    results: list[dict] = []
    with_skill_passed = 0
    with_skill_total_assertions = 0
    without_skill_passed = 0
    without_skill_total_assertions = 0

    for case in eval_cases:
        prompt = case["prompt"]
        assertions = case.get("assertions", [])
        case_result: dict[str, Any] = {
            "eval_id": case["id"],
            "prompt": prompt,
            "expected_behavior": case.get("expected_behavior", ""),
        }

        # --- with_skill ---
        logger.info("评测 [%s] eval_id=%d with_skill 开始", skill_id, case["id"])
        ws_result = await _run_single_eval(prompt, skill_context=skill_context)
        ws_assertions = []
        for a in assertions:
            passed = check_assertion(a, ws_result["tool_calls"], ws_result["output"])
            ws_assertions.append({"name": a["name"], "check": a["check"], "passed": passed})
            with_skill_total_assertions += 1
            if passed:
                with_skill_passed += 1

        ws_pass_rate = sum(1 for a in ws_assertions if a["passed"]) / len(ws_assertions) if ws_assertions else 0.0
        case_result["with_skill"] = {
            **ws_result,
            "assertions": ws_assertions,
            "pass_rate": round(ws_pass_rate, 4),
        }

        # --- without_skill (A/B 模式) ---
        if mode == "ab":
            logger.info("评测 [%s] eval_id=%d without_skill 开始", skill_id, case["id"])
            wos_result = await _run_single_eval(prompt, skill_context=None)
            wos_assertions = []
            for a in assertions:
                passed = check_assertion(a, wos_result["tool_calls"], wos_result["output"])
                wos_assertions.append({"name": a["name"], "check": a["check"], "passed": passed})
                without_skill_total_assertions += 1
                if passed:
                    without_skill_passed += 1

            wos_pass_rate = (
                sum(1 for a in wos_assertions if a["passed"]) / len(wos_assertions) if wos_assertions else 0.0
            )
            case_result["without_skill"] = {
                **wos_result,
                "assertions": wos_assertions,
                "pass_rate": round(wos_pass_rate, 4),
            }
        else:
            case_result["without_skill"] = None

        results.append(case_result)

    # 汇总
    ws_overall = round(with_skill_passed / with_skill_total_assertions, 4) if with_skill_total_assertions else 0.0
    wos_overall = (
        round(without_skill_passed / without_skill_total_assertions, 4) if without_skill_total_assertions else None
    )
    improvement = round(ws_overall - wos_overall, 4) if wos_overall is not None else None

    summary: dict[str, Any] = {
        "total": len(results),
        "with_skill_pass_rate": ws_overall,
        "without_skill_pass_rate": wos_overall,
        "improvement": improvement,
    }

    # 触发率测试（如有）
    trigger_result = None
    if trigger_evals:
        trigger_result = await check_trigger_rate(skill_id, trigger_evals)

    return {
        "skill_id": skill_id,
        "mode": mode,
        "results": results,
        "summary": summary,
        "trigger_eval": trigger_result,
    }


# ---------------------------------------------------------------------------
# 触发率测试
# ---------------------------------------------------------------------------


async def check_trigger_rate(
    skill_id: str,
    trigger_evals: list[dict],
) -> dict[str, Any]:
    """测试 description 触发准确率。

    Args:
        skill_id: 目标技能 ID
        trigger_evals: [{"query": "...", "should_trigger": true/false}, ...]

    Returns:
        {
            "precision": float,
            "recall": float,
            "f1": float,
            "details": [
                {"query": "...", "should_trigger": bool, "triggered": bool, "correct": bool, "rank": int|null}
            ]
        }
    """
    from modules.agents.skill_service import recommend_skills

    details: list[dict] = []
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0

    for case in trigger_evals:
        query = case["query"]
        should_trigger = case["should_trigger"]

        try:
            recommendations = await recommend_skills(message=query, user_role="admin", limit=3)
        except Exception as exc:
            logger.warning("触发率测试 recommend_skills 失败: %s", exc)
            recommendations = []

        recommended_ids = [r["id"] for r in recommendations]
        triggered = skill_id in recommended_ids
        rank = recommended_ids.index(skill_id) + 1 if triggered else None
        correct = triggered == should_trigger

        details.append(
            {
                "query": query,
                "should_trigger": should_trigger,
                "triggered": triggered,
                "correct": correct,
                "rank": rank,
            }
        )

        if should_trigger and triggered:
            true_positives += 1
        elif should_trigger and not triggered:
            false_negatives += 1
        elif not should_trigger and triggered:
            false_positives += 1
        else:
            true_negatives += 1

    precision = (
        round(true_positives / (true_positives + false_positives), 4) if (true_positives + false_positives) > 0 else 0.0
    )
    recall = (
        round(true_positives / (true_positives + false_negatives), 4) if (true_positives + false_negatives) > 0 else 0.0
    )
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "details": details,
    }

"""故障自动分析工作流 — critical 告警触发自动诊断"""

import json
import logging
import re
import time
import uuid
from datetime import datetime

from database import get_db

logger = logging.getLogger(__name__)

DIAGNOSIS_PROMPT = """你是 ServerHub 故障诊断专家。系统检测到以下严重告警，请进行根因分析。

## 告警信息
- 来源: {source}
- 严重级别: {severity}
- 告警内容: {alert_context}

## 诊断步骤
1. 首先调用相关工具收集当前系统状态
2. 使用 task() 委派 log-analyzer 分析相关服务日志
3. 根据收集到的证据，分析根本原因
4. 给出紧急处置建议和长期修复方案

## 输出格式
在分析完成后，输出如下 JSON（用 ```json 包裹）：

```json
{{
  "affected_components": ["受影响的组件列表"],
  "symptoms": ["观察到的症状列表"],
  "root_cause": "根本原因分析",
  "evidence": ["支持根因判断的证据，如日志片段"],
  "immediate_actions": ["紧急处置步骤"],
  "long_term_solutions": ["长期修复方案"]
}}
```
"""


def _parse_diagnosis_report(report_text: str) -> dict | None:
    """从诊断报告中提取结构化 JSON"""
    pattern = r"```json\s*\n?(.*?)\n?\s*```"
    matches = re.findall(pattern, report_text, re.DOTALL)
    for match in reversed(matches):
        try:
            data = json.loads(match)
            if "root_cause" in data:
                return data
        except (json.JSONDecodeError, ValueError):
            continue
    return None


async def trigger_diagnosis(source: str, severity: str, alert_context: str):
    """
    触发自动故障诊断。

    Args:
        source: 告警来源（如 patrol task ID 或 alert rule ID）
        severity: 严重级别
        alert_context: 告警上下文描述
    """
    report_id = str(uuid.uuid4())
    logger.info(f"触发故障诊断: source={source}, severity={severity}")

    try:
        from modules.agents.deep_agent import build_agent

        agent = await build_agent(safety_mode="autonomous", purpose="patrol")
        thread_id = f"diagnosis-{report_id}"
        config = {"configurable": {"thread_id": thread_id}}

        prompt = DIAGNOSIS_PROMPT.format(
            source=source,
            severity=severity,
            alert_context=alert_context,
        )

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": prompt}]},
            config=config,
        )

        # 提取 AI 响应
        report_text = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "content") and not hasattr(msg, "tool_call_id"):
                report_text = msg.content
                break

        # 解析结构化报告
        parsed = _parse_diagnosis_report(report_text)

        db = await get_db()
        if parsed:
            await db.execute(
                "INSERT INTO fault_reports (id, source, severity, affected_components, symptoms, "
                "root_cause, evidence, immediate_actions, long_term_solutions, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')",
                (
                    report_id, source, severity,
                    json.dumps(parsed.get("affected_components", []), ensure_ascii=False),
                    json.dumps(parsed.get("symptoms", []), ensure_ascii=False),
                    parsed.get("root_cause", ""),
                    json.dumps(parsed.get("evidence", []), ensure_ascii=False),
                    json.dumps(parsed.get("immediate_actions", []), ensure_ascii=False),
                    json.dumps(parsed.get("long_term_solutions", []), ensure_ascii=False),
                ),
            )
        else:
            # JSON 解析失败，存原始文本
            await db.execute(
                "INSERT INTO fault_reports (id, source, severity, root_cause, status) VALUES (?, ?, ?, ?, 'open')",
                (report_id, source, severity, report_text[:3000]),
            )
        await db.commit()

        # 自动录入案例库
        if parsed and parsed.get("root_cause"):
            try:
                symptoms_text = "; ".join(parsed.get("symptoms", []))
                solutions_text = "; ".join(parsed.get("immediate_actions", []) + parsed.get("long_term_solutions", []))
                # 从 source 推断分类
                category = "general"
                source_lower = (source + " " + alert_context).lower()
                for cat, kws in [("memory", ["内存","memory","swap"]), ("docker", ["docker","容器","container"]),
                                 ("gpu", ["gpu","显存","温度"]), ("service", ["服务","service","systemd"]),
                                 ("network", ["网络","端口","port","firewall"]), ("security", ["安全","ssh","权限"])]:
                    if any(k in source_lower for k in kws):
                        category = cat
                        break

                cursor = await db.execute(
                    "INSERT INTO fault_cases (title, category, symptoms, root_cause, solution, tags, source, source_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'auto', ?)",
                    (f"[自动] {parsed['root_cause'][:60]}", category, symptoms_text[:500],
                     parsed["root_cause"][:1000], solutions_text[:1000], f"{severity},{category}", report_id),
                )
                case_id = cursor.lastrowid
                try:
                    await db.execute(
                        "INSERT INTO fault_cases_fts(rowid, title, symptoms, root_cause, solution, tags) VALUES (?, ?, ?, ?, ?, ?)",
                        (case_id, f"[自动] {parsed['root_cause'][:60]}", symptoms_text[:500],
                         parsed["root_cause"][:1000], solutions_text[:1000], f"{severity},{category}"),
                    )
                except Exception:
                    pass
                await db.commit()
            except Exception as e:
                logger.error(f"自动录入案例库失败: {e}")

        # 发送 Telegram 摘要
        try:
            from modules.notifications.services import send_telegram
            if parsed:
                summary = (
                    f"🔍 故障诊断报告\n"
                    f"来源: {source}\n"
                    f"根因: {parsed.get('root_cause', '未知')[:200]}\n"
                    f"紧急处置: {'; '.join(parsed.get('immediate_actions', []))[:300]}"
                )
            else:
                summary = f"🔍 故障诊断完成 (来源: {source})\n{report_text[:400]}"
            await send_telegram(summary[:1000])
        except Exception:
            pass

        logger.info(f"故障诊断完成: {report_id}")
        return report_id

    except Exception as e:
        logger.error(f"故障诊断失败: {e}", exc_info=True)
        # 记录失败
        try:
            db = await get_db()
            await db.execute(
                "INSERT INTO fault_reports (id, source, severity, root_cause, status) VALUES (?, ?, ?, ?, 'open')",
                (report_id, source, severity, f"诊断执行失败: {e}"),
            )
            await db.commit()
        except Exception:
            pass
        return None

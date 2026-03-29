"""巡检报告结构化 Schema + 解析工具"""

import json
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# ─── 严重程度等级（从低到高） ───

SEVERITY_ORDER = {
    "info": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}

# severity → 巡检状态映射
SEVERITY_TO_STATUS = {
    "info": "ok",
    "low": "ok",
    "medium": "warning",
    "high": "warning",
    "critical": "critical",
}


def parse_patrol_report(raw_report: str) -> dict | None:
    """
    从 LLM 巡检报告中提取结构化 JSON。

    查找策略（优先级递减）：
    1. ```json ... ``` 代码块
    2. 最后一个 {...} JSON 对象
    3. 返回 None（回退到关键字匹配）
    """
    # 策略 1: 找 ```json 代码块
    pattern = r"```json\s*\n?(.*?)\n?\s*```"
    matches = re.findall(pattern, raw_report, re.DOTALL)
    for match in reversed(matches):
        try:
            data = json.loads(match)
            if _validate_report(data):
                return _normalize_report(data)
        except (json.JSONDecodeError, ValueError):
            continue

    # 策略 2: 找最后一个大括号包裹的 JSON
    brace_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
    brace_matches = re.findall(brace_pattern, raw_report, re.DOTALL)
    for match in reversed(brace_matches):
        try:
            data = json.loads(match)
            if _validate_report(data):
                return _normalize_report(data)
        except (json.JSONDecodeError, ValueError):
            continue

    return None


def _validate_report(data: dict) -> bool:
    """验证 JSON 是否符合报告 schema（宽松检查）"""
    if not isinstance(data, dict):
        return False
    # 至少要有 check_items 或 status
    return "check_items" in data or "status" in data


def _normalize_report(data: dict) -> dict:
    """规范化报告字段"""
    report = {
        "summary": data.get("summary", ""),
        "status": data.get("status", "ok"),
        "check_items": [],
        "metrics_snapshot": data.get("metrics_snapshot", {}),
        "generated_at": data.get("generated_at", datetime.now().isoformat()),
    }

    for item in data.get("check_items", []):
        if not isinstance(item, dict):
            continue
        report["check_items"].append(
            {
                "name": item.get("name", "未命名检查项"),
                "status": item.get("status", "pass"),
                "severity": item.get("severity", "info"),
                "current_value": str(item.get("current_value", "")),
                "threshold": str(item.get("threshold", "")),
                "detail": item.get("detail", ""),
                "recommendation": item.get("recommendation", ""),
            }
        )

    # 根据 check_items 重新计算 status
    if report["check_items"]:
        max_severity = (
            max(SEVERITY_ORDER.get(item["severity"], 0) for item in report["check_items"] if item["status"] != "pass")
            if any(item["status"] != "pass" for item in report["check_items"])
            else 0
        )

        for sev, order in SEVERITY_ORDER.items():
            if order == max_severity:
                report["status"] = SEVERITY_TO_STATUS.get(sev, "ok")
                break

    return report


def determine_status_from_text(report_text: str) -> str:
    """
    后备方案：当 JSON 解析失败时，用关键字匹配判断状态。
    改进版：更精细的关键字分级。
    """
    critical_keywords = ["严重", "紧急", "critical", "危险", "立即处理"]
    warning_keywords = ["告警", "异常", "超过", "警告", "warning", "注意", "偏高"]

    text_lower = report_text.lower()
    if any(w in text_lower for w in critical_keywords):
        return "critical"
    if any(w in text_lower for w in warning_keywords):
        return "warning"
    return "ok"


def report_summary_text(report_json: dict) -> str:
    """将结构化报告转为告警通知用的摘要文本"""
    lines = []
    status_emoji = {"ok": "✅", "warning": "⚠️", "critical": "🚨"}.get(report_json.get("status", "ok"), "ℹ️")
    lines.append(f"{status_emoji} {report_json.get('summary', '巡检完成')}")

    fail_items = [item for item in report_json.get("check_items", []) if item.get("status") != "pass"]
    if fail_items:
        lines.append("")
        for item in fail_items:
            sev = item.get("severity", "info").upper()
            lines.append(
                f"[{sev}] {item['name']}: {item.get('current_value', '')} (阈值: {item.get('threshold', 'N/A')})"
            )
            if item.get("recommendation"):
                lines.append(f"  → {item['recommendation']}")

    return "\n".join(lines)

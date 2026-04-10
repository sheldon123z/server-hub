"""Pipeline AI 辅助服务 — 生成/修改/审查 YAML

不使用 PipelineAgent（那是运行时顾问）。
直接调用 LLM，注入动态 Pipeline schema 知识。
"""

import json
import logging
import re
from typing import get_args

import yaml

from modules.agents.llm import get_chat_model
from modules.pipelines.models import STEP_TYPES
from modules.pipelines.services import validate_pipeline_yaml
from modules.pipelines.templates import get_builtin_templates

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 动态 Schema 构建
# ---------------------------------------------------------------------------

_STEP_TYPE_DOCS = {
    "shell": "执行 Shell 命令\n  command: '...'  # 必填\n  timeout: 300",
    "ssh": "SSH 远程执行\n  host: '{{params.target_server}}'  # 必填\n  username: 'root'\n  command: '...'  # 必填",
    "agent": "AI 分析（只读）\n  prompt: '...'  # 必填\n  output_format: json | text\n  max_tool_calls: 20",
    "approval": "人工审批\n  assignee: admin\n  timeout: 3600",
    "decision": "人工决策（多选项路由）\n  prompt: '...'  # 必填\n  context_from: step-id\n  options:\n    - id: option-id\n      label: 显示文本\n      description: 描述\n      next_step: target-step-id\n  timeout: 3600\n  on_timeout: default-option-id",
    "condition": "条件分支\n  expression: '...'  # 必填\n  on_true: target-step-id\n  on_false: target-step-id",
    "parallel": "并行执行\n  branches:  # 必填\n    - id: branch-1\n      type: shell\n      command: '...'",
    "http": "HTTP 请求\n  url: '...'  # 必填\n  method: GET | POST | PUT | DELETE\n  headers: {}\n  body: {}",
    "notify": "发送通知\n  channel: telegram | email | webhook\n  message: '...'",
    "delay": "延迟等待\n  seconds: 60",
    "playbook": "执行 Playbook\n  playbook_id: '...'\n  params: {}",
}


def _build_step_schema() -> str:
    """从 STEP_TYPES 动态构建步骤类型文档"""
    lines = []
    for st in get_args(STEP_TYPES):
        doc = _STEP_TYPE_DOCS.get(st, f"{st} — 详见文档")
        lines.append(f"#### {st} — {doc}")
    return "\n\n".join(lines)


def _build_system_prompt() -> str:
    step_schema = _build_step_schema()
    step_count = len(get_args(STEP_TYPES))
    return f"""你是 ServerHub Pipeline YAML 生成助手。

## Pipeline YAML Schema

### 顶层结构
name: 唯一标识（英文、连字符）
display_name: 中文显示名
description: 描述
version: 1
max_concurrent_runs: 1
timeout: 3600
trigger:
  type: manual | cron | alert | api
  cron: "0 8 * * *"
  alert_rule_id: "..."
params:
  - name: 参数名
    type: string | number | boolean | array | secret
    required: true
    default: 默认值
    description: 描述

### 步骤类型（当前支持 {step_count} 种）

{step_schema}

### 模板变量
{{{{params.xxx}}}} — 运行参数
{{{{steps.xxx.output}}}} — 步骤输出
{{{{steps.xxx.exit_code}}}} — 退出码
{{{{run.id}}}} — 运行 ID

### on_failure 策略
abort (默认) | skip | notify_continue | goto:{{step_id}}

## 生成规则
1. 每个步骤必须有唯一 id（英文、连字符）
2. condition/decision 的目标必须引用有效的 step id
3. 关键操作前建议添加 approval 或 decision 步骤
4. shell 命令建议设置 timeout
5. agent 步骤的 prompt 要具体明确
6. 输出纯 YAML，不要包含 markdown 代码块标记
"""


# ---------------------------------------------------------------------------
# 模板选择器
# ---------------------------------------------------------------------------

_TEMPLATE_KEYWORDS = {
    "server-init": ["初始化", "部署", "上架", "安装", "配置"],
    "auto-heal": ["故障", "修复", "自愈", "告警", "恢复"],
    "daily-patrol": ["巡检", "监控", "检查", "定时", "日常"],
    "security-scan": ["安全", "扫描", "漏洞", "审计", "合规"],
}


def _select_templates(description: str) -> list[dict]:
    """根据描述选择最相关的 1-2 个模板"""
    templates = get_builtin_templates()
    scores = {}
    for tmpl in templates:
        kws = _TEMPLATE_KEYWORDS.get(tmpl["id"], [])
        scores[tmpl["id"]] = sum(1 for kw in kws if kw in description)

    sorted_ids = sorted(scores, key=scores.get, reverse=True)
    selected = [tid for tid in sorted_ids[:2] if scores[tid] > 0]
    if not selected:
        selected = ["daily-patrol"]

    return [t for t in templates if t["id"] in selected]


# ---------------------------------------------------------------------------
# 安全策略验证
# ---------------------------------------------------------------------------

_STEP_SECURITY = {
    "shell": {"level": "privileged", "needs_approval": True},
    "ssh": {"level": "privileged", "needs_approval": True},
    "http": {"level": "moderate", "needs_approval": False},
    "playbook": {"level": "moderate", "needs_approval": False},
    "agent": {"level": "safe", "needs_approval": False},
    "approval": {"level": "safe", "needs_approval": False},
    "decision": {"level": "safe", "needs_approval": False},
    "condition": {"level": "safe", "needs_approval": False},
    "parallel": {"level": "safe", "needs_approval": False},
    "notify": {"level": "safe", "needs_approval": False},
    "delay": {"level": "safe", "needs_approval": False},
}


def _validate_security(parsed: dict) -> dict:
    """结构化安全策略验证（递归检查 parallel branches）"""
    issues = []
    level = "safe"

    def _check_steps(steps: list[dict], approval_seen: bool = False):
        nonlocal level
        for step in steps:
            st = step.get("type", "")
            policy = _STEP_SECURITY.get(st)
            if not policy:
                issues.append({"severity": "error", "step_id": step.get("id"), "message": f"未知步骤类型: {st}"})
                continue

            # 递归检查 parallel branches
            if st == "parallel":
                for branch in step.get("branches", []):
                    _check_steps([branch], approval_seen)
                continue

            # 更新 approval 可见状态
            if st in ("approval", "decision"):
                approval_seen = True

            if policy["needs_approval"] and not approval_seen:
                issues.append(
                    {
                        "severity": "warning",
                        "step_id": step.get("id"),
                        "message": f"{st} 步骤前没有 approval/decision 步骤，建议添加",
                    }
                )
                level = "needs_approval"

    _check_steps(parsed.get("steps", []))
    return {"security_level": level, "issues": issues}


# ---------------------------------------------------------------------------
# YAML 提取
# ---------------------------------------------------------------------------


def _extract_yaml(response: str) -> str:
    """从 LLM 响应中提取纯 YAML"""
    match = re.search(r"```ya?ml\s*\n(.*?)```", response, re.DOTALL)
    if match:
        return match.group(1).strip()
    try:
        yaml.safe_load(response)
        return response.strip()
    except yaml.YAMLError:
        pass
    lines = response.split("\n")
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("name:")), 0)
    return "\n".join(lines[start:]).strip()


def _extract_explanation(response: str) -> str:
    """提取 YAML 之外的说明文字"""
    match = re.search(r"```ya?ml\s*\n.*?```\s*(.*)", response, re.DOTALL)
    if match:
        return match.group(1).strip()[:500]
    return ""


# ---------------------------------------------------------------------------
# 核心 API
# ---------------------------------------------------------------------------


async def generate_pipeline(description: str, hints: dict | None = None) -> dict:
    """从自然语言生成 Pipeline YAML"""
    model = get_chat_model("chat")
    system = _build_system_prompt()

    # 注入相关模板作为 few-shot
    templates = _select_templates(description)
    examples = ""
    for t in templates:
        examples += f"\n\n## 参考模板: {t['display_name']}\n```yaml\n{t['yaml_content']}\n```"

    user_prompt = f"请根据以下需求生成 Pipeline YAML:\n\n{description}"
    if hints:
        user_prompt += f"\n\n提示: {json.dumps(hints, ensure_ascii=False)}"
    if examples:
        user_prompt += f"\n\n以下是类似的模板供参考:{examples}\n\n请生成新的 YAML（不要复制模板）:"

    response = await model.ainvoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
    )
    content = response.content if isinstance(response.content, str) else str(response.content)

    yaml_content = _extract_yaml(content)
    validation = await validate_pipeline_yaml(yaml_content)

    # 安全策略验证
    security = {"security_level": "safe", "issues": []}
    try:
        parsed = yaml.safe_load(yaml_content)
        if isinstance(parsed, dict):
            security = _validate_security(parsed)
    except yaml.YAMLError:
        pass

    return {
        "yaml_content": yaml_content,
        "validation": validation,
        "security": security,
        "explanation": _extract_explanation(content),
    }


async def modify_pipeline(yaml_content: str, instruction: str) -> dict:
    """基于指令修改现有 YAML"""
    model = get_chat_model("chat")
    system = _build_system_prompt()

    user_prompt = f"""现有 Pipeline YAML:
```yaml
{yaml_content}
```

修改指令: {instruction}

请输出修改后的完整 YAML。在 YAML 之后简要列出改动点。"""

    response = await model.ainvoke(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ]
    )
    content = response.content if isinstance(response.content, str) else str(response.content)

    new_yaml = _extract_yaml(content)
    validation = await validate_pipeline_yaml(new_yaml)

    security = {"security_level": "safe", "issues": []}
    try:
        parsed = yaml.safe_load(new_yaml)
        if isinstance(parsed, dict):
            security = _validate_security(parsed)
    except yaml.YAMLError:
        pass

    # 提取改动摘要
    changes = []
    explanation = _extract_explanation(content)
    for line in explanation.split("\n"):
        line = line.strip().lstrip("- •·")
        if line:
            changes.append(line)

    return {
        "yaml_content": new_yaml,
        "validation": validation,
        "security": security,
        "changes": changes[:10],
    }


async def review_pipeline(yaml_content: str) -> dict:
    """审查 Pipeline YAML"""
    model = get_chat_model("chat")

    user_prompt = f"""请审查以下 Pipeline YAML，给出评分（0-100）和改进建议。

```yaml
{yaml_content}
```

请以 JSON 格式输出:
{{
  "score": 85,
  "issues": [
    {{"severity": "error|warning|info", "step_id": "xxx", "message": "问题描述", "suggestion": "修复建议"}}
  ],
  "best_practices": ["✅ 好的做法", "⚠️ 改进建议"]
}}"""

    response = await model.ainvoke(
        [
            {"role": "system", "content": _build_system_prompt()},
            {"role": "user", "content": user_prompt},
        ]
    )
    content = response.content if isinstance(response.content, str) else str(response.content)

    # 解析 JSON 响应
    try:
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            review = json.loads(match.group())
        else:
            review = {
                "score": 0,
                "issues": [{"severity": "error", "message": "AI 审查响应解析失败"}],
                "best_practices": [],
            }
    except json.JSONDecodeError:
        review = {"score": 0, "issues": [{"severity": "error", "message": "AI 审查响应解析失败"}], "best_practices": []}

    # 追加安全策略检查
    try:
        parsed = yaml.safe_load(yaml_content)
        if isinstance(parsed, dict):
            security = _validate_security(parsed)
            review["security"] = security
    except yaml.YAMLError:
        pass

    return review

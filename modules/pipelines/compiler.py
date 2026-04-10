"""Pipeline 编排引擎 — YAML 编译器 + LangGraph 构建 + Mermaid 生成

编译流程:
  YAML 文本
    → parse_pipeline_yaml()  — 语法解析 + Pydantic 校验
  PipelineDefinition
    → validate_pipeline()    — 循环检测 + step 引用检查 + 参数完整性
    → compile_to_langgraph() — 动态构建 StateGraph
  CompiledGraph
    → 运行时 checkpoint 断点恢复
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import yaml
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from modules.pipelines.models import (
    PipelineDefinition,
    PipelineState,
    StepDefinition,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 模板变量解析
# ---------------------------------------------------------------------------

_TEMPLATE_RE = re.compile(r"\{\{(.+?)\}\}")


def resolve_template(template_str: str, state: PipelineState) -> str:
    """解析模板变量，支持 {{params.x}}, {{steps.x.output}}, {{run.id}} 等

    Args:
        template_str: 含模板占位符的字符串
        state: 当前 Pipeline 运行时状态

    Returns:
        替换后的字符串; 无法解析的占位符保留原样
    """

    def _resolve_match(match: re.Match) -> str:
        path = match.group(1).strip()
        parts = path.split(".")
        if not parts:
            return match.group(0)

        root = parts[0]
        rest = parts[1:]

        # {{params.xxx}}
        if root == "params":
            value = state.get("params", {})
            for key in rest:
                if isinstance(value, dict):
                    value = value.get(key, match.group(0))
                else:
                    return match.group(0)
            return str(value) if not isinstance(value, str) else value

        # {{steps.xxx.output}} / {{steps.xxx.output.field}} / {{steps.xxx.exit_code}}
        if root == "steps" and len(rest) >= 1:
            step_id = rest[0]
            step_data = state.get("step_outputs", {}).get(step_id)
            if step_data is None:
                return match.group(0)
            # rest[1:] 是 step_data 之后的路径
            # 约定: "output" 是 step_data 自身的别名（step 执行结果）
            remaining = list(rest[1:])
            value = step_data
            if remaining and remaining[0] == "output":
                # "output" 指向 step_data 本身，跳过这一层
                remaining = remaining[1:]
            # 深度取值
            for key in remaining:
                if isinstance(value, dict):
                    value = value.get(key, match.group(0))
                elif isinstance(value, str):
                    # 尝试 JSON 解析
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, dict):
                            value = parsed.get(key, match.group(0))
                        else:
                            return match.group(0)
                    except (json.JSONDecodeError, TypeError):
                        return match.group(0)
                else:
                    return match.group(0)
            return str(value) if not isinstance(value, str) else value

        # {{run.id}} / {{run.started_at}}
        if root == "run":
            if rest and rest[0] == "id":
                return state.get("run_id", match.group(0))
            return match.group(0)

        return match.group(0)

    return _TEMPLATE_RE.sub(_resolve_match, template_str)


# ---------------------------------------------------------------------------
# YAML 解析
# ---------------------------------------------------------------------------


def parse_pipeline_yaml(yaml_str: str) -> PipelineDefinition:
    """将 YAML 文本解析为 PipelineDefinition

    Raises:
        ValueError: YAML 语法错误或 Pydantic 校验失败
    """
    try:
        data = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 语法错误: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("YAML 顶层必须是字典")

    try:
        return PipelineDefinition(**data)
    except ValidationError as e:
        raise ValueError(f"Pipeline 定义校验失败: {e}") from e


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


def _collect_all_step_ids(steps: list[StepDefinition]) -> list[str]:
    """递归收集所有 step id（含 parallel branches 内部的）"""
    ids: list[str] = []
    for step in steps:
        ids.append(step.id)
        if step.branches:
            ids.extend(_collect_all_step_ids(step.branches))
    return ids


def validate_pipeline(definition: PipelineDefinition) -> list[str]:
    """校验 Pipeline 定义，返回错误列表（空列表表示通过）

    检查项:
    - step id 唯一性
    - condition 的 on_true/on_false 引用有效 step
    - on_failure goto 引用有效 step
    - 参数完整性（required 参数有 name 和 type）
    - 至少有一个 step
    """
    errors: list[str] = []

    if not definition.steps:
        errors.append("Pipeline 必须至少包含一个 step")
        return errors

    all_ids = _collect_all_step_ids(definition.steps)

    # step id 唯一性
    seen: set[str] = set()
    for sid in all_ids:
        if sid in seen:
            errors.append(f"重复的 step id: '{sid}'")
        seen.add(sid)

    id_set = set(all_ids)

    # 校验 step 引用
    for step in definition.steps:
        # condition 引用检查
        if step.type == "condition":
            if step.on_true and step.on_true not in id_set:
                errors.append(f"Step '{step.id}' 的 on_true 引用了不存在的 step: '{step.on_true}'")
            if step.on_false and step.on_false not in id_set:
                errors.append(f"Step '{step.id}' 的 on_false 引用了不存在的 step: '{step.on_false}'")

        # on_failure goto 引用检查
        if step.on_failure and step.on_failure.startswith("goto:"):
            target = step.on_failure[5:]
            if target not in id_set:
                errors.append(f"Step '{step.id}' 的 on_failure 引用了不存在的 step: '{target}'")

        # parallel 分支校验
        if step.type == "parallel" and not step.branches:
            errors.append(f"Step '{step.id}' 类型为 parallel 但未定义 branches")

    # 参数完整性
    for param in definition.params:
        if not param.name:
            errors.append("参数定义缺少 name 字段")
        if not param.type:
            errors.append(f"参数 '{param.name}' 缺少 type 字段")

    return errors


# ---------------------------------------------------------------------------
# LangGraph 构建
# ---------------------------------------------------------------------------


def _build_step_node(step: StepDefinition):
    """构建 step 节点函数 — 实际执行器在 steps/ 模块中

    每个节点函数:
    1. 解析模板变量
    2. 调用对应类型的 executor
    3. 将输出写入 state.step_outputs
    4. 更新 current_step
    """
    from modules.pipelines.steps import get_step_executor

    executor = get_step_executor(step.type)

    async def node(state: PipelineState) -> dict:
        # 解析 step 中的模板变量
        step_input: dict[str, Any] = {}
        for field_name in ("command", "host", "prompt", "message", "url", "body", "expression"):
            value = getattr(step, field_name, None)
            if isinstance(value, str):
                step_input[field_name] = resolve_template(value, state)

        # 传递额外参数
        if step.params:
            resolved_params = {}
            for k, v in step.params.items():
                resolved_params[k] = resolve_template(str(v), state) if isinstance(v, str) else v
            step_input["params"] = resolved_params

        step_input["step_id"] = step.id
        step_input["step_type"] = step.type
        step_input["timeout"] = step.timeout

        try:
            result = await executor(**step_input)
        except Exception as exc:
            logger.exception("Step '%s' (%s) 执行异常", step.id, step.type)
            result = {"status": "failed", "error": str(exc)}

        # 更新 state
        step_outputs = dict(state.get("step_outputs", {}))
        step_outputs[step.id] = result

        return {
            "step_outputs": step_outputs,
            "current_step": step.id,
        }

    # 便于调试
    node.__name__ = f"step_{step.id}"
    node.__qualname__ = f"step_{step.id}"
    return node


def _build_parallel_join_node(step: StepDefinition):
    """构建 parallel join 节点 — 合并各分支输出"""

    async def join_node(state: PipelineState) -> dict:
        # Send() 的各分支结果已经由 LangGraph 合并到 state 中
        # join 只需标记 parallel step 完成
        step_outputs = dict(state.get("step_outputs", {}))
        branch_results = {}
        if step.branches:
            for branch in step.branches:
                branch_results[branch.id] = step_outputs.get(branch.id, {})
        step_outputs[step.id] = {"branches": branch_results, "status": "completed"}
        return {
            "step_outputs": step_outputs,
            "current_step": step.id,
        }

    join_node.__name__ = f"join_{step.id}"
    join_node.__qualname__ = f"join_{step.id}"
    return join_node


def compile_to_langgraph(
    definition: PipelineDefinition,
    checkpointer: Any = None,
) -> Any:
    """将 PipelineDefinition 编译为 LangGraph CompiledGraph

    映射规则:
    - 线性 step → add_edge
    - condition  → conditional_edges
    - parallel   → Send() + join 节点
    - approval   → interrupt_before
    - 其他       → 普通节点

    Args:
        definition: 经过校验的 Pipeline 定义
        checkpointer: LangGraph AsyncSqliteSaver 或 None

    Returns:
        CompiledGraph 实例
    """
    from langgraph.types import Send

    graph = StateGraph(PipelineState)
    steps = definition.steps
    interrupt_nodes: list[str] = []

    # 第一遍: 注册所有节点
    for step in steps:
        node_name = step.id

        if step.type == "parallel":
            # parallel: 为每个分支创建节点 + join 节点
            if step.branches:
                for branch in step.branches:
                    graph.add_node(branch.id, _build_step_node(branch))
            join_name = f"{step.id}_join"
            graph.add_node(join_name, _build_parallel_join_node(step))

        elif step.type == "condition":
            # condition 不需要独立节点，通过 conditional_edges 实现
            pass

        else:
            graph.add_node(node_name, _build_step_node(step))

            if step.type == "approval":
                interrupt_nodes.append(node_name)

    # 第二遍: 连接边
    for i, step in enumerate(steps):
        prev_name = steps[i - 1].id if i > 0 else None
        next_name = steps[i + 1].id if i + 1 < len(steps) else None

        # 确定当前 step 的"出口名"（parallel 用 join 节点）
        current_exit = step.id
        if step.type == "parallel":
            current_exit = f"{step.id}_join"
        elif step.type == "condition":
            current_exit = None  # condition 通过 conditional_edges 处理

        # START → 第一个 step
        if i == 0:
            if step.type == "parallel" and step.branches:
                # START → Send() 到各分支
                branch_ids = [b.id for b in step.branches]

                def _fan_out_start(state: PipelineState, _ids=branch_ids) -> list:
                    return [Send(bid, state) for bid in _ids]

                graph.add_conditional_edges(START, _fan_out_start)
            elif step.type == "condition":
                _add_condition_edges(graph, step, START, next_name)
            else:
                graph.add_edge(START, step.id)

        # 从上一个 step 连到当前 step
        elif prev_name is not None:
            prev_step = steps[i - 1]
            prev_exit = prev_step.id
            if prev_step.type == "parallel":
                prev_exit = f"{prev_step.id}_join"
            elif prev_step.type == "condition":
                prev_exit = None  # 已经在 condition 处理中添加了边

            if prev_exit is not None:
                if step.type == "parallel" and step.branches:
                    branch_ids = [b.id for b in step.branches]

                    def _fan_out(state: PipelineState, _ids=branch_ids) -> list:
                        return [Send(bid, state) for bid in _ids]

                    graph.add_conditional_edges(prev_exit, _fan_out)
                elif step.type == "condition":
                    _add_condition_edges(graph, step, prev_exit, next_name)
                else:
                    graph.add_edge(prev_exit, step.id)

        # parallel 内部: 各分支 → join
        if step.type == "parallel" and step.branches:
            join_name = f"{step.id}_join"
            for branch in step.branches:
                graph.add_edge(branch.id, join_name)

        # 最后一个 step → END
        if i == len(steps) - 1 and current_exit is not None:
            graph.add_edge(current_exit, END)

    # 编译
    compile_kwargs: dict[str, Any] = {}
    if checkpointer is not None:
        compile_kwargs["checkpointer"] = checkpointer
    if interrupt_nodes:
        compile_kwargs["interrupt_before"] = interrupt_nodes

    return graph.compile(**compile_kwargs)


def _add_condition_edges(
    graph: StateGraph,
    step: StepDefinition,
    source: str,
    fallback_next: str | None,
) -> None:
    """为 condition step 添加条件边"""
    on_true_target = step.on_true or fallback_next or END
    on_false_target = step.on_false or fallback_next or END

    def _route(state: PipelineState, _step=step, _true=on_true_target, _false=on_false_target) -> str:
        expr = _step.expression or ""
        resolved = resolve_template(expr, state)
        try:
            # 安全评估简单表达式
            result = _safe_eval_condition(resolved)
        except Exception:
            logger.warning("条件表达式 '%s' 评估失败，走 on_false 分支", resolved)
            result = False
        return _true if result else _false

    # 收集所有可能的目标节点
    targets: set[str] = set()
    if on_true_target != END:
        targets.add(on_true_target)
    if on_false_target != END:
        targets.add(on_false_target)
    if on_true_target == END or on_false_target == END:
        targets.add(END)

    # 不使用 path_map; 直接注册 conditional_edges
    graph.add_conditional_edges(source, _route, {t: t for t in targets})


def _safe_eval_condition(expr: str) -> bool:
    """安全评估简单条件表达式

    仅支持: 数值比较 (>=, <=, >, <, ==, !=)、字符串比较、bool 字面量
    """
    expr = expr.strip()

    # 布尔字面量
    if expr.lower() in ("true", "1", "yes"):
        return True
    if expr.lower() in ("false", "0", "no", ""):
        return False

    # 简单比较: "value op threshold"
    comparison_re = re.compile(r"^(.+?)\s*(>=|<=|!=|==|>|<)\s*(.+)$")
    m = comparison_re.match(expr)
    if m:
        left_str, op, right_str = m.group(1).strip(), m.group(2), m.group(3).strip()
        left = _try_parse_number(left_str)
        right = _try_parse_number(right_str)
        ops = {
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        return ops[op](left, right)

    # 无法解析 — 非空字符串视为 True
    return bool(expr)


def _try_parse_number(s: str) -> float | str:
    """尝试将字符串解析为数值，失败则返回原字符串"""
    # 去掉引号
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    try:
        return float(s)
    except ValueError:
        return s


# ---------------------------------------------------------------------------
# Mermaid 流程图生成
# ---------------------------------------------------------------------------


def generate_mermaid(definition: PipelineDefinition) -> str:
    """根据 PipelineDefinition 生成 Mermaid 流程图代码"""
    lines: list[str] = ["graph TD"]
    steps = definition.steps

    if not steps:
        return "graph TD\n    START --> END"

    def _node_label(step: StepDefinition) -> str:
        label = step.name or step.id
        return f'{step.id}["{label}"]'

    def _node_shape(step: StepDefinition) -> str:
        """根据 step 类型选择 Mermaid 节点形状"""
        label = step.name or step.id
        if step.type == "condition":
            return f'{step.id}{{"{label}"}}'
        if step.type == "decision":
            return f'{step.id}{{"{label}"}}'
        if step.type == "approval":
            return f'{step.id}(["{label}"])'
        if step.type == "parallel":
            return f'{step.id}[["{label}"]]'
        return f'{step.id}["{label}"]'

    # 注册节点
    for step in steps:
        lines.append(f"    {_node_shape(step)}")
        if step.type == "parallel" and step.branches:
            for branch in step.branches:
                lines.append(f"    {_node_label(branch)}")

    # 连接边
    for i, step in enumerate(steps):
        # 前一个节点
        if i == 0:
            prev = "START((Start))"
            lines.insert(1, f"    {prev}")
            prev_id = "START"
        else:
            prev_step = steps[i - 1]
            prev_id = prev_step.id
            if prev_step.type == "parallel":
                # parallel 的各分支指向当前 step
                if prev_step.branches:
                    for branch in prev_step.branches:
                        lines.append(f"    {branch.id} --> {step.id}")
                continue
            if prev_step.type == "condition":
                # condition 已在下面处理，跳过
                continue
            if prev_step.type == "decision":
                # decision 的各选项边已在下面处理，跳过
                continue

        if step.type == "decision":
            # 菱形节点 + 每个 option 生成一条带标签的边
            lines.append(f"    {prev_id} --> {step.id}")
            for opt in step.options or []:
                target = opt.get("next_step")
                label = opt.get("label", opt.get("id", ""))
                if target:
                    lines.append(f'    {step.id} -->|"{label}"| {target}')
        elif step.type == "condition":
            # 菱形节点 + 两条分支
            lines.append(f"    {prev_id} --> {step.id}")
            if step.on_true:
                lines.append(f'    {step.id} -->|"True"| {step.on_true}')
            if step.on_false:
                lines.append(f'    {step.id} -->|"False"| {step.on_false}')
        elif step.type == "parallel" and step.branches:
            lines.append(f"    {prev_id} --> {step.id}")
            for branch in step.branches:
                lines.append(f"    {step.id} --> {branch.id}")
        else:
            lines.append(f"    {prev_id} --> {step.id}")

    # 最后一个 step → END
    last = steps[-1]
    last_id = last.id
    if last.type in ("condition", "decision"):
        # condition/decision 的终点由分支边决定，不额外连 END
        pass
    elif last.type == "parallel" and last.branches:
        lines.append("    END_NODE((End))")
        for branch in last.branches:
            lines.append(f"    {branch.id} --> END_NODE")
    else:
        lines.append("    END_NODE((End))")
        lines.append(f"    {last_id} --> END_NODE")

    return "\n".join(lines)

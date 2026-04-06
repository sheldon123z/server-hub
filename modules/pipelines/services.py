"""Pipeline 业务逻辑层 — CRUD + 统计 + YAML 验证"""

import json
import logging
import uuid
from datetime import datetime, timedelta

from database import get_db

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------

_PIPELINE_FIELDS = (
    "id, name, display_name, description, yaml_content, steps_json, "
    "params_json, trigger_json, version, max_concurrent_runs, timeout, "
    "enabled, created_by, created_at, updated_at"
)

_RUN_FIELDS = (
    "id, pipeline_id, pipeline_version, status, params_json, "
    "current_step_id, steps_state_json, trigger_type, started_at, "
    "completed_at, started_by, error, langgraph_thread_id, summary"
)

_STEP_LOG_FIELDS = (
    "id, run_id, step_id, step_type, status, started_at, completed_at, input_json, output_json, error, duration_ms"
)


def _row_to_pipeline(row) -> dict:
    return {
        "id": row[0],
        "name": row[1],
        "display_name": row[2],
        "description": row[3],
        "yaml_content": row[4],
        "steps_json": row[5],
        "params_json": row[6],
        "trigger_json": row[7],
        "version": row[8],
        "max_concurrent_runs": row[9],
        "timeout": row[10],
        "enabled": bool(row[11]),
        "created_by": row[12],
        "created_at": row[13],
        "updated_at": row[14],
    }


def _row_to_run(row) -> dict:
    return {
        "id": row[0],
        "pipeline_id": row[1],
        "pipeline_version": row[2],
        "status": row[3],
        "params_json": row[4],
        "current_step_id": row[5],
        "steps_state_json": row[6],
        "trigger_type": row[7],
        "started_at": row[8],
        "completed_at": row[9],
        "started_by": row[10],
        "error": row[11],
        "langgraph_thread_id": row[12],
        "summary": row[13],
    }


def _row_to_step_log(row) -> dict:
    return {
        "id": row[0],
        "run_id": row[1],
        "step_id": row[2],
        "step_type": row[3],
        "status": row[4],
        "started_at": row[5],
        "completed_at": row[6],
        "input_json": row[7],
        "output_json": row[8],
        "error": row[9],
        "duration_ms": row[10],
    }


def _parse_yaml(yaml_content: str) -> dict:
    """解析 YAML 文本，延迟导入 yaml 库。"""
    import yaml

    return yaml.safe_load(yaml_content)


def _compile_steps(parsed: dict) -> str:
    """从解析后的 pipeline 定义编译 steps_json。

    尝试调用 compiler 模块；若尚未实现则回退为直接序列化 steps 列表。
    """
    try:
        from modules.pipelines.compiler import compile_steps_json

        return compile_steps_json(parsed)
    except (ImportError, AttributeError):
        # compiler 模块在另一个 PR 中实现，回退为原始 steps
        return json.dumps(parsed.get("steps", []), ensure_ascii=False)


def _validate_parsed(parsed: dict) -> list[str]:
    """校验已解析的 pipeline 定义，返回错误列表。"""
    errors: list[str] = []
    if not parsed:
        errors.append("YAML 内容为空")
        return errors

    if not parsed.get("name"):
        errors.append("缺少必填字段: name")
    if not parsed.get("steps"):
        errors.append("缺少必填字段: steps (至少需要一个步骤)")

    steps = parsed.get("steps", [])
    step_ids: set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"步骤 #{i + 1} 格式错误: 必须是字典")
            continue
        sid = step.get("id")
        if not sid:
            errors.append(f"步骤 #{i + 1} 缺少 id")
        elif sid in step_ids:
            errors.append(f"步骤 id 重复: {sid}")
        else:
            step_ids.add(sid)
        if not step.get("type"):
            errors.append(f"步骤 '{sid or i + 1}' 缺少 type")

    # 尝试调用 compiler 的高级校验（循环检测等）
    try:
        from modules.pipelines.compiler import validate_pipeline

        advanced_errors = validate_pipeline(parsed)
        if advanced_errors:
            errors.extend(advanced_errors)
    except (ImportError, AttributeError):
        pass

    return errors


# ---------------------------------------------------------------------------
# Pipeline 定义 CRUD
# ---------------------------------------------------------------------------


async def create_pipeline(yaml_content: str, created_by: str) -> dict:
    """解析 YAML -> 验证 -> 编译 steps_json -> 存入 pipelines 表。"""
    parsed = _parse_yaml(yaml_content)
    errors = _validate_parsed(parsed)
    if errors:
        raise ValueError(f"Pipeline 验证失败: {'; '.join(errors)}")

    pipeline_id = uuid.uuid4().hex[:16]
    now = datetime.now().isoformat()
    steps_json = _compile_steps(parsed)
    params_json = json.dumps(parsed.get("params", []), ensure_ascii=False)
    trigger_json = json.dumps(parsed.get("trigger", {"type": "manual"}), ensure_ascii=False)

    db = await get_db()
    await db.execute(
        f"INSERT INTO pipelines ({_PIPELINE_FIELDS}) "  # noqa: S608
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            pipeline_id,
            parsed["name"],
            parsed.get("display_name", parsed["name"]),
            parsed.get("description", ""),
            yaml_content,
            steps_json,
            params_json,
            trigger_json,
            1,  # version
            parsed.get("max_concurrent_runs", 1),
            parsed.get("timeout", 3600),
            1 if parsed.get("enabled", True) else 0,
            created_by,
            now,
            now,
        ),
    )
    await db.commit()
    logger.info("创建 Pipeline: %s (%s)", pipeline_id, parsed["name"])
    return await get_pipeline(pipeline_id)


async def update_pipeline(pipeline_id: str, yaml_content: str) -> dict:
    """更新 YAML + 自增 version。"""
    db = await get_db()
    row = await (
        await db.execute(
            f"SELECT {_PIPELINE_FIELDS} FROM pipelines WHERE id=?",  # noqa: S608
            (pipeline_id,),
        )
    ).fetchone()
    if not row:
        raise ValueError("Pipeline 不存在")

    existing = _row_to_pipeline(row)
    parsed = _parse_yaml(yaml_content)
    errors = _validate_parsed(parsed)
    if errors:
        raise ValueError(f"Pipeline 验证失败: {'; '.join(errors)}")

    new_version = existing["version"] + 1
    now = datetime.now().isoformat()
    steps_json = _compile_steps(parsed)
    params_json = json.dumps(parsed.get("params", []), ensure_ascii=False)
    trigger_json = json.dumps(parsed.get("trigger", {"type": "manual"}), ensure_ascii=False)

    await db.execute(
        "UPDATE pipelines SET name=?, display_name=?, description=?, yaml_content=?, "
        "steps_json=?, params_json=?, trigger_json=?, version=?, "
        "max_concurrent_runs=?, timeout=?, updated_at=? WHERE id=?",
        (
            parsed["name"],
            parsed.get("display_name", parsed["name"]),
            parsed.get("description", ""),
            yaml_content,
            steps_json,
            params_json,
            trigger_json,
            new_version,
            parsed.get("max_concurrent_runs", 1),
            parsed.get("timeout", 3600),
            now,
            pipeline_id,
        ),
    )
    await db.commit()
    logger.info("更新 Pipeline: %s → v%d", pipeline_id, new_version)
    return await get_pipeline(pipeline_id)


async def get_pipeline(pipeline_id: str) -> dict | None:
    db = await get_db()
    row = await (
        await db.execute(
            f"SELECT {_PIPELINE_FIELDS} FROM pipelines WHERE id=?",  # noqa: S608
            (pipeline_id,),
        )
    ).fetchone()
    return _row_to_pipeline(row) if row else None


async def list_pipelines(enabled: bool | None = None) -> list[dict]:
    db = await get_db()
    if enabled is not None:
        rows = await (
            await db.execute(
                f"SELECT {_PIPELINE_FIELDS} FROM pipelines WHERE enabled=? ORDER BY updated_at DESC",  # noqa: S608
                (1 if enabled else 0,),
            )
        ).fetchall()
    else:
        rows = await (
            await db.execute(
                f"SELECT {_PIPELINE_FIELDS} FROM pipelines ORDER BY updated_at DESC",  # noqa: S608
            )
        ).fetchall()
    return [_row_to_pipeline(r) for r in rows]


async def delete_pipeline(pipeline_id: str) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM pipelines WHERE id=?", (pipeline_id,))
    await db.commit()
    deleted = cursor.rowcount > 0
    if deleted:
        logger.info("删除 Pipeline: %s", pipeline_id)
    return deleted


# ---------------------------------------------------------------------------
# Pipeline Run 查询
# ---------------------------------------------------------------------------


async def get_pipeline_run(run_id: str) -> dict | None:
    db = await get_db()
    row = await (
        await db.execute(
            f"SELECT {_RUN_FIELDS} FROM pipeline_runs WHERE id=?",  # noqa: S608
            (run_id,),
        )
    ).fetchone()
    return _row_to_run(row) if row else None


async def list_pipeline_runs(
    pipeline_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    db = await get_db()
    conditions: list[str] = []
    params: list = []

    if pipeline_id:
        conditions.append("pipeline_id=?")
        params.append(pipeline_id)
    if status:
        conditions.append("status=?")
        params.append(status)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)

    rows = await (
        await db.execute(
            f"SELECT {_RUN_FIELDS} FROM pipeline_runs {where} ORDER BY started_at DESC LIMIT ?",  # noqa: S608
            params,
        )
    ).fetchall()
    return [_row_to_run(r) for r in rows]


async def get_run_step_logs(run_id: str) -> list[dict]:
    db = await get_db()
    rows = await (
        await db.execute(
            f"SELECT {_STEP_LOG_FIELDS} FROM pipeline_step_logs WHERE run_id=? ORDER BY started_at",  # noqa: S608
            (run_id,),
        )
    ).fetchall()
    return [_row_to_step_log(r) for r in rows]


# ---------------------------------------------------------------------------
# 统计
# ---------------------------------------------------------------------------


async def get_pipeline_stats(pipeline_id: str | None = None, days: int = 30) -> dict:
    """成功率、平均耗时、按天聚合。"""
    db = await get_db()
    since = (datetime.now() - timedelta(days=days)).isoformat()

    conditions = ["started_at >= ?"]
    params: list = [since]
    if pipeline_id:
        conditions.append("pipeline_id=?")
        params.append(pipeline_id)

    where = "WHERE " + " AND ".join(conditions)

    # 总数 / 成功数 / 失败数
    summary_row = await (
        await db.execute(
            f"""SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
                FROM pipeline_runs {where}""",  # noqa: S608
            params,
        )
    ).fetchone()

    total = summary_row[0] or 0
    success = summary_row[1] or 0
    failed = summary_row[2] or 0
    success_rate = round(success / total * 100, 1) if total > 0 else 0

    # 平均耗时（仅统计已完成的）
    duration_row = await (
        await db.execute(
            f"""SELECT AVG(
                    CAST((julianday(completed_at) - julianday(started_at)) * 86400 AS INTEGER)
                ) FROM pipeline_runs
                {where} AND status IN ('completed', 'failed') AND completed_at IS NOT NULL""",  # noqa: S608
            params,
        )
    ).fetchone()
    avg_duration_seconds = round(duration_row[0] or 0)

    # 按天聚合
    daily_rows = await (
        await db.execute(
            f"""SELECT DATE(started_at) as day,
                       COUNT(*) as total,
                       SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as success,
                       SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as failed
                FROM pipeline_runs {where}
                GROUP BY DATE(started_at)
                ORDER BY day""",  # noqa: S608
            params,
        )
    ).fetchall()

    daily = [{"date": r[0], "total": r[1], "success": r[2] or 0, "failed": r[3] or 0} for r in daily_rows]

    return {
        "total": total,
        "success": success,
        "failed": failed,
        "success_rate": success_rate,
        "avg_duration_seconds": avg_duration_seconds,
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# YAML 验证（不保存）
# ---------------------------------------------------------------------------


async def validate_pipeline_yaml(yaml_content: str) -> dict:
    """仅验证 YAML，返回 {valid: bool, errors: [], parsed: {...}}。"""
    try:
        parsed = _parse_yaml(yaml_content)
    except Exception as e:
        return {"valid": False, "errors": [f"YAML 语法错误: {e}"], "parsed": None}

    errors = _validate_parsed(parsed)
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "parsed": {
            "name": parsed.get("name"),
            "display_name": parsed.get("display_name"),
            "steps_count": len(parsed.get("steps", [])),
            "params_count": len(parsed.get("params", [])),
            "trigger": parsed.get("trigger", {}).get("type", "manual"),
        }
        if parsed
        else None,
    }


# ---------------------------------------------------------------------------
# Mermaid 流程图生成
# ---------------------------------------------------------------------------


def generate_mermaid(pipeline: dict) -> str:
    """从 pipeline 的 steps_json 或 yaml_content 生成 Mermaid 流程图代码。"""
    try:
        steps = json.loads(pipeline.get("steps_json") or "[]")
    except (json.JSONDecodeError, TypeError):
        try:
            parsed = _parse_yaml(pipeline["yaml_content"])
            steps = parsed.get("steps", [])
        except Exception:
            return "graph TD\n  A[无法解析步骤]"

    if not steps:
        return "graph TD\n  A[空流水线]"

    lines = ["graph TD"]
    for i, step in enumerate(steps):
        sid = step.get("id", f"step{i}")
        name = step.get("name", sid)
        stype = step.get("type", "unknown")

        # 节点形状根据类型
        if stype == "approval":
            lines.append(f"  {sid}{{{{{name}}}}}")
        elif stype == "condition":
            lines.append(f"  {sid}{{{name}}}")
        elif stype == "parallel":
            lines.append(f"  {sid}[/{name}/]")
        else:
            lines.append(f"  {sid}[{name}]")

        # 连接到下一步
        if i < len(steps) - 1:
            next_sid = steps[i + 1].get("id", f"step{i + 1}")
            lines.append(f"  {sid} --> {next_sid}")

        # parallel 类型展开 branches
        if stype == "parallel":
            for branch in step.get("branches", []):
                bid = branch.get("id", "branch")
                bname = branch.get("name", bid)
                lines.append(f"  {bid}[{bname}]")
                lines.append(f"  {sid} --> {bid}")

        # condition 类型的分支
        if stype == "condition":
            on_true = step.get("on_true")
            on_false = step.get("on_false")
            if on_true:
                lines.append(f'  {sid} -->|"true"| {on_true}')
            if on_false:
                lines.append(f'  {sid} -->|"false"| {on_false}')

    return "\n".join(lines)

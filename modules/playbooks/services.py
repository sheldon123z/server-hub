"""剧本核心业务逻辑 — 参数验证, prompt 渲染, 执行编排"""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime

from database import get_db

logger = logging.getLogger(__name__)

PLAYBOOK_COLUMNS = [
    "id", "name", "description", "category", "system_prompt", "parameters",
    "tools_required", "validation_rules", "trigger_config", "safety_mode",
    "steps_visual", "is_builtin", "tags", "created_by", "created_at", "updated_at",
]


def _row_to_dict(row) -> dict | None:
    """将数据库行转换为字典"""
    if row is None:
        return None
    return dict(zip(PLAYBOOK_COLUMNS, row))


async def get_playbook(playbook_id: str) -> dict | None:
    """获取单个剧本"""
    db = await get_db()
    row = await (
        await db.execute("SELECT * FROM playbooks WHERE id = ?", (playbook_id,))
    ).fetchone()
    return _row_to_dict(row)


async def list_playbooks(category: str | None = None) -> list[dict]:
    """列出剧本，可按分类过滤"""
    db = await get_db()
    if category:
        rows = await (
            await db.execute(
                "SELECT * FROM playbooks WHERE category = ? ORDER BY updated_at DESC",
                (category,),
            )
        ).fetchall()
    else:
        rows = await (
            await db.execute("SELECT * FROM playbooks ORDER BY updated_at DESC")
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


async def create_playbook(data: dict, created_by: str) -> str:
    """创建剧本，返回 id"""
    db = await get_db()
    await db.execute(
        "INSERT INTO playbooks "
        "(id, name, description, category, system_prompt, parameters, "
        "tools_required, validation_rules, trigger_config, safety_mode, "
        "steps_visual, tags, created_by) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            data["id"], data["name"], data.get("description", ""),
            data.get("category", "general"), data["system_prompt"],
            data.get("parameters", "[]"), data.get("tools_required", ""),
            data.get("validation_rules", "{}"),
            data.get("trigger_config", '{"type":"manual"}'),
            data.get("safety_mode"), data.get("steps_visual"),
            data.get("tags", ""), created_by,
        ),
    )
    await db.commit()
    return data["id"]


async def update_playbook(playbook_id: str, updates: dict) -> None:
    """更新剧本字段"""
    db = await get_db()
    set_parts, values = [], []
    for key, val in updates.items():
        if val is not None and key in PLAYBOOK_COLUMNS:
            set_parts.append(f"{key} = ?")
            values.append(val)
    if not set_parts:
        return
    set_parts.append("updated_at = ?")
    values.append(datetime.now().isoformat())
    values.append(playbook_id)
    await db.execute(
        f"UPDATE playbooks SET {', '.join(set_parts)} WHERE id = ?", values
    )
    await db.commit()


async def delete_playbook(playbook_id: str) -> None:
    """删除剧本（内置剧本不可删除）"""
    db = await get_db()
    row = await (
        await db.execute(
            "SELECT is_builtin FROM playbooks WHERE id = ?", (playbook_id,)
        )
    ).fetchone()
    if row and row[0]:
        raise ValueError("内置剧本不可删除")
    await db.execute("DELETE FROM playbooks WHERE id = ?", (playbook_id,))
    await db.commit()


async def resolve_parameters(playbook: dict, user_params: dict) -> dict:
    """解析参数：验证必填、应用默认值、解密凭据"""
    from modules.playbooks.credentials import decrypt_credential

    param_defs = json.loads(playbook.get("parameters") or "[]")
    resolved = {}
    for pdef in param_defs:
        name = pdef["name"]
        if name in user_params:
            resolved[name] = user_params[name]
        elif pdef.get("credential_ref"):
            try:
                resolved[name] = await decrypt_credential(pdef["credential_ref"])
            except Exception:
                if pdef.get("required"):
                    raise ValueError(
                        f"凭据 '{pdef['credential_ref']}' 不存在且参数 '{name}' 必填"
                    )
        elif "default" in pdef:
            resolved[name] = pdef["default"]
        elif pdef.get("required"):
            raise ValueError(f"缺少必填参数: {name}")

        # 正则验证
        if pdef.get("validation") and resolved.get(name):
            if not re.match(pdef["validation"], str(resolved[name])):
                raise ValueError(
                    f"参数 '{name}' 格式不正确 (期望: {pdef['validation']})"
                )
    return resolved


def render_prompt(template: str, params: dict) -> str:
    """将 {param} 占位符替换为实际值"""
    result = template
    for key, val in params.items():
        placeholder = "{" + key + "}"
        if isinstance(val, list):
            val_str = ", ".join(str(v) for v in val)
        else:
            val_str = str(val)
        result = result.replace(placeholder, val_str)
    return result


def sanitize_params_for_log(params: dict, param_defs: list) -> dict:
    """将 secret 类型参数替换为 *** 用于日志记录"""
    secret_names = {p["name"] for p in param_defs if p.get("type") == "secret"}
    return {k: "***" if k in secret_names else v for k, v in params.items()}


async def execute_playbook(
    playbook_id: str,
    parameters: dict,
    triggered_by: str,
    trigger_type: str = "manual",
) -> tuple[str, str, str]:
    """执行剧本（核心引擎）

    Returns: (execution_id, status, report)
    """
    from modules.agents.deep_agent import build_agent
    from modules.agents.report_schema import determine_status_from_text

    playbook = await get_playbook(playbook_id)
    if not playbook:
        raise ValueError(f"剧本不存在: {playbook_id}")

    # 参数解析
    param_defs = json.loads(playbook.get("parameters") or "[]")
    resolved = await resolve_parameters(playbook, parameters)
    safe_params = sanitize_params_for_log(resolved, param_defs)

    # 渲染提示词
    rendered_prompt = render_prompt(playbook["system_prompt"], resolved)

    # 创建执行记录
    execution_id = uuid.uuid4().hex[:12]
    thread_id = f"playbook-{playbook_id}-{execution_id}"
    db = await get_db()
    await db.execute(
        "INSERT INTO playbook_executions "
        "(id, playbook_id, parameters_json, status, triggered_by, trigger_type, thread_id) "
        "VALUES (?,?,?,?,?,?,?)",
        (
            execution_id, playbook_id,
            json.dumps(safe_params, ensure_ascii=False),
            "running", triggered_by, trigger_type, thread_id,
        ),
    )
    await db.commit()

    # 构建 agent
    validation = json.loads(playbook.get("validation_rules") or "{}")
    safety_mode = playbook.get("safety_mode") or (
        "autonomous" if trigger_type == "schedule" else "supervised"
    )
    timeout = validation.get("timeout_seconds", 300)

    start_time = time.time()
    try:
        agent = await build_agent(safety_mode=safety_mode, purpose="patrol")
        config = {"configurable": {"thread_id": thread_id}}

        result = await asyncio.wait_for(
            agent.ainvoke(
                {"messages": [{"role": "user", "content": rendered_prompt}]},
                config=config,
            ),
            timeout=timeout,
        )

        # 提取报告
        report = ""
        for msg in reversed(result.get("messages", [])):
            if hasattr(msg, "content") and not hasattr(msg, "tool_call_id"):
                report = msg.content
                break

        duration = time.time() - start_time
        status = determine_status_from_text(report) if report else "success"

        await db.execute(
            "UPDATE playbook_executions SET status=?, report=?, completed_at=?, "
            "duration_seconds=? WHERE id=?",
            (
                status, report[:20000], datetime.now().isoformat(),
                round(duration, 1), execution_id,
            ),
        )
        await db.commit()
        return execution_id, status, report

    except asyncio.TimeoutError:
        await db.execute(
            "UPDATE playbook_executions SET status='timeout', report='执行超时', "
            "completed_at=? WHERE id=?",
            (datetime.now().isoformat(), execution_id),
        )
        await db.commit()
        return execution_id, "timeout", "执行超时"

    except Exception as e:
        await db.execute(
            "UPDATE playbook_executions SET status='error', report=?, "
            "completed_at=? WHERE id=?",
            (str(e)[:5000], datetime.now().isoformat(), execution_id),
        )
        await db.commit()
        return execution_id, "error", str(e)

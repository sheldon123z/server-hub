"""Agent 运行时服务层。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from database import get_db

logger = logging.getLogger(__name__)

_active_run_tasks: dict[str, asyncio.Task] = {}


# ---------------------------------------------------------------------------
# DbWriteBuffer — 收集 SQL 操作，单事务批量写入
# ---------------------------------------------------------------------------


class DbWriteBuffer:
    """在 SSE 流期间收集数据库写操作，通过 flush() 在单个事务中批量提交。

    用法::

        buf = DbWriteBuffer()
        buf.add("INSERT INTO t (a) VALUES (?)", ("v",))
        ...
        await buf.flush()  # 单次 commit
    """

    def __init__(self) -> None:
        self._ops: list[tuple[str, tuple[Any, ...]]] = []

    # -- 收集 ----------------------------------------------------------------

    def add(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        """将一条 SQL 写操作加入缓冲区（不立即执行）。"""
        self._ops.append((sql, params))

    @property
    def pending(self) -> int:
        return len(self._ops)

    # -- 刷写 ----------------------------------------------------------------

    async def flush(self) -> int:
        """将缓冲区中所有操作在单个事务中提交，返回执行条数。

        即使缓冲区为空也安全调用（直接返回 0）。
        """
        if not self._ops:
            return 0
        ops = self._ops
        self._ops = []
        db = await get_db()
        try:
            for sql, params in ops:
                await db.execute(sql, params)
            await db.commit()
            return len(ops)
        except Exception:
            # 回滚后重新抛出，调用方可决定是否重试
            with contextlib.suppress(Exception):
                await db.rollback()
            logger.exception("DbWriteBuffer flush 失败 (%d ops)", len(ops))
            raise

    # -- 便捷方法：与 append_run_event / record_legacy_agent_event 对应 --------

    def buffer_run_event(
        self,
        run_id: str,
        conversation_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        """缓冲一条 run_event INSERT，返回生成的 event_id。"""
        event_id = str(uuid.uuid4())
        self.add(
            "INSERT INTO agent_run_events (id, run_id, conversation_id, event_type, payload_json, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, run_id, conversation_id, event_type, json_dumps(payload), now_iso()),
        )
        return event_id

    def buffer_legacy_event(
        self,
        conversation_id: str,
        *,
        event_type: str,
        username: str,
        tool_name: str | None = None,
        tool_input: str | None = None,
        tool_output: str | None = None,
        risk_level: str | None = None,
        details: str | None = None,
    ) -> None:
        """缓冲一条 legacy agent_events INSERT。"""
        self.add(
            "INSERT INTO agent_events"
            " (conversation_id, event_type, tool_name, tool_input, tool_output, risk_level, username, details)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (conversation_id, event_type, tool_name, tool_input, tool_output, risk_level, username, details),
        )

    def buffer_run_status(
        self,
        run_id: str,
        *,
        status: str,
        error: str | None = None,
        completed: bool = False,
    ) -> None:
        """缓冲一条 run 状态更新。"""
        completed_at = now_iso() if completed else None
        self.add(
            "UPDATE agent_runs"
            " SET status = ?, error = COALESCE(?, error), updated_at = ?, completed_at = COALESCE(?, completed_at)"
            " WHERE id = ?",
            (status, error, now_iso(), completed_at, run_id),
        )

    def buffer_conversation_touch(self, conversation_id: str) -> None:
        """缓冲 conversation updated_at + message_count 更新。"""
        self.add(
            "UPDATE agent_conversations SET updated_at = ?, message_count = message_count + 1 WHERE id = ?",
            (now_iso(), conversation_id),
        )


def now_iso() -> str:
    return datetime.now().isoformat()


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


async def ensure_conversation(
    conversation_id: str,
    *,
    username: str,
    safety_mode: str,
    first_message: str,
) -> None:
    db = await get_db()
    existing = await db.execute(
        "SELECT id FROM agent_conversations WHERE id = ?",
        (conversation_id,),
    )
    if await existing.fetchone():
        return
    title = first_message[:30] + ("..." if len(first_message) > 30 else "")
    await db.execute(
        "INSERT INTO agent_conversations (id, title, username, safety_mode) VALUES (?, ?, ?, ?)",
        (conversation_id, title, username, safety_mode),
    )
    await db.commit()


async def create_run(
    *,
    conversation_id: str,
    username: str,
    safety_mode: str,
    user_message: str,
    page_context: str | None = None,
    skill_id: str | None = None,
) -> dict[str, str]:
    db = await get_db()
    run_id = str(uuid.uuid4())
    created_at = now_iso()
    await db.execute(
        """
        INSERT INTO agent_runs (
            id, conversation_id, username, status, safety_mode, page_context, skill_id,
            user_message, created_at, updated_at
        )
        VALUES (?, ?, ?, 'running', ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            conversation_id,
            username,
            safety_mode,
            page_context,
            skill_id,
            user_message,
            created_at,
            created_at,
        ),
    )
    await db.commit()
    return {"run_id": run_id, "created_at": created_at}


async def update_run_status(
    run_id: str,
    *,
    status: str,
    error: str | None = None,
    completed: bool = False,
) -> None:
    db = await get_db()
    completed_at = now_iso() if completed else None
    await db.execute(
        """
        UPDATE agent_runs
        SET status = ?, error = COALESCE(?, error), updated_at = ?, completed_at = COALESCE(?, completed_at)
        WHERE id = ?
        """,
        (status, error, now_iso(), completed_at, run_id),
    )
    await db.commit()


async def append_run_event(
    run_id: str,
    conversation_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> str:
    db = await get_db()
    event_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO agent_run_events (id, run_id, conversation_id, event_type, payload_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (event_id, run_id, conversation_id, event_type, json_dumps(payload), now_iso()),
    )
    await db.commit()
    return event_id


async def record_legacy_agent_event(
    conversation_id: str,
    *,
    event_type: str,
    username: str,
    tool_name: str | None = None,
    tool_input: str | None = None,
    tool_output: str | None = None,
    risk_level: str | None = None,
    details: str | None = None,
) -> None:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO agent_events (
            conversation_id, event_type, tool_name, tool_input, tool_output, risk_level, username, details
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (conversation_id, event_type, tool_name, tool_input, tool_output, risk_level, username, details),
    )
    await db.commit()


def register_active_run(run_id: str) -> None:
    task = asyncio.current_task()
    if task is not None:
        _active_run_tasks[run_id] = task


def unregister_active_run(run_id: str) -> None:
    _active_run_tasks.pop(run_id, None)


async def cancel_run(run_id: str, *, reason: str = "") -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT status FROM agent_runs WHERE id = ?", (run_id,))
    row = await cursor.fetchone()
    if not row:
        return False
    await db.execute(
        "UPDATE agent_runs SET status = 'cancel_requested', error = ?, updated_at = ? WHERE id = ?",
        (reason or "用户请求取消", now_iso(), run_id),
    )
    await db.commit()
    task = _active_run_tasks.get(run_id)
    if task and not task.done():
        task.cancel()
    return True


async def list_run_events(run_id: str, after: str | None = None) -> list[dict[str, Any]]:
    db = await get_db()
    params: list[Any] = [run_id]
    sql = """
        SELECT id, event_type, payload_json, created_at
        FROM agent_run_events
        WHERE run_id = ?
    """
    if after:
        sql += " AND created_at >= (SELECT created_at FROM agent_run_events WHERE id = ?)"
        params.append(after)
    sql += " ORDER BY created_at ASC"
    cursor = await db.execute(sql, tuple(params))
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "event_type": row[1],
            "payload": json.loads(row[2]),
            "created_at": row[3],
        }
        for row in rows
    ]


async def list_runs(*, username: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    db = await get_db()
    params: list[Any] = []
    sql = """
        SELECT id, conversation_id, username, status, safety_mode, page_context, skill_id,
               user_message, error, created_at, updated_at, completed_at
        FROM agent_runs
    """
    if username:
        sql += " WHERE username = ?"
        params.append(username)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    cursor = await db.execute(sql, tuple(params))
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "conversation_id": row[1],
            "username": row[2],
            "status": row[3],
            "safety_mode": row[4],
            "page_context": row[5],
            "skill_id": row[6],
            "user_message": row[7],
            "error": row[8],
            "created_at": row[9],
            "updated_at": row[10],
            "completed_at": row[11],
        }
        for row in rows
    ]


async def get_run(run_id: str) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, conversation_id, username, status, safety_mode, page_context, skill_id,
               user_message, error, created_at, updated_at, completed_at
        FROM agent_runs WHERE id = ?
        """,
        (run_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "conversation_id": row[1],
        "username": row[2],
        "status": row[3],
        "safety_mode": row[4],
        "page_context": row[5],
        "skill_id": row[6],
        "user_message": row[7],
        "error": row[8],
        "created_at": row[9],
        "updated_at": row[10],
        "completed_at": row[11],
    }


def extract_content(raw: Any) -> str:
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for block in raw:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(raw or "")


def snapshot_messages_to_history(messages: list[Any]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            history.append({"role": "user", "content": extract_content(msg.content)})
        elif isinstance(msg, AIMessage):
            content = extract_content(msg.content)
            if content:
                history.append({"role": "assistant", "content": content})
            for tc in getattr(msg, "tool_calls", []) or []:
                history.append({"role": "tool_call", "tool": tc.get("name", ""), "args": tc.get("args", {})})
        elif isinstance(msg, ToolMessage):
            history.append(
                {
                    "role": "tool_result",
                    "tool": getattr(msg, "name", ""),
                    "content": extract_content(msg.content)[:500],
                }
            )
    return history


def run_event_to_message(event_type: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    if event_type == "message.final":
        return {"role": "assistant", "content": payload.get("content", ""), "id": payload.get("id")}
    if event_type == "tool.call":
        return {"role": "tool_call", "tool": payload.get("tool", ""), "args": payload.get("input", {})}
    if event_type == "tool.result":
        return {"role": "tool_result", "tool": payload.get("tool", ""), "content": payload.get("content", "")}
    if event_type == "approval.request":
        return {
            "role": "approval",
            "approval_id": payload.get("approval_id"),
            "description": payload.get("description", "需要审批"),
            "actions": payload.get("actions", []),
        }
    if event_type == "run.error":
        return {"role": "assistant", "content": f"错误: {payload.get('error', '未知错误')}"}
    return None

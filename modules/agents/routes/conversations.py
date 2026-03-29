"""对话历史路由"""

import json

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from database import get_db
from modules.agents.run_service import run_event_to_message, snapshot_messages_to_history

router = APIRouter()


@router.get("/conversations")
async def list_conversations(user=Depends(get_current_user)):
    """每个用户只看自己的对话历史"""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT c.id, c.title, c.username, c.safety_mode, c.created_at, c.updated_at, c.message_count,
               (
                   SELECT r.status
                   FROM agent_runs r
                   WHERE r.conversation_id = c.id
                   ORDER BY r.created_at DESC
                   LIMIT 1
               )
        FROM agent_conversations c
        WHERE c.is_archived = 0 AND c.username = ?
        ORDER BY c.updated_at DESC LIMIT 50
        """,
        (user["username"],),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "title": r[1],
            "username": r[2],
            "safety_mode": r[3],
            "created_at": r[4],
            "updated_at": r[5],
            "message_count": r[6],
            "latest_run_status": r[7],
        }
        for r in rows
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user=Depends(get_current_user)):
    # 验证对话归属（所有用户只能看自己的对话）
    db = await get_db()
    cursor = await db.execute("SELECT username FROM agent_conversations WHERE id = ?", (conversation_id,))
    row = await cursor.fetchone()
    if not row or row[0] != user["username"]:
        raise HTTPException(status_code=403, detail="无权查看此对话")
    try:
        latest_run_cursor = await db.execute(
            """
            SELECT id, status, created_at, completed_at
            FROM agent_runs
            WHERE conversation_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (conversation_id,),
        )
        latest_run = await latest_run_cursor.fetchone()
        messages = []
        todos = []

        if latest_run:
            event_cursor = await db.execute(
                """
                SELECT event_type, payload_json
                FROM agent_run_events
                WHERE run_id = ?
                ORDER BY created_at ASC
                """,
                (latest_run[0],),
            )
            rows = await event_cursor.fetchall()
            for event_type, payload_json in rows:
                payload = json.loads(payload_json)
                if event_type == "todo.update":
                    todos = payload.get("todos", [])
                mapped = run_event_to_message(event_type, payload)
                if mapped:
                    messages.append(mapped)

        if not messages:
            from modules.agents.deep_agent import build_agent

            agent = await build_agent(user_role=user["role"])
            config = {"configurable": {"thread_id": conversation_id}}
            snapshot = await agent.aget_state(config)
            messages = snapshot_messages_to_history(snapshot.values.get("messages", []))
            todos = snapshot.values.get("todos", [])

        return {
            "conversation_id": conversation_id,
            "messages": messages,
            "todos": todos,
            "latest_run_summary": (
                {
                    "id": latest_run[0],
                    "status": latest_run[1],
                    "created_at": latest_run[2],
                    "completed_at": latest_run[3],
                }
                if latest_run
                else None
            ),
        }
    except Exception as e:
        return {"conversation_id": conversation_id, "messages": [], "todos": [], "error": str(e)}


@router.delete("/conversations/{conversation_id}")
async def archive_conversation(conversation_id: str, user=Depends(get_current_user)):
    db = await get_db()
    # 验证对话归属（所有用户只能删除自己的对话）
    cursor = await db.execute("SELECT username FROM agent_conversations WHERE id = ?", (conversation_id,))
    row = await cursor.fetchone()
    if not row or row[0] != user["username"]:
        raise HTTPException(status_code=403, detail="无权操作此对话")
    await db.execute("UPDATE agent_conversations SET is_archived = 1 WHERE id = ?", (conversation_id,))
    await db.commit()
    return {"ok": True}

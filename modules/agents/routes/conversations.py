"""对话历史路由"""

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

from auth.dependencies import get_current_user
from database import get_db

router = APIRouter()


@router.get("/conversations")
async def list_conversations(user=Depends(get_current_user)):
    """每个用户只看自己的对话历史"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, title, username, safety_mode, created_at, updated_at, message_count "
        "FROM agent_conversations WHERE is_archived = 0 AND username = ? ORDER BY updated_at DESC LIMIT 50",
        (user["username"],),
    )
    rows = await cursor.fetchall()
    return [
        {"id": r[0], "title": r[1], "username": r[2], "safety_mode": r[3],
         "created_at": r[4], "updated_at": r[5], "message_count": r[6]}
        for r in rows
    ]


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user=Depends(get_current_user)):
    # 验证对话归属（所有用户只能看自己的对话）
    db = await get_db()
    cursor = await db.execute(
        "SELECT username FROM agent_conversations WHERE id = ?", (conversation_id,)
    )
    row = await cursor.fetchone()
    if not row or row[0] != user["username"]:
        raise HTTPException(status_code=403, detail="无权查看此对话")
    try:
        from modules.agents.deep_agent import build_agent
        agent = await build_agent(user_role=user["role"])
        config = {"configurable": {"thread_id": conversation_id}}
        snapshot = await agent.aget_state(config)

        messages = []
        for msg in snapshot.values.get("messages", []):
            if isinstance(msg, HumanMessage):
                messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                if msg.content:
                    messages.append({"role": "assistant", "content": msg.content})
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        messages.append({"role": "tool_call", "tool": tc["name"], "args": tc["args"]})
            elif isinstance(msg, ToolMessage):
                messages.append({"role": "tool_result", "content": msg.content[:500] if msg.content else ""})

        todos = snapshot.values.get("todos", [])
        return {"conversation_id": conversation_id, "messages": messages, "todos": todos}
    except Exception as e:
        return {"conversation_id": conversation_id, "messages": [], "todos": [], "error": str(e)}


@router.delete("/conversations/{conversation_id}")
async def archive_conversation(conversation_id: str, user=Depends(get_current_user)):
    db = await get_db()
    # 验证对话归属（所有用户只能删除自己的对话）
    cursor = await db.execute(
        "SELECT username FROM agent_conversations WHERE id = ?", (conversation_id,)
    )
    row = await cursor.fetchone()
    if not row or row[0] != user["username"]:
        raise HTTPException(status_code=403, detail="无权操作此对话")
    await db.execute("UPDATE agent_conversations SET is_archived = 1 WHERE id = ?", (conversation_id,))
    await db.commit()
    return {"ok": True}

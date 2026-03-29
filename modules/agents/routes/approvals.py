"""审批路由"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import AIMessage
from langgraph.types import Command

from auth.dependencies import require_role
from database import get_db
from modules.agents.run_service import append_run_event, update_run_status
from modules.agents.schemas import ApprovalAction

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/approvals")
async def list_approvals(user=Depends(require_role("admin"))):
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, conversation_id, created_at, tool_name, tool_input, risk_level, description, status "
        "FROM agent_approvals WHERE status = 'pending' ORDER BY created_at DESC"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0],
            "conversation_id": r[1],
            "created_at": r[2],
            "tool_name": r[3],
            "tool_input": r[4],
            "risk_level": r[5],
            "description": r[6],
            "status": r[7],
        }
        for r in rows
    ]


@router.post("/approvals/{approval_id}")
async def resolve_approval(approval_id: str, body: ApprovalAction, user=Depends(require_role("admin"))):
    """批准或拒绝待审批操作"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT conversation_id, run_id, status FROM agent_approvals WHERE id = ?",
        (approval_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "审批记录不存在")
    if row[2] != "pending":
        raise HTTPException(400, "该审批已处理")

    conversation_id = row[0]
    run_id = row[1]
    await db.execute(
        "UPDATE agent_approvals SET status = ?, resolved_at = ?, resolved_by = ? WHERE id = ?",
        (body.action + "d", datetime.now().isoformat(), user["username"], approval_id),
    )
    await db.commit()

    try:
        from modules.agents.deep_agent import build_agent

        agent = await build_agent(safety_mode="supervised")
        config = {"configurable": {"thread_id": conversation_id}}
        if run_id:
            await update_run_status(run_id, status="running")

        # Deep Agents 使用 decisions 列表恢复
        decision = {"type": body.action}  # "approve" or "reject"
        result = await agent.ainvoke(
            Command(resume={"decisions": [decision]}),
            config=config,
        )

        final_content = ""
        for msg in reversed(result.get("messages", [])):
            if isinstance(msg, AIMessage) and msg.content:
                final_content = msg.content
                break

        if run_id:
            await append_run_event(
                run_id,
                conversation_id,
                "message.final",
                {
                    "run_id": run_id,
                    "conversation_id": conversation_id,
                    "content": final_content[:1000],
                    "id": f"resume-{approval_id}",
                },
            )
            await append_run_event(
                run_id,
                conversation_id,
                "run.completed",
                {"run_id": run_id, "conversation_id": conversation_id, "status": "completed"},
            )
            await update_run_status(run_id, status="completed", completed=True)

        return {"ok": True, "action": body.action + "d", "result": final_content[:1000]}
    except Exception as e:
        logger.error("Resume failed: %s", e)
        if run_id:
            await append_run_event(
                run_id,
                conversation_id,
                "run.error",
                {"run_id": run_id, "conversation_id": conversation_id, "error": str(e)},
            )
            await update_run_status(run_id, status="error", error=str(e), completed=True)
        return {"ok": False, "error": str(e)}

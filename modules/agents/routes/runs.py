"""Agent run 生命周期路由。"""

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import get_current_user
from modules.agents.run_service import (
    cancel_run,
    create_run,
    ensure_conversation,
    get_run,
    list_run_events,
    list_runs,
)
from modules.agents.schemas import ChatRequest, RunCancelRequest

router = APIRouter()


@router.get("/runs")
async def list_agent_runs(user=Depends(get_current_user)):
    username = None if user["role"] == "admin" else user["username"]
    return await list_runs(username=username)


@router.post("/runs")
async def create_agent_run(body: ChatRequest, user=Depends(get_current_user)):
    conversation_id = body.conversation_id or __import__("uuid").uuid4().hex
    safety_mode = body.safety_mode if user["role"] == "admin" else "supervised"
    await ensure_conversation(
        conversation_id,
        username=user["username"],
        safety_mode=safety_mode,
        first_message=body.message,
    )
    run = await create_run(
        conversation_id=conversation_id,
        username=user["username"],
        safety_mode=safety_mode,
        user_message=body.message,
        page_context=body.page_context,
        skill_id=body.skill_id,
    )
    return {"ok": True, "conversation_id": conversation_id, **run}


@router.get("/runs/{run_id}")
async def get_agent_run(run_id: str, user=Depends(get_current_user)):
    run = await get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="运行不存在")
    if user["role"] != "admin" and run["username"] != user["username"]:
        raise HTTPException(status_code=403, detail="无权查看此运行")
    return run


@router.get("/runs/{run_id}/events")
async def get_agent_run_events(run_id: str, after: str | None = None, user=Depends(get_current_user)):
    run = await get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="运行不存在")
    if user["role"] != "admin" and run["username"] != user["username"]:
        raise HTTPException(status_code=403, detail="无权查看此运行")
    return {"run_id": run_id, "events": await list_run_events(run_id, after=after)}


@router.post("/runs/{run_id}/cancel")
async def cancel_agent_run(run_id: str, body: RunCancelRequest, user=Depends(get_current_user)):
    run = await get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="运行不存在")
    if user["role"] != "admin" and run["username"] != user["username"]:
        raise HTTPException(status_code=403, detail="无权取消此运行")
    ok = await cancel_run(run_id, reason=body.reason)
    if not ok:
        raise HTTPException(status_code=400, detail="运行无法取消")
    return {"ok": True, "run_id": run_id}

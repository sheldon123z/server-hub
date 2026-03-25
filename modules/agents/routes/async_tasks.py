"""后台异步任务路由"""

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import require_role
from database import get_db

router = APIRouter()


@router.get("/async-tasks")
async def list_async_tasks(user=Depends(require_role("admin"))):
    """列出所有后台异步任务"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, task_type, instruction, status, created_at, completed_at "
        "FROM async_agent_tasks ORDER BY created_at DESC LIMIT 50"
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": r[0], "task_type": r[1], "instruction": (r[2] or "")[:200],
            "status": r[3], "created_at": r[4], "completed_at": r[5],
        }
        for r in rows
    ]


@router.get("/async-tasks/{task_id}")
async def get_async_task(task_id: str, user=Depends(require_role("admin"))):
    """查看后台任务详情"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, task_type, instruction, status, result, created_at, completed_at "
        "FROM async_agent_tasks WHERE id = ?",
        (task_id,),
    )
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {
        "id": row[0], "task_type": row[1], "instruction": row[2],
        "status": row[3], "result": row[4],
        "created_at": row[5], "completed_at": row[6],
    }


@router.delete("/async-tasks/{task_id}")
async def cancel_async_task_api(task_id: str, user=Depends(require_role("admin"))):
    """取消后台任务"""
    from modules.agents.async_tasks import cancel_task
    result = await cancel_task(task_id)
    return {"ok": True, "message": result}

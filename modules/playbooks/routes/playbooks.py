"""剧本 CRUD 路由"""

from fastapi import APIRouter, Depends, HTTPException

from auth.dependencies import require_role
from modules.playbooks import services
from modules.playbooks.schemas import PlaybookCreateRequest, PlaybookUpdateRequest

playbooks_router = APIRouter()


@playbooks_router.get("/")
@playbooks_router.get("")
async def list_playbooks(category: str = "", user=Depends(require_role("admin"))):
    return await services.list_playbooks(category or None)


@playbooks_router.get("/{playbook_id}")
async def get_playbook(playbook_id: str, user=Depends(require_role("admin"))):
    pb = await services.get_playbook(playbook_id)
    if not pb:
        raise HTTPException(404, "剧本不存在")
    return pb


@playbooks_router.post("/")
async def create_playbook(body: PlaybookCreateRequest, user=Depends(require_role("admin"))):
    try:
        pid = await services.create_playbook(body.model_dump(), user["username"])
        return {"ok": True, "id": pid}
    except Exception as e:
        raise HTTPException(400, str(e))


@playbooks_router.put("/{playbook_id}")
async def update_playbook(playbook_id: str, body: PlaybookUpdateRequest, user=Depends(require_role("admin"))):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    await services.update_playbook(playbook_id, updates)
    return {"ok": True}


@playbooks_router.delete("/{playbook_id}")
async def delete_playbook(playbook_id: str, user=Depends(require_role("admin"))):
    try:
        await services.delete_playbook(playbook_id)
        return {"ok": True}
    except ValueError as e:
        raise HTTPException(400, str(e))

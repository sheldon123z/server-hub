"""凭据管理路由"""

from fastapi import APIRouter, Depends

from auth.dependencies import require_role
from modules.playbooks.schemas import CredentialCreateRequest
from modules.playbooks import credentials as cred_service

credentials_router = APIRouter(prefix="/credentials")


@credentials_router.get("/")
async def list_creds(user=Depends(require_role("admin"))):
    return await cred_service.list_credentials()


@credentials_router.post("/")
async def create_cred(body: CredentialCreateRequest, user=Depends(require_role("admin"))):
    cred_id = await cred_service.store_credential(
        body.name, body.value, body.description, body.credential_type, user["username"],
    )
    return {"ok": True, "id": cred_id}


@credentials_router.delete("/{name}")
async def delete_cred(name: str, user=Depends(require_role("admin"))):
    await cred_service.delete_credential(name)
    return {"ok": True}

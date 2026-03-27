from fastapi import APIRouter
from modules.playbooks.routes.playbooks import playbooks_router
from modules.playbooks.routes.executions import executions_router
from modules.playbooks.routes.credentials import credentials_router

router = APIRouter(prefix="/api/playbooks", tags=["Playbooks"])
router.include_router(playbooks_router)
router.include_router(executions_router)
router.include_router(credentials_router)

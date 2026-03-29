from fastapi import APIRouter

from modules.playbooks.routes.credentials import credentials_router
from modules.playbooks.routes.executions import executions_router
from modules.playbooks.routes.playbooks import playbooks_router

router = APIRouter(prefix="/api/playbooks", tags=["Playbooks"])
# credentials 和 executions 有固定前缀，必须在 playbooks CRUD（含 /{playbook_id}）之前注册
router.include_router(credentials_router)
router.include_router(executions_router)
router.include_router(playbooks_router)

"""智能体 API 路由 — 拆分为子模块，统一导出 router"""

from fastapi import APIRouter

from modules.agents.routes.chat import router as chat_router
from modules.agents.routes.approvals import router as approvals_router
from modules.agents.routes.conversations import router as conversations_router
from modules.agents.routes.patrols import router as patrols_router
from modules.agents.routes.alerts import router as alerts_router
from modules.agents.routes.fault import router as fault_router
from modules.agents.routes.config import router as config_router
from modules.agents.routes.async_tasks import router as async_tasks_router
from modules.agents.routes.terminal import router as terminal_router

router = APIRouter(prefix="/api/agents", tags=["AI Agent"])

router.include_router(chat_router)
router.include_router(approvals_router)
router.include_router(conversations_router)
router.include_router(patrols_router)
router.include_router(alerts_router)
router.include_router(fault_router)
router.include_router(config_router)
router.include_router(async_tasks_router)
router.include_router(terminal_router)

"""Clash 代理管理路由"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth.dependencies import require_role
from modules.proxy.services import (
    get_clash_status,
    get_proxy_groups,
    switch_proxy_node,
    switch_config,
    update_subscription,
    restart_clash,
    test_group_delays,
)

router = APIRouter(prefix="/api/proxy", tags=["代理管理"])


class SwitchNodeReq(BaseModel):
    group: str
    node: str


class SwitchConfigReq(BaseModel):
    config: str


@router.get("/status")
async def api_status(user=Depends(require_role("admin"))):
    return await get_clash_status()


@router.get("/groups")
async def api_groups(user=Depends(require_role("admin"))):
    return await get_proxy_groups()


@router.post("/switch-node")
async def api_switch_node(req: SwitchNodeReq, user=Depends(require_role("admin"))):
    ok = await switch_proxy_node(req.group, req.node)
    if ok:
        return {"ok": True, "msg": f"已切换到 {req.node}"}
    return JSONResponse({"ok": False, "msg": "切换失败"}, status_code=500)


@router.post("/switch-config")
async def api_switch_config(req: SwitchConfigReq, user=Depends(require_role("admin"))):
    result = await switch_config(req.config)
    status_code = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status_code)


@router.post("/update-subscription")
async def api_update_sub(user=Depends(require_role("admin"))):
    result = await update_subscription()
    status_code = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status_code)


@router.post("/restart")
async def api_restart(user=Depends(require_role("admin"))):
    result = await restart_clash()
    status_code = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status_code)


@router.get("/test-delays/{group}")
async def api_test_delays(group: str, user=Depends(require_role("admin"))):
    delays = await test_group_delays(group)
    return delays

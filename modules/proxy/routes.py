"""通用代理管理路由."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth.dependencies import require_role
from modules.proxy.services import (
    add_subscription_profile,
    get_clash_proxy_groups,
    get_clash_status,
    get_default_instance_id,
    get_proxy_groups,
    get_proxy_instance_status,
    list_proxy_instances,
    restart_clash,
    run_proxy_instance_action,
    switch_config,
    switch_proxy_config,
    switch_proxy_node,
    test_group_delays,
    update_subscription,
)

router = APIRouter(prefix="/api/proxy", tags=["代理管理"])


class SwitchNodeReq(BaseModel):
    group: str
    node: str


class SwitchConfigReq(BaseModel):
    config: str


class AddSubscriptionProfileReq(BaseModel):
    name: str
    url: str
    switch_after_add: bool = False


@router.get("/instances")
async def api_instances(user=Depends(require_role("admin"))):
    return await list_proxy_instances()


@router.get("/instances/{instance_id}")
async def api_instance_status(instance_id: str, user=Depends(require_role("admin"))):
    try:
        return await get_proxy_instance_status(instance_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/instances/{instance_id}/actions/{action}")
async def api_instance_action(instance_id: str, action: str, user=Depends(require_role("admin"))):
    try:
        result = await run_proxy_instance_action(instance_id, action)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if result.get("unsupported"):
        return JSONResponse(result, status_code=400)

    status_code = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status_code)


@router.post("/instances/{instance_id}/switch-config")
async def api_instance_switch_config(
    instance_id: str,
    req: SwitchConfigReq,
    user=Depends(require_role("admin")),
):
    try:
        result = await switch_proxy_config(instance_id, req.config)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    if result.get("unsupported"):
        return JSONResponse(result, status_code=400)

    status_code = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status_code)


@router.post("/instances/{instance_id}/config-profiles")
async def api_instance_add_config_profile(
    instance_id: str,
    req: AddSubscriptionProfileReq,
    user=Depends(require_role("admin")),
):
    try:
        result = await add_subscription_profile(
            instance_id,
            req.name,
            req.url,
            switch_after_add=req.switch_after_add,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    status_code = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status_code)


@router.post("/instances/{instance_id}/config-profiles/{profile_key}/update-subscription")
async def api_instance_update_profile_subscription(
    instance_id: str,
    profile_key: str,
    user=Depends(require_role("admin")),
):
    try:
        result = await update_subscription(instance_id, profile_key=profile_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if result.get("unsupported"):
        return JSONResponse(result, status_code=400)

    status_code = 200 if result.get("ok") else 500
    return JSONResponse(result, status_code=status_code)


@router.get("/instances/{instance_id}/extensions/clash/groups")
async def api_instance_clash_groups(instance_id: str, user=Depends(require_role("admin"))):
    try:
        return await get_clash_proxy_groups(instance_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/instances/{instance_id}/extensions/clash/switch-node")
async def api_instance_switch_node(
    instance_id: str,
    req: SwitchNodeReq,
    user=Depends(require_role("admin")),
):
    try:
        ok = await switch_proxy_node(instance_id, req.group, req.node)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if ok:
        return {"ok": True, "msg": f"已切换到 {req.node}"}
    return JSONResponse({"ok": False, "msg": "切换失败"}, status_code=500)


@router.get("/instances/{instance_id}/extensions/clash/test-delays/{group}")
async def api_instance_test_delays(instance_id: str, group: str, user=Depends(require_role("admin"))):
    try:
        return await test_group_delays(instance_id, group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ─── 兼容旧版 Clash 单实例 API ───


@router.get("/status")
async def api_status(user=Depends(require_role("admin"))):
    return await get_clash_status()


@router.get("/groups")
async def api_groups(user=Depends(require_role("admin"))):
    return await get_proxy_groups()


@router.post("/switch-node")
async def api_switch_node(req: SwitchNodeReq, user=Depends(require_role("admin"))):
    instance_id = get_default_instance_id()
    if not instance_id:
        raise HTTPException(status_code=404, detail="未配置默认代理实例")

    try:
        ok = await switch_proxy_node(instance_id, req.group, req.node)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if ok:
        return {"ok": True, "msg": f"已切换到 {req.node}"}
    return JSONResponse({"ok": False, "msg": "切换失败"}, status_code=500)


@router.post("/switch-config")
async def api_switch_config(req: SwitchConfigReq, user=Depends(require_role("admin"))):
    result = await switch_config(req.config)
    if result.get("unsupported"):
        return JSONResponse(result, status_code=400)
    status_code = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status_code)


@router.post("/update-subscription")
async def api_update_sub(user=Depends(require_role("admin"))):
    result = await update_subscription()
    if result.get("unsupported"):
        return JSONResponse(result, status_code=400)
    status_code = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status_code)


@router.post("/restart")
async def api_restart(user=Depends(require_role("admin"))):
    result = await restart_clash()
    status_code = 200 if result["ok"] else 500
    return JSONResponse(result, status_code=status_code)


@router.get("/test-delays/{group}")
async def api_test_delays(group: str, user=Depends(require_role("admin"))):
    instance_id = get_default_instance_id()
    if not instance_id:
        raise HTTPException(status_code=404, detail="未配置默认代理实例")
    try:
        return await test_group_delays(instance_id, group)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

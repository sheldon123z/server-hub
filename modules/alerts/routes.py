"""告警管理 API 路由"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import get_current_user, require_role
from modules.alerts.models import AlertRuleCreate, AlertRuleUpdate
from modules.alerts.services import (
    acknowledge_alert,
    create_rule,
    delete_rule,
    get_active_alerts,
    get_alert_history,
    get_rule,
    list_rules,
    toggle_rule,
    update_rule,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/alerts", tags=["告警管理"])


# ---------------------------------------------------------------------------
# 活跃告警
# ---------------------------------------------------------------------------


@router.get("/active")
async def list_active_alerts(
    server_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    user=Depends(get_current_user),
):
    """获取当前活跃（firing）告警列表"""
    alerts = await get_active_alerts(server_id=server_id, limit=limit)
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/history")
async def list_alert_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    server_id: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status: str | None = Query(default=None),
    user=Depends(get_current_user),
):
    """分页查询告警历史"""
    result = await get_alert_history(limit=limit, offset=offset, server_id=server_id, severity=severity, status=status)
    return result


@router.put("/{alert_id}/acknowledge")
async def ack_alert(
    alert_id: int,
    user=Depends(require_role("admin")),
):
    """确认告警（标记已知晓）"""
    ok = await acknowledge_alert(alert_id, user["username"])
    if not ok:
        raise HTTPException(404, "告警不存在或已不处于 firing 状态")
    return {"ok": True}


# ---------------------------------------------------------------------------
# 规则 CRUD
# ---------------------------------------------------------------------------


@router.get("/rules")
async def list_alert_rules(
    enabled_only: bool = Query(default=False),
    user=Depends(get_current_user),
):
    """获取告警规则列表"""
    rules = await list_rules(enabled_only=enabled_only)
    return {"rules": rules, "count": len(rules)}


@router.post("/rules", status_code=201)
async def create_alert_rule(
    body: AlertRuleCreate,
    user=Depends(require_role("admin")),
):
    """创建告警规则"""
    rule = await create_rule(body.model_dump(), created_by=user["username"])
    return rule


@router.put("/rules/{rule_id}")
async def update_alert_rule(
    rule_id: str,
    body: AlertRuleUpdate,
    user=Depends(require_role("admin")),
):
    """更新告警规则"""
    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "没有要更新的字段")
    result = await update_rule(rule_id, data)
    if not result:
        raise HTTPException(404, "规则不存在")
    return result


@router.delete("/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    user=Depends(require_role("admin")),
):
    """删除告警规则"""
    # 内置规则不允许删除
    rule = await get_rule(rule_id)
    if not rule:
        raise HTTPException(404, "规则不存在")
    if rule_id.startswith("builtin-"):
        raise HTTPException(400, "内置规则不允许删除，可禁用")
    ok = await delete_rule(rule_id)
    return {"ok": ok}


@router.put("/rules/{rule_id}/toggle")
async def toggle_alert_rule(
    rule_id: str,
    enabled: bool = Query(...),
    user=Depends(require_role("admin")),
):
    """启用/禁用告警规则"""
    result = await toggle_rule(rule_id, enabled)
    if not result:
        raise HTTPException(404, "规则不存在")
    return result


@router.post("/rules/{rule_id}/test")
async def test_alert_rule(
    rule_id: str,
    user=Depends(require_role("admin")),
):
    """使用当前最新快照立即测试规则条件"""
    import json

    from database import get_db

    db = await get_db()
    row = await (
        await db.execute("SELECT data FROM metrics_latest WHERE server_id='local' ORDER BY collected_at DESC LIMIT 1")
    ).fetchone()
    if not row:
        raise HTTPException(503, "暂无指标快照，请稍后重试")

    try:
        snapshot = json.loads(row[0])
    except Exception:
        raise HTTPException(500, "指标快照解析失败")

    from modules.alerts.evaluator import evaluate_rule_now

    result = await evaluate_rule_now(rule_id, snapshot)
    return result


# ---------------------------------------------------------------------------
# 评估器状态（调试用）
# ---------------------------------------------------------------------------


@router.get("/states")
async def get_evaluator_states(user=Depends(require_role("admin"))):
    """返回评估器内存中所有规则的当前状态（调试用）"""
    from modules.alerts.evaluator import get_all_states

    return {"states": get_all_states()}

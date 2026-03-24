"""
系统监控 API 路由
提供实时指标、历史数据、WebSocket 推送、进程排行、inode、告警接口
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from auth.dependencies import get_current_user
from auth.jwt_handler import verify_token
from auth.user_store import get_user_by_name
from database import get_db
from modules.monitoring.collectors import (
    collect_all,
    collect_gpu,
    collect_inode,
    collect_top_processes,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["系统监控"])

# 单独的 WebSocket router，不带 prefix（由 main.py 直接挂载）
ws_router = APIRouter()


# ---------------------------------------------------------------------------
# WebSocket 管理器
# ---------------------------------------------------------------------------

class MetricsWSManager:
    """管理 WebSocket 连接，支持向所有客户端广播指标数据"""

    def __init__(self):
        self.connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.add(ws)
        logger.info(f"WebSocket 客户端连接 (当前: {len(self.connections)})")

    async def disconnect(self, ws: WebSocket):
        self.connections.discard(ws)
        logger.info(f"WebSocket 客户端断开 (当前: {len(self.connections)})")

    async def broadcast(self, data: dict):
        if not self.connections:
            return
        dead: set = set()
        payload = json.dumps(data, ensure_ascii=False)
        for ws in self.connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.add(ws)
        if dead:
            self.connections -= dead


ws_manager = MetricsWSManager()


# ---------------------------------------------------------------------------
# WebSocket 端点
# ---------------------------------------------------------------------------

async def _ws_authenticate(websocket: WebSocket) -> dict | None:
    """从 WebSocket cookie 或 query param 验证 JWT"""
    token = websocket.cookies.get("access_token")
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        return None

    payload = verify_token(token)
    if not payload or payload.get("type") != "access":
        return None

    user = await get_user_by_name(payload["sub"])
    if not user or user.get("disabled"):
        return None

    return user


@ws_router.websocket("/ws/metrics")
async def metrics_ws(websocket: WebSocket):
    """
    WebSocket 指标推送端点
    客户端连接后自动接收实时指标广播，发送任意消息作为心跳
    """
    user = await _ws_authenticate(websocket)
    if not user:
        await websocket.close(code=4001, reason="未授权")
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            # 等待客户端消息（心跳 ping 或其他）
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# REST 端点
# ---------------------------------------------------------------------------

@router.get("/realtime")
async def get_realtime(user=Depends(get_current_user)):
    """获取当前系统指标快照"""
    snapshot = await asyncio.get_event_loop().run_in_executor(None, collect_all)
    return snapshot


@router.get("/history")
async def get_history(
    metric: str,
    hours: int = Query(default=24, ge=1, le=720),
    user=Depends(get_current_user),
):
    """
    查询历史指标数据

    Args:
        metric: 指标名称 (cpu, memory, gpu, disk, network, disk_io, docker, all)
        hours: 查询最近多少小时的数据，默认 24
    """
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, value_json FROM metrics WHERE metric_type = 'all' AND timestamp >= ? ORDER BY timestamp ASC",
        (cutoff,),
    )
    rows = await cursor.fetchall()

    result = []
    for row in rows:
        ts = row[0]
        try:
            data = json.loads(row[1])
            if metric == "all":
                result.append({"timestamp": ts, "value": json.dumps(data)})
            else:
                value = data.get(metric)
                if value is not None:
                    result.append({"timestamp": ts, "value": value})
        except (json.JSONDecodeError, KeyError):
            continue

    return result


@router.get("/gpu")
async def get_gpu_detail(user=Depends(get_current_user)):
    """获取详细 GPU 信息"""
    gpu_info = await asyncio.get_event_loop().run_in_executor(None, collect_gpu)
    return gpu_info


@router.get("/top-processes")
async def get_top_processes(
    limit: int = Query(default=15, ge=1, le=50),
    user=Depends(get_current_user),
):
    """获取资源占用 Top N 进程排行"""
    data = await asyncio.get_event_loop().run_in_executor(None, lambda: collect_top_processes(limit))
    return data


@router.get("/inode")
async def get_inode(user=Depends(get_current_user)):
    """获取所有挂载点的 inode 使用情况"""
    data = await asyncio.get_event_loop().run_in_executor(None, collect_inode)
    return data


@router.get("/alerts/summary")
async def get_alerts_summary(user=Depends(get_current_user)):
    """获取告警摘要: 各级别数量 + 活跃规则数"""
    db = await get_db()

    # 活跃告警规则数
    cursor = await db.execute(
        "SELECT COUNT(*) FROM alert_rules WHERE enabled = 1"
    )
    row = await cursor.fetchone()
    active_rules = row[0] if row else 0

    # 最近24h各级别告警数
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor = await db.execute(
        "SELECT severity, COUNT(*) FROM alert_history WHERE created_at >= ? GROUP BY severity",
        (cutoff,),
    )
    rows = await cursor.fetchall()
    by_severity = {r[0]: r[1] for r in rows}

    return {
        "active_rules": active_rules,
        "last_24h": by_severity,
        "total_24h": sum(by_severity.values()),
    }


@router.get("/alerts/recent")
async def get_alerts_recent(
    limit: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
    user=Depends(get_current_user),
):
    """获取最近的告警历史记录"""
    db = await get_db()

    if severity:
        cursor = await db.execute(
            "SELECT * FROM alert_history WHERE severity = ? ORDER BY created_at DESC LIMIT ?",
            (severity, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM alert_history ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )

    rows = await cursor.fetchall()
    return [dict(r) for r in rows]

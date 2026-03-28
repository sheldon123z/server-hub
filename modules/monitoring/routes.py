"""
系统监控 API 路由
提供实时指标、历史数据、WebSocket 推送、进程排行、inode、告警接口
"""

import asyncio
import json
import logging
from collections import deque
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from auth.dependencies import get_current_user, get_user_from_access_token
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
    """WebSocket 管理器 — 支持 per-client 服务器订阅过滤 + 内存缓存"""

    def __init__(self):
        self._connections: dict[WebSocket, set[str]] = {}  # ws → subscribed server_ids
        self._cache: dict[str, deque] = {}  # server_id → recent snapshots (5min)
        self._cache_max = 60  # 5min @ 5s interval

    async def connect(self, ws: WebSocket, server_ids: set[str] | None = None):
        await ws.accept()
        subs = server_ids or {"local"}
        self._connections[ws] = subs
        logger.info(f"WebSocket 客户端连接, 订阅={subs} (当前: {len(self._connections)})")

        # Push cached data immediately so client doesn't wait
        for sid in subs:
            if sid in self._cache:
                for snapshot in self._cache[sid]:
                    try:
                        await ws.send_json(snapshot)
                    except Exception:
                        break

    def disconnect(self, ws: WebSocket):
        subs = self._connections.pop(ws, None)
        logger.info(f"WebSocket 客户端断开, 订阅={subs} (当前: {len(self._connections)})")

    async def update_subscription(self, ws: WebSocket, server_ids: set[str]):
        """Update a client's subscription list and push cached data for new subscriptions"""
        if ws in self._connections:
            old = self._connections[ws]
            self._connections[ws] = server_ids
            logger.debug(f"WebSocket 订阅更新: {old} → {server_ids}")

            # Push cached snapshots for newly subscribed servers
            new_sids = server_ids - old if "*" not in old else set()
            if "*" in server_ids:
                new_sids = set(self._cache.keys()) - (old if "*" not in old else set())
            for sid in new_sids:
                if sid in self._cache:
                    for snapshot in self._cache[sid]:
                        try:
                            await ws.send_json(snapshot)
                        except Exception:
                            return

    async def broadcast(self, message: dict):
        """Broadcast to subscribed clients only"""
        server_id = message.get("server_id", "local")

        # Update cache
        if server_id not in self._cache:
            self._cache[server_id] = deque(maxlen=self._cache_max)
        self._cache[server_id].append(message)

        # Send to subscribed clients
        if not self._connections:
            return
        disconnected = []
        for ws, subscribed in self._connections.items():
            if "*" in subscribed or server_id in subscribed:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


ws_manager = MetricsWSManager()


# ---------------------------------------------------------------------------
# WebSocket 端点
# ---------------------------------------------------------------------------

async def _ws_authenticate(websocket: WebSocket) -> dict | None:
    """从 WebSocket cookie 或 query param 验证 JWT"""
    token = websocket.cookies.get("access_token")
    if not token:
        token = websocket.query_params.get("token")
    return await get_user_from_access_token(token)


@ws_router.websocket("/ws/metrics")
async def metrics_ws(websocket: WebSocket):
    """
    WebSocket 指标推送端点
    客户端连接后自动接收实时指标广播。
    支持发送 {"type": "subscribe", "server_ids": ["local", "xxx"]} 更新订阅。
    其他消息视为心跳。
    """
    user = await _ws_authenticate(websocket)
    if not user:
        await websocket.close(code=4001, reason="未授权")
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "subscribe" and "server_ids" in msg:
                    server_ids = set(msg["server_ids"])
                    if server_ids:
                        await ws_manager.update_subscription(websocket, server_ids)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # heartbeat or malformed — ignore
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        ws_manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# REST 端点
# ---------------------------------------------------------------------------

@router.get("/realtime")
async def get_realtime(
    server_id: str = Query(default="local", description="服务器ID，默认 local 表示本机"),
    user=Depends(get_current_user),
):
    """获取当前系统指标快照，支持指定远程服务器"""
    if server_id == "local":
        snapshot = await asyncio.get_event_loop().run_in_executor(None, collect_all)
        return snapshot  # 保持向后兼容：本机直接返回原始快照格式

    # 远程服务器 — 通过 AgentClient 获取（工厂函数自动解密 token）
    from modules.servers.agent_client import get_agent_client

    try:
        client = await get_agent_client(server_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"服务器 {server_id} 不存在")

    try:
        result = await asyncio.wait_for(client.get_metrics(), timeout=10)
        # AgentClient 返回 {"ok": true, "data": {...}} — 解包以保持与本机格式一致
        if isinstance(result, dict) and "data" in result:
            snapshot = result["data"]
        else:
            snapshot = result
        return snapshot
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"远程指标获取失败: {e}")


@router.get("/history")
async def get_history(
    metric: str,
    hours: int = Query(default=24, ge=1, le=720),
    server_id: str = Query(default="local", description="服务器ID，默认只查本机数据"),
    user=Depends(get_current_user),
):
    """
    查询历史指标数据

    Args:
        metric: 指标名称 (cpu, memory, gpu, disk, network, disk_io, docker, all)
        hours: 查询最近多少小时的数据，默认 24
        server_id: 服务器ID，默认 "local" 只返回本机数据
    """
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    db = await get_db()
    cursor = await db.execute(
        "SELECT timestamp, value_json FROM metrics WHERE metric_type = 'all' "
        "AND (server_id = ? OR server_id IS NULL) AND timestamp >= ? ORDER BY timestamp ASC",
        (server_id, cutoff),
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
async def get_gpu_detail(
    server_id: str = Query(default="local", description="服务器ID"),
    user=Depends(get_current_user),
):
    """获取详细 GPU 信息，支持远程服务器"""
    if server_id == "local":
        gpu_info = await asyncio.get_event_loop().run_in_executor(None, collect_gpu)
        return gpu_info

    from modules.servers.agent_client import get_agent_client
    try:
        client = await get_agent_client(server_id)
        result = await asyncio.wait_for(client.get_metrics(), timeout=10)
        data = result.get("data", result) if isinstance(result, dict) else result
        return data.get("gpu", {}) if isinstance(data, dict) else {}
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=502, detail=f"远程 GPU 信��获取失败: {e}")


@router.get("/top-processes")
async def get_top_processes(
    limit: int = Query(default=15, ge=1, le=50),
    server_id: str = Query(default="local", description="服务器ID"),
    user=Depends(get_current_user),
):
    """获取资源占用 Top N 进程排行，支持远程服务器"""
    if server_id == "local":
        data = await asyncio.get_event_loop().run_in_executor(None, lambda: collect_top_processes(limit))
        return data

    # 远程服务器暂不支持进程列表（Agent 端无专用端点）
    return {"cpu": [], "memory": [], "gpu": [], "_remote": True, "_message": "远程服务器暂不支持进程排行"}


@router.get("/inode")
async def get_inode(user=Depends(get_current_user)):
    """获取所有挂载点的 inode 使用情况"""
    data = await asyncio.get_event_loop().run_in_executor(None, collect_inode)
    return data


@router.get("/alerts/summary")
async def get_alerts_summary(
    server_id: str = Query(default="local", description="服务器ID"),
    user=Depends(get_current_user),
):
    """获取告警摘要: 各级别数量 + 活跃规则数"""
    db = await get_db()

    # 活跃告警规则数
    cursor = await db.execute(
        "SELECT COUNT(*) FROM alert_rules WHERE enabled = 1"
    )
    row = await cursor.fetchone()
    active_rules = row[0] if row else 0

    # 最近24h各级别告警数（按 server_id 过滤）
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor = await db.execute(
        "SELECT severity, COUNT(*) FROM alert_history "
        "WHERE created_at >= ? AND (server_id = ? OR server_id IS NULL) GROUP BY severity",
        (cutoff, server_id),
    )
    rows = await cursor.fetchall()
    by_severity = {r[0]: r[1] for r in rows}

    return {
        "active_rules": active_rules,
        "critical": by_severity.get("critical", 0),
        "warning": by_severity.get("warning", 0),
        "info": by_severity.get("info", 0),
        "last_24h": by_severity,
        "total_24h": sum(by_severity.values()),
    }


@router.get("/alerts/recent")
async def get_alerts_recent(
    limit: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
    server_id: str = Query(default="local", description="服务器ID"),
    user=Depends(get_current_user),
):
    """获取最近的告警历史记录"""
    db = await get_db()

    base_where = "WHERE (server_id = ? OR server_id IS NULL)"
    params: list = [server_id]
    if severity:
        base_where += " AND severity = ?"
        params.append(severity)

    cursor = await db.execute(
        f"SELECT * FROM alert_history {base_where} ORDER BY created_at DESC LIMIT ?",
        (*params, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Fleet 舰队监控端点
# ---------------------------------------------------------------------------


def extract_metric(snapshot: dict, metric: str) -> dict:
    """Extract a specific metric value + timestamp from a full snapshot."""
    ts = snapshot.get("_timestamp", "")
    if metric == "cpu":
        return {"ts": ts, "value": snapshot.get("cpu", {}).get("overall_percent", 0)}
    elif metric == "memory":
        return {"ts": ts, "value": snapshot.get("memory", {}).get("percent", 0)}
    elif metric == "disk":
        parts = snapshot.get("disk", {}).get("partitions", [])
        root = next((p for p in parts if p.get("mountpoint") == "/"), parts[0] if parts else {})
        return {"ts": ts, "value": root.get("percent", 0)}
    elif metric == "gpu":
        return {"ts": ts, "value": snapshot.get("gpu", {}).get("utilization", 0)}
    elif metric == "swap":
        return {"ts": ts, "value": snapshot.get("memory", {}).get("swap_percent", 0)}
    elif metric == "network":
        net = snapshot.get("network", {})
        return {"ts": ts, "value": net.get("bytes_sent", 0) + net.get("bytes_recv", 0)}
    return {"ts": ts, "value": 0}


def extract_metric_percent(data: dict, metric: str) -> float:
    """Extract a single percent value from a metrics snapshot."""
    if metric == "cpu":
        return data.get("cpu", {}).get("overall_percent", 0)
    if metric == "memory":
        return data.get("memory", {}).get("percent", 0)
    if metric == "disk":
        parts = data.get("disk", {}).get("partitions", [])
        root = next((p for p in parts if p.get("mountpoint") == "/"), parts[0] if parts else {})
        return root.get("percent", 0)
    if metric == "gpu":
        return data.get("gpu", {}).get("utilization", 0)
    if metric == "swap":
        return data.get("memory", {}).get("swap_percent", 0)
    return 0


@router.get("/fleet/overview")
async def fleet_overview(user=Depends(get_current_user)):
    """全舰队概览 — 各服务器最新指标 + 聚合统计"""
    from modules.monitoring.metrics_store import get_metrics_store

    store = get_metrics_store()
    return await store.get_fleet_summary()


@router.get("/fleet/compare")
async def fleet_compare(
    server_ids: str = Query(..., description="逗号分隔的服务器ID"),
    metric: str = Query(default="cpu", description="对比指标"),
    hours: int = Query(default=1, ge=1, le=72),
    user=Depends(get_current_user),
):
    """多服务器指标对比"""
    from modules.monitoring.metrics_store import get_metrics_store

    store = get_metrics_store()
    ids = [s.strip() for s in server_ids.split(",") if s.strip()]
    # 并行查询所有服务器的历史数据
    histories = await asyncio.gather(*(store.query_history(sid, hours) for sid in ids))
    result = {sid: [extract_metric(h, metric) for h in hist] for sid, hist in zip(ids, histories)}
    return {"server_ids": ids, "metric": metric, "hours": hours, "data": result}


@router.get("/fleet/heatmap")
async def fleet_heatmap(user=Depends(get_current_user)):
    """热力图数据 — 所有服务器 × 所有指标"""
    from modules.monitoring.metrics_store import get_metrics_store

    store = get_metrics_store()
    fleet = await store.query_fleet_latest()

    metrics_list = ["cpu", "memory", "disk", "gpu", "swap"]

    # 一次查询加载所有服务器名称，避免 N+1
    db = await get_db()
    name_rows = await (await db.execute("SELECT id, name FROM servers")).fetchall()
    name_map = {r[0]: r[1] for r in name_rows}

    servers = []
    matrix = []
    for sid, data in fleet.items():
        servers.append({"id": sid, "name": name_map.get(sid, sid)})
        matrix.append([extract_metric_percent(data, m) for m in metrics_list])

    return {"servers": servers, "metrics": metrics_list, "matrix": matrix}


@router.get("/fleet/top")
async def fleet_top(
    metric: str = Query(default="cpu", description="排序指标"),
    limit: int = Query(default=10, ge=1, le=50),
    user=Depends(get_current_user),
):
    """Top N 服务器排行"""
    from modules.monitoring.metrics_store import get_metrics_store

    store = get_metrics_store()
    summary = await store.get_fleet_summary()
    servers = summary.get("servers", [])

    key = f"{metric}_percent"
    sorted_servers = sorted(servers, key=lambda s: s.get(key, 0), reverse=True)
    return sorted_servers[:limit]

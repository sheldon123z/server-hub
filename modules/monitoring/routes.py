"""
系统监控 API 路由
提供实时指标、历史数据、WebSocket 推送、进程排行、inode、告警接口
"""

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from auth.dependencies import get_current_user, get_user_from_access_token
from modules.monitoring.collectors import (
    collect_all,
    collect_gpu,
    collect_inode,
    collect_top_processes,
)
from modules.monitoring.services import (
    get_alerts_recent_data,
    get_alerts_summary_data,
    get_fleet_compare,
    get_fleet_heatmap,
    get_fleet_overview,
    get_fleet_top,
    get_history_data,
)
from modules.monitoring.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/monitoring", tags=["系统监控"])

# 单独的 WebSocket router，不带 prefix（由 main.py 直接挂载）
ws_router = APIRouter()


# ---------------------------------------------------------------------------
# WebSocket 端点
# ---------------------------------------------------------------------------


async def _ws_authenticate(websocket: WebSocket) -> dict | None:
    """从 WebSocket cookie 验证 JWT (CWE-598: 不从 query param 读取 token)"""
    token = websocket.cookies.get("access_token")
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
        logger.debug("WebSocket 客户端主动断开")
    except Exception as e:
        logger.warning("WebSocket 异常断开: %s", e)
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
        snapshot = await asyncio.to_thread(collect_all)
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
    return await get_history_data(metric, hours, server_id)


@router.get("/gpu")
async def get_gpu_detail(
    server_id: str = Query(default="local", description="服务器ID"),
    user=Depends(get_current_user),
):
    """获取详细 GPU 信息，支持远程服务器"""
    if server_id == "local":
        gpu_info = await asyncio.to_thread(collect_gpu)
        return gpu_info

    from modules.servers.agent_client import get_agent_client

    try:
        client = await get_agent_client(server_id)
        result = await asyncio.wait_for(client.get_metrics(), timeout=10)
        data = result.get("data", result) if isinstance(result, dict) else result
        return data.get("gpu", {}) if isinstance(data, dict) else {}
    except Exception as e:
        from fastapi import HTTPException

        raise HTTPException(status_code=502, detail=f"远程 GPU 信息获取失败: {e}")


@router.get("/top-processes")
async def get_top_processes(
    limit: int = Query(default=15, ge=1, le=50),
    server_id: str = Query(default="local", description="服务器ID"),
    user=Depends(get_current_user),
):
    """获取资源占用 Top N 进程排行，支持远程服务器"""
    if server_id == "local":
        data = await asyncio.to_thread(collect_top_processes, limit)
        return data

    # 远程服务器暂不支持进程列表（Agent 端无专用端点）
    return {"cpu": [], "memory": [], "gpu": [], "_remote": True, "_message": "远程服务器暂不支持进程排行"}


@router.get("/inode")
async def get_inode(user=Depends(get_current_user)):
    """获取所有挂载点的 inode 使用情况"""
    data = await asyncio.to_thread(collect_inode)
    return data


@router.get("/alerts/summary")
async def get_alerts_summary(
    server_id: str = Query(default="local", description="服务器ID"),
    user=Depends(get_current_user),
):
    """获取告警摘要: 各级别数量 + 活跃规则数"""
    return await get_alerts_summary_data(server_id)


@router.get("/alerts/recent")
async def get_alerts_recent(
    limit: int = Query(default=20, ge=1, le=100),
    severity: str | None = Query(default=None),
    server_id: str = Query(default="local", description="服务器ID"),
    user=Depends(get_current_user),
):
    """获取最近的告警历史记录"""
    return await get_alerts_recent_data(limit, severity, server_id)


# ---------------------------------------------------------------------------
# Fleet 舰队监控端点
# ---------------------------------------------------------------------------


@router.get("/fleet/overview")
async def fleet_overview(user=Depends(get_current_user)):
    """全舰队概览 — 各服务器最新指标 + 聚合统计"""
    return await get_fleet_overview()


@router.get("/fleet/compare")
async def fleet_compare(
    server_ids: str = Query(..., description="逗号分隔的服务器ID"),
    metric: str = Query(default="cpu", description="对比指标"),
    hours: int = Query(default=1, ge=1, le=72),
    user=Depends(get_current_user),
):
    """多服务器指标对比"""
    ids = [s.strip() for s in server_ids.split(",") if s.strip()]
    return await get_fleet_compare(ids, metric, hours)


@router.get("/fleet/heatmap")
async def fleet_heatmap(user=Depends(get_current_user)):
    """热力图数据 — 所有服务器 × 所有指标"""
    return await get_fleet_heatmap()


@router.get("/fleet/top")
async def fleet_top(
    metric: str = Query(default="cpu", description="排序指标"),
    limit: int = Query(default=10, ge=1, le=50),
    user=Depends(get_current_user),
):
    """Top N 服务器排行"""
    return await get_fleet_top(metric, limit)

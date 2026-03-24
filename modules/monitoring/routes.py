"""
系统监控 API 路由
提供实时指标、历史数据和 GPU 详情接口
"""

import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query

from auth.dependencies import get_current_user
from database import get_db
from modules.monitoring.collectors import collect_all, collect_gpu

router = APIRouter(prefix="/api/monitoring", tags=["系统监控"])


@router.get("/realtime")
async def get_realtime(user=Depends(get_current_user)):
    """获取当前系统指标快照"""
    import asyncio
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
        metric: 指标名称 (cpu, memory, gpu, disk)
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
    import asyncio
    gpu_info = await asyncio.get_event_loop().run_in_executor(None, collect_gpu)
    return gpu_info

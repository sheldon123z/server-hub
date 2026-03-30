"""
监控业务逻辑层
提供指标提取、Fleet 舰队查询等业务函数，供 routes.py 调用
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from database import get_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 指标提取工具函数
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


# ---------------------------------------------------------------------------
# Fleet 舰队查询业务函数
# ---------------------------------------------------------------------------


async def get_fleet_overview() -> dict:
    """全舰队概览 — 各服务器最新指标 + 聚合统计"""
    from modules.monitoring.metrics_store import get_metrics_store

    store = get_metrics_store()
    return await store.get_fleet_summary()


async def get_fleet_compare(server_ids: list[str], metric: str, hours: int) -> dict:
    """多服务器指标对比"""
    from modules.monitoring.metrics_store import get_metrics_store

    store = get_metrics_store()
    histories = await asyncio.gather(*(store.query_history(sid, hours) for sid in server_ids))
    result = {sid: [extract_metric(h, metric) for h in hist] for sid, hist in zip(server_ids, histories, strict=False)}
    return {"server_ids": server_ids, "metric": metric, "hours": hours, "data": result}


async def get_fleet_heatmap() -> dict:
    """热力图数据 — 所有服务器 x 所有指标"""
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


async def get_fleet_top(metric: str, limit: int) -> list:
    """Top N 服务器排行"""
    from modules.monitoring.metrics_store import get_metrics_store

    store = get_metrics_store()
    summary = await store.get_fleet_summary()
    servers = summary.get("servers", [])

    key = f"{metric}_percent"
    sorted_servers = sorted(servers, key=lambda s: s.get(key, 0), reverse=True)
    return sorted_servers[:limit]


async def get_history_data(metric: str, hours: int, server_id: str) -> list:
    """查询历史指标数据

    短期查询 (<=720h) 使用 LIMIT 500 防止大查询拖慢 SQLite。
    长期查询 (>720h) 取全量数据后在应用层均匀降采样到 max_rows 条。
    """
    max_rows = 500
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    db = await get_db()

    if hours > 720:
        # 长期查询: 取全量数据，应用层降采样
        cursor = await db.execute(
            "SELECT timestamp, value_json FROM metrics WHERE metric_type = 'all' "
            "AND server_id = ? AND timestamp >= ? "
            "ORDER BY timestamp ASC",
            (server_id, cutoff),
        )
    else:
        # 短期查询: LIMIT 限制即可
        cursor = await db.execute(
            "SELECT timestamp, value_json FROM metrics WHERE metric_type = 'all' "
            "AND server_id = ? AND timestamp >= ? "
            "ORDER BY timestamp ASC LIMIT ?",
            (server_id, cutoff, max_rows),
        )
    rows = await cursor.fetchall()

    # 长期查询均匀降采样: 按 stride 抽取
    downsample_step = max(1, len(rows) // max_rows) if hours > 720 else 1

    result = []
    for i, row in enumerate(rows):
        if downsample_step > 1 and i % downsample_step != 0:
            continue
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

    # 降采样后仍可能略多于 max_rows（取整误差），截断保证上限
    return result[:max_rows]


async def get_alerts_summary_data(server_id: str) -> dict:
    """获取告警摘要: 各级别数量 + 活跃规则数"""
    db = await get_db()

    # 活跃告警规则数
    cursor = await db.execute("SELECT COUNT(*) FROM alert_rules WHERE enabled = 1")
    row = await cursor.fetchone()
    active_rules = row[0] if row else 0

    # 最近24h各级别告警数（按 server_id 过滤）
    cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
    cursor = await db.execute(
        "SELECT severity, COUNT(*) FROM alert_history WHERE created_at >= ? AND server_id = ? GROUP BY severity",
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


async def get_alerts_recent_data(limit: int, severity: str | None, server_id: str) -> list:
    """获取最近的告警历史记录"""
    db = await get_db()

    base_where = "WHERE server_id = ?"
    params: list = [server_id]
    if severity:
        base_where += " AND severity = ?"
        params.append(severity)

    cursor = await db.execute(
        f"SELECT * FROM alert_history {base_where} ORDER BY created_at DESC LIMIT ?",  # noqa: S608 — where 由代码构建
        (*params, limit),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]

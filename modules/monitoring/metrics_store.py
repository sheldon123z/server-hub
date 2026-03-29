"""指标存储抽象层 — 统一 metrics 读写接口

# Capacity estimate:
# - 10 servers × 1440 samples/day = 14,400 rows/day → SQLite handles easily
# - 100 servers × 1440 = 144,000 rows/day → OK for 90-day retention (~13M rows)
# - 500+ servers → Consider PostgreSQL/TimescaleDB migration
"""

import json
import logging
from datetime import datetime, timedelta

from database import get_db

logger = logging.getLogger(__name__)


class MetricsStore:
    """SQLite metrics store implementation.

    Capacity: handles up to ~100 servers comfortably with 90-day retention.
    For 500+ servers, migrate to PostgreSQL/TimescaleDB (swap this class).
    """

    async def insert(self, server_id: str, metric_type: str, value_json: str) -> None:
        db = await get_db()
        await db.execute(
            "INSERT INTO metrics (server_id, metric_type, value_json) VALUES (?, ?, ?)",
            (server_id, metric_type, value_json),
        )
        await db.commit()

    async def bulk_insert(self, rows: list[tuple]) -> None:
        """rows: list of (server_id, metric_type, value_json)"""
        if not rows:
            return
        db = await get_db()
        await db.executemany(
            "INSERT INTO metrics (server_id, metric_type, value_json) VALUES (?, ?, ?)",
            rows,
        )
        await db.commit()

    async def query_latest(self, server_id: str = "local") -> dict | None:
        """Get the most recent metric snapshot for a server."""
        db = await get_db()
        row = await (
            await db.execute(
                "SELECT value_json FROM metrics WHERE server_id = ? AND metric_type = 'all' "
                "ORDER BY timestamp DESC LIMIT 1",
                (server_id,),
            )
        ).fetchone()
        if row:
            return json.loads(row[0])
        return None

    async def query_fleet_latest(self) -> dict[str, dict]:
        """Get the latest metrics for ALL servers in one query.

        Uses the metrics_latest table (UPSERT'd by scheduler) for O(N) lookup
        instead of a self-join on the large metrics table.
        Falls back to the old self-join query if metrics_latest is empty.
        """
        db = await get_db()
        # Fast path: metrics_latest table (populated by scheduler UPSERT)
        rows = await (
            await db.execute("SELECT server_id, data FROM metrics_latest")
        ).fetchall()
        if rows:
            result = {}
            for row in rows:
                try:
                    result[row[0]] = json.loads(row[1])
                except (json.JSONDecodeError, IndexError):
                    continue
            return result

        # Fallback: self-join (for first startup before any UPSERT)
        rows = await (
            await db.execute(
                "SELECT m.server_id, m.value_json FROM metrics m "
                "INNER JOIN (SELECT server_id, MAX(timestamp) AS max_ts FROM metrics "
                "WHERE metric_type = 'all' GROUP BY server_id) latest "
                "ON m.server_id = latest.server_id AND m.timestamp = latest.max_ts "
                "AND m.metric_type = 'all'"
            )
        ).fetchall()
        result = {}
        for row in rows:
            try:
                result[row[0]] = json.loads(row[1])
            except (json.JSONDecodeError, IndexError):
                continue
        return result

    async def query_history(self, server_id: str, hours: int = 24, metric_type: str = "all") -> list[dict]:
        """Get historical metrics for a server."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        db = await get_db()
        rows = await (
            await db.execute(
                "SELECT timestamp, value_json FROM metrics "
                "WHERE server_id = ? AND metric_type = ? AND timestamp >= ? "
                "ORDER BY timestamp ASC",
                (server_id, metric_type, cutoff),
            )
        ).fetchall()
        result = []
        for row in rows:
            try:
                data = json.loads(row[1])
                data["_timestamp"] = row[0]
                result.append(data)
            except (json.JSONDecodeError, IndexError):
                continue
        return result

    async def query_fleet_history(self, hours: int = 1, metric: str = "cpu") -> dict[str, list]:
        """Get historical metrics for ALL servers.

        Queries per-server_id to leverage idx_metrics_server_time index
        instead of a full table scan with only timestamp filter.
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        db = await get_db()

        # Get distinct server_ids first, then query each with index
        sid_rows = await (
            await db.execute("SELECT DISTINCT server_id FROM metrics_latest")
        ).fetchall()
        if not sid_rows:
            # Fallback: discover from metrics table
            sid_rows = await (
                await db.execute(
                    "SELECT DISTINCT server_id FROM metrics WHERE metric_type = 'all' AND timestamp >= ?",
                    (cutoff,),
                )
            ).fetchall()

        result: dict[str, list] = {}
        for (sid,) in sid_rows:
            rows = await (
                await db.execute(
                    "SELECT timestamp, value_json FROM metrics "
                    "WHERE server_id = ? AND metric_type = 'all' AND timestamp >= ? "
                    "ORDER BY timestamp ASC",
                    (sid, cutoff),
                )
            ).fetchall()
            entries = []
            for row in rows:
                try:
                    data = json.loads(row[1])
                    data["_timestamp"] = row[0]
                    entries.append(data)
                except (json.JSONDecodeError, IndexError):
                    continue
            if entries:
                result[sid] = entries
        return result

    async def get_fleet_summary(self) -> dict:
        """Get aggregate fleet metrics summary.
        遍历所有已注册服务器（非仅有 metrics 的），新注册无数据的也会显示。
        """
        fleet_latest = await self.query_fleet_latest()

        # Load ALL registered servers (not just those with metrics)
        db = await get_db()
        server_rows = await (await db.execute("SELECT id, name, status FROM servers")).fetchall()
        if not server_rows:
            return {"servers": [], "aggregate": {"total_servers": 0, "online": 0, "offline": 0, "degraded": 0}}

        servers = []
        total_cpu = total_mem = total_disk = 0
        count = 0

        for row in server_rows:
            sid, name, status = row[0], row[1], row[2]
            metrics = fleet_latest.get(sid, {})
            cpu = metrics.get("cpu", {}).get("overall_percent", 0) if isinstance(metrics.get("cpu"), dict) else 0
            mem = metrics.get("memory", {}).get("percent", 0) if isinstance(metrics.get("memory"), dict) else 0
            disk_parts = metrics.get("disk", {}).get("partitions", []) if isinstance(metrics.get("disk"), dict) else []
            root_disk = next((p for p in disk_parts if p.get("mountpoint") == "/"), disk_parts[0] if disk_parts else {})
            disk = root_disk.get("percent", 0)
            gpu = metrics.get("gpu", {}).get("utilization", 0) if isinstance(metrics.get("gpu"), dict) else 0

            servers.append(
                {
                    "id": sid,
                    "name": name,
                    "status": status,
                    "cpu_percent": round(cpu, 1),
                    "memory_percent": round(mem, 1),
                    "disk_percent": round(disk, 1),
                    "gpu_percent": round(gpu, 1),
                    "hostname": metrics.get("hostname", name),
                    "uptime": metrics.get("uptime", 0),
                }
            )

            if status == "online":
                total_cpu += cpu
                total_mem += mem
                total_disk += disk
                count += 1

        online = sum(1 for s in servers if s["status"] == "online")
        offline = sum(1 for s in servers if s["status"] == "offline")

        return {
            "servers": servers,
            "aggregate": {
                "total_servers": len(servers),
                "online": online,
                "offline": offline,
                "degraded": len(servers) - online - offline,
                "avg_cpu": round(total_cpu / max(count, 1), 1),
                "avg_memory": round(total_mem / max(count, 1), 1),
                "avg_disk": round(total_disk / max(count, 1), 1),
            },
        }

    async def cleanup(self, retention_days: int = 90) -> int:
        """Delete metrics older than retention period. Returns deleted count.

        Uses server_id in WHERE clause to leverage idx_metrics_server_time index.
        """
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        db = await get_db()
        # Per-server_id deletion leverages the compound index
        rows = await (
            await db.execute("SELECT DISTINCT server_id FROM metrics WHERE timestamp < ?", (cutoff,))
        ).fetchall()
        total = 0
        for (sid,) in rows:
            cursor = await db.execute(
                "DELETE FROM metrics WHERE server_id = ? AND timestamp < ?",
                (sid, cutoff),
            )
            total += cursor.rowcount
        await db.commit()
        return total


# Singleton
_store: MetricsStore | None = None


def get_metrics_store() -> MetricsStore:
    global _store
    if _store is None:
        _store = MetricsStore()
    return _store

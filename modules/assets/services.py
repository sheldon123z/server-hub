"""资产台账 — 自动发现 + CRUD，支持多服务器"""

import json
import logging
from datetime import datetime

from database import get_db

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 本地资产发现
# ---------------------------------------------------------------------------


async def discover_all(server_id: str = "local") -> dict:
    """执行资产发现并 upsert 到 assets 表。

    server_id == "local" 时直接调用本地采集模块；
    远程服务器则通过 AgentClient 调用 /assets/discover 端点。
    """
    if server_id != "local":
        return await _discover_remote(server_id)

    return await _discover_local(server_id)


async def _discover_local(server_id: str = "local") -> dict:
    """本地资产发现 — 调用各模块采集器"""
    db = await get_db()
    now = datetime.utcnow().isoformat()
    stats = {"service": 0, "container": 0, "compose": 0, "port": 0, "storage": 0}

    # ─── systemd 服务 ───
    try:
        from modules.services.services import list_services

        services = await list_services()
        for s in services:
            aid = f"service:{s['name']}"
            status = "running" if s.get("active") else "stopped"
            props = json.dumps(
                {
                    "enabled": s.get("enabled", False),
                    "description": s.get("description", ""),
                },
                ensure_ascii=False,
            )
            await _upsert_asset(db, aid, "service", s["name"], status, props, now, server_id=server_id)
            stats["service"] += 1
    except Exception as e:
        logger.error("服务资产发现失败: %s", e)

    # ─── Docker Compose 堆栈 ───
    compose_containers: dict[str, list[str]] = {}
    try:
        from modules.docker.services import list_compose_stacks

        stacks = await list_compose_stacks()
        for st in stacks:
            aid = f"compose:{st['name']}"
            status = "running" if st.get("running") else "stopped"
            props = json.dumps(
                {
                    "path": st.get("path", ""),
                    "display_name": st.get("display_name", st["name"]),
                    "container_count": st.get("container_count", 0),
                },
                ensure_ascii=False,
            )
            await _upsert_asset(db, aid, "compose", st["name"], status, props, now, server_id=server_id)
            stats["compose"] += 1
            compose_containers[st["name"]] = []
    except Exception as e:
        logger.error("Compose 堆栈发现失败: %s", e)

    # ─── Docker 容器 ───
    try:
        from modules.docker.services import list_containers

        containers = await list_containers(all=True)
        for c in containers:
            name = c.get("Names") or c.get("name", "?")
            name = name.lstrip("/")
            aid = f"container:{name}"
            raw_status = c.get("Status") or c.get("status", "unknown")
            status = "running" if "Up" in raw_status else "stopped"
            props = json.dumps(
                {
                    "image": c.get("Image") or c.get("image", ""),
                    "status_detail": raw_status,
                },
                ensure_ascii=False,
            )
            deps = []
            for stack_name in compose_containers:
                if name.startswith((stack_name, "docker-")) or stack_name in name:
                    deps.append(f"compose:{stack_name}")
                    compose_containers[stack_name].append(aid)
                    break
            await _upsert_asset(db, aid, "container", name, status, props, now, deps, server_id=server_id)
            stats["container"] += 1
    except Exception as e:
        logger.error("容器资产发现失败: %s", e)

    # 回写 compose 的依赖
    for stack_name, container_ids in compose_containers.items():
        if container_ids:
            await db.execute(
                "UPDATE assets SET dependencies = ? WHERE id = ? AND server_id = ?",
                (json.dumps(container_ids, ensure_ascii=False), f"compose:{stack_name}", server_id),
            )

    # ─── 监听端口 ───
    try:
        from modules.network.services import get_listening_ports

        ports = await get_listening_ports()
        service_names = []
        if stats["service"] > 0:
            try:
                from modules.services.services import list_services as _ls

                service_names = [s["name"] for s in await _ls()]
            except Exception as e:
                logger.debug("加载服务名列表失败: %s", e)
        for p in ports:
            port_str = f"{p['port']}/{p['proto']}"
            aid = f"port:{port_str}"
            props = json.dumps(
                {
                    "local_addr": p.get("local_addr", ""),
                    "pid": p.get("pid", 0),
                    "process": p.get("process", ""),
                },
                ensure_ascii=False,
            )
            deps = []
            proc = p.get("process", "")
            if proc and service_names:
                for s_name in service_names:
                    if s_name in proc:
                        deps.append(f"service:{s_name}")
                        break
            await _upsert_asset(db, aid, "port", port_str, "listening", props, now, deps, server_id=server_id)
            stats["port"] += 1
    except Exception as e:
        logger.error("端口资产发现失败: %s", e)

    # ─── 存储挂载点 ───
    try:
        from modules.dashboard.collectors import get_extra_disks

        disks = get_extra_disks()
        for d in disks:
            mp = d["mountpoint"]
            aid = f"storage:{mp}"
            props = json.dumps(
                {
                    "device": d.get("device", ""),
                    "total": d.get("total", 0),
                    "used": d.get("used", 0),
                    "percent": d.get("percent", 0),
                },
                ensure_ascii=False,
            )
            status = "warning" if d.get("percent", 0) > 85 else "ok"
            await _upsert_asset(db, aid, "storage", mp, status, props, now, server_id=server_id)
            stats["storage"] += 1
    except Exception as e:
        logger.error("存储资产发现失败: %s", e)

    await db.commit()
    logger.info("资产发现完成 [%s]: %s", server_id, stats)
    return stats


# ---------------------------------------------------------------------------
# 远程资产发现
# ---------------------------------------------------------------------------


async def _discover_remote(server_id: str) -> dict:
    """通过 AgentClient 从远程服务器发现资产"""
    from modules.servers.agent_client import get_agent_client

    client = await get_agent_client(server_id)
    result = await client._request("GET", "/assets/discover", timeout=30.0)
    if not result.get("ok"):
        raise RuntimeError(f"远程资产发现失败: {result.get('error', 'unknown')}")

    remote_assets = result["data"]
    if not isinstance(remote_assets, list):
        return {"total": 0}

    db = await get_db()
    now = datetime.utcnow().isoformat()
    stats: dict[str, int] = {}

    for a in remote_assets:
        aid = a.get("id", "")
        atype = a.get("type", "unknown")
        name = a.get("name", aid)
        status = a.get("status", "unknown")
        props = (
            json.dumps(a.get("properties", {}), ensure_ascii=False) if isinstance(a.get("properties"), dict) else "{}"
        )
        deps = a.get("dependencies", [])
        await _upsert_asset(
            db, aid, atype, name, status, props, now, deps if isinstance(deps, list) else None, server_id=server_id
        )
        stats[atype] = stats.get(atype, 0) + 1

    await db.commit()
    logger.info("远程资产发现完成 [%s]: %s", server_id, stats)
    return stats


# ---------------------------------------------------------------------------
# CRUD 辅助
# ---------------------------------------------------------------------------


async def _upsert_asset(
    db,
    aid: str,
    atype: str,
    name: str,
    status: str,
    properties: str,
    last_seen: str,
    dependencies: list | None = None,
    *,
    server_id: str = "local",
):
    """插入或更新资产（不覆盖手动录入的资产）"""
    # assets.id 是 PRIMARY KEY，不同服务器可能有同名资产 (如 service:nginx)
    # 对非 local 服务器，id 加 server_id 前缀保证全局唯一
    unique_id = f"{server_id}:{aid}" if server_id != "local" else aid

    existing = await db.execute("SELECT is_manual FROM assets WHERE id = ? AND server_id = ?", (unique_id, server_id))
    row = await existing.fetchone()
    deps_json = json.dumps(dependencies, ensure_ascii=False) if dependencies else None

    if row:
        if row[0]:  # is_manual=1, 只更新 last_seen 和 status
            await db.execute(
                "UPDATE assets SET status = ?, last_seen = ? WHERE id = ? AND server_id = ?",
                (status, last_seen, unique_id, server_id),
            )
        else:
            await db.execute(
                "UPDATE assets SET status = ?, properties = ?, last_seen = ?, dependencies = COALESCE(?, dependencies) "
                "WHERE id = ? AND server_id = ?",
                (status, properties, last_seen, deps_json, unique_id, server_id),
            )
    else:
        await db.execute(
            "INSERT INTO assets (id, type, name, status, properties, dependencies, last_seen, server_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (unique_id, atype, name, status, properties, deps_json, last_seen, server_id),
        )


async def get_assets(asset_type: str = "", server_id: str = "local") -> list[dict]:
    """获取资产列表（按 server_id 过滤）"""
    db = await get_db()
    if asset_type:
        cursor = await db.execute(
            "SELECT id, type, name, status, properties, dependencies, is_manual, last_seen "
            "FROM assets WHERE type = ? AND server_id = ? ORDER BY name",
            (asset_type, server_id),
        )
    else:
        cursor = await db.execute(
            "SELECT id, type, name, status, properties, dependencies, is_manual, last_seen "
            "FROM assets WHERE server_id = ? ORDER BY type, name",
            (server_id,),
        )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        item = {"id": r[0], "type": r[1], "name": r[2], "status": r[3], "is_manual": bool(r[6]), "last_seen": r[7]}
        for field, idx in [("properties", 4), ("dependencies", 5)]:
            if r[idx]:
                try:
                    item[field] = json.loads(r[idx])
                except (json.JSONDecodeError, TypeError):
                    item[field] = r[idx]
            else:
                item[field] = {} if field == "properties" else []
        results.append(item)
    return results


async def generate_topology_mermaid(server_id: str = "local") -> str:
    """生成 Mermaid 拓扑图"""
    assets = await get_assets(server_id=server_id)
    lines = ["graph TD"]

    type_icons = {"service": "⚙️", "container": "🐳", "compose": "📦", "port": "🌐", "storage": "💾"}
    status_styles = {
        "running": "fill:#22c55e,color:#000",
        "stopped": "fill:#ef4444,color:#fff",
        "listening": "fill:#38bdf8,color:#000",
        "ok": "fill:#22c55e,color:#000",
        "warning": "fill:#fbbf24,color:#000",
        "unknown": "fill:#94a3b8,color:#000",
    }

    for a in assets:
        icon = type_icons.get(a["type"], "")
        node_id = a["id"].replace(":", "_").replace("/", "_").replace("-", "_").replace(".", "_")
        label = f"{icon} {a['name']}"
        lines.append(f'    {node_id}["{label}"]')

    for a in assets:
        deps = a.get("dependencies", [])
        if isinstance(deps, list):
            src = a["id"].replace(":", "_").replace("/", "_").replace("-", "_").replace(".", "_")
            for dep_id in deps:
                tgt = dep_id.replace(":", "_").replace("/", "_").replace("-", "_").replace(".", "_")
                lines.append(f"    {tgt} --> {src}")

    for a in assets:
        node_id = a["id"].replace(":", "_").replace("/", "_").replace("-", "_").replace(".", "_")
        style = status_styles.get(a["status"], status_styles["unknown"])
        lines.append(f"    style {node_id} {style}")

    return "\n".join(lines)

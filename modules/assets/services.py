"""资产台账 — 自动发现 + CRUD"""

import json
import logging
from datetime import datetime

from database import get_db

logger = logging.getLogger(__name__)


async def discover_all() -> dict:
    """执行全量资产发现，upsert 到 assets 表。返回发现统计。"""
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
            props = json.dumps({
                "enabled": s.get("enabled", False),
                "description": s.get("description", ""),
            }, ensure_ascii=False)
            await _upsert_asset(db, aid, "service", s["name"], status, props, now)
            stats["service"] += 1
    except Exception as e:
        logger.error(f"服务资产发现失败: {e}")

    # ─── Docker Compose 堆栈 ───
    compose_containers = {}  # stack_name -> [container_ids]
    try:
        from modules.docker.services import list_compose_stacks
        stacks = await list_compose_stacks()
        for st in stacks:
            aid = f"compose:{st['name']}"
            status = "running" if st.get("running") else "stopped"
            props = json.dumps({
                "path": st.get("path", ""),
                "display_name": st.get("display_name", st["name"]),
                "container_count": st.get("container_count", 0),
            }, ensure_ascii=False)
            await _upsert_asset(db, aid, "compose", st["name"], status, props, now)
            stats["compose"] += 1
            compose_containers[st["name"]] = []
    except Exception as e:
        logger.error(f"Compose 堆栈发现失败: {e}")

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
            props = json.dumps({
                "image": c.get("Image") or c.get("image", ""),
                "status_detail": raw_status,
            }, ensure_ascii=False)
            # 推断所属堆栈
            deps = []
            for stack_name in compose_containers:
                if name.startswith(stack_name) or name.startswith(f"docker-") or stack_name in name:
                    deps.append(f"compose:{stack_name}")
                    compose_containers[stack_name].append(aid)
                    break
            await _upsert_asset(db, aid, "container", name, status, props, now, deps)
            stats["container"] += 1
    except Exception as e:
        logger.error(f"容器资产发现失败: {e}")

    # 回写 compose 的依赖（堆栈→容器）
    for stack_name, container_ids in compose_containers.items():
        if container_ids:
            await db.execute(
                "UPDATE assets SET dependencies = ? WHERE id = ?",
                (json.dumps(container_ids, ensure_ascii=False), f"compose:{stack_name}"),
            )

    # ─── 监听端口 ───
    try:
        from modules.network.services import get_listening_ports
        ports = await get_listening_ports()
        # 预加载服务名列表，避免在循环中重复调用
        service_names = []
        if stats["service"] > 0:
            try:
                from modules.services.services import list_services as _ls
                service_names = [s["name"] for s in await _ls()]
            except Exception:
                pass
        for p in ports:
            port_str = f"{p['port']}/{p['proto']}"
            aid = f"port:{port_str}"
            props = json.dumps({
                "local_addr": p.get("local_addr", ""),
                "pid": p.get("pid", 0),
                "process": p.get("process", ""),
            }, ensure_ascii=False)
            # 推断端口所属服务
            deps = []
            proc = p.get("process", "")
            if proc and service_names:
                for s_name in service_names:
                    if s_name in proc:
                        deps.append(f"service:{s_name}")
                        break
            await _upsert_asset(db, aid, "port", port_str, "listening", props, now, deps)
            stats["port"] += 1
    except Exception as e:
        logger.error(f"端口资产发现失败: {e}")

    # ─── 存储挂载点 ───
    try:
        from modules.dashboard.collectors import get_extra_disks
        disks = get_extra_disks()
        for d in disks:
            mp = d["mountpoint"]
            aid = f"storage:{mp}"
            props = json.dumps({
                "device": d.get("device", ""),
                "total": d.get("total", 0),
                "used": d.get("used", 0),
                "percent": d.get("percent", 0),
            }, ensure_ascii=False)
            status = "warning" if d.get("percent", 0) > 85 else "ok"
            await _upsert_asset(db, aid, "storage", mp, status, props, now)
            stats["storage"] += 1
    except Exception as e:
        logger.error(f"存储资产发现失败: {e}")

    await db.commit()
    logger.info(f"资产发现完成: {stats}")
    return stats


async def _upsert_asset(db, aid: str, atype: str, name: str, status: str,
                        properties: str, last_seen: str, dependencies: list = None):
    """插入或更新资产（不覆盖手动录入的资产）"""
    existing = await db.execute("SELECT is_manual FROM assets WHERE id = ?", (aid,))
    row = await existing.fetchone()
    deps_json = json.dumps(dependencies, ensure_ascii=False) if dependencies else None

    if row:
        if row[0]:  # is_manual=1, 只更新 last_seen 和 status
            await db.execute(
                "UPDATE assets SET status = ?, last_seen = ? WHERE id = ?",
                (status, last_seen, aid),
            )
        else:
            await db.execute(
                "UPDATE assets SET status = ?, properties = ?, last_seen = ?, dependencies = COALESCE(?, dependencies) WHERE id = ?",
                (status, properties, last_seen, deps_json, aid),
            )
    else:
        await db.execute(
            "INSERT INTO assets (id, type, name, status, properties, dependencies, last_seen) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (aid, atype, name, status, properties, deps_json, last_seen),
        )


async def get_assets(asset_type: str = "") -> list[dict]:
    """获取资产列表"""
    db = await get_db()
    if asset_type:
        cursor = await db.execute(
            "SELECT id, type, name, status, properties, dependencies, is_manual, last_seen "
            "FROM assets WHERE type = ? ORDER BY name", (asset_type,),
        )
    else:
        cursor = await db.execute(
            "SELECT id, type, name, status, properties, dependencies, is_manual, last_seen "
            "FROM assets ORDER BY type, name"
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


async def generate_topology_mermaid() -> str:
    """生成 Mermaid 拓扑图"""
    assets = await get_assets()
    lines = ["graph TD"]

    # 节点定义
    type_icons = {"service": "⚙️", "container": "🐳", "compose": "📦", "port": "🌐", "storage": "💾"}
    status_styles = {"running": "fill:#22c55e,color:#000", "stopped": "fill:#ef4444,color:#fff",
                     "listening": "fill:#38bdf8,color:#000", "ok": "fill:#22c55e,color:#000",
                     "warning": "fill:#fbbf24,color:#000", "unknown": "fill:#94a3b8,color:#000"}

    for a in assets:
        icon = type_icons.get(a["type"], "")
        node_id = a["id"].replace(":", "_").replace("/", "_").replace("-", "_").replace(".", "_")
        label = f"{icon} {a['name']}"
        lines.append(f'    {node_id}["{label}"]')

    # 边（依赖关系）
    for a in assets:
        deps = a.get("dependencies", [])
        if isinstance(deps, list):
            src = a["id"].replace(":", "_").replace("/", "_").replace("-", "_").replace(".", "_")
            for dep_id in deps:
                tgt = dep_id.replace(":", "_").replace("/", "_").replace("-", "_").replace(".", "_")
                lines.append(f"    {tgt} --> {src}")

    # 样式
    for a in assets:
        node_id = a["id"].replace(":", "_").replace("/", "_").replace("-", "_").replace(".", "_")
        style = status_styles.get(a["status"], status_styles["unknown"])
        lines.append(f"    style {node_id} {style}")

    return "\n".join(lines)

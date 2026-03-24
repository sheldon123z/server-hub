"""资产台账 API 路由"""

import json
from fastapi import APIRouter, Request, Depends, HTTPException

from auth.dependencies import require_role
from database import get_db
from modules.assets.services import discover_all, get_assets, generate_topology_mermaid

router = APIRouter(prefix="/api/assets", tags=["资产台账"])


@router.get("/")
async def list_assets(type: str = "", user=Depends(require_role("admin"))):
    """获取资产列表"""
    return await get_assets(type)


@router.post("/discover")
async def trigger_discover(user=Depends(require_role("admin"))):
    """触发资产发现"""
    stats = await discover_all()
    total = sum(stats.values())
    return {"ok": True, "stats": stats, "total": total}


@router.get("/topology")
async def get_topology(user=Depends(require_role("admin"))):
    """获取 Mermaid 拓扑图"""
    mermaid = await generate_topology_mermaid()
    return {"mermaid": mermaid}


@router.get("/summary")
async def get_summary(user=Depends(require_role("admin"))):
    """获取资产统计概览"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT type, COUNT(*), SUM(CASE WHEN status IN ('running','ok','listening') THEN 1 ELSE 0 END) "
        "FROM assets GROUP BY type"
    )
    rows = await cursor.fetchall()
    summary = {}
    for r in rows:
        summary[r[0]] = {"total": r[1], "healthy": r[2]}
    return summary


@router.put("/{asset_id:path}")
async def update_asset(asset_id: str, request: Request, user=Depends(require_role("admin"))):
    """更新资产属性/依赖"""
    db = await get_db()
    existing = await db.execute("SELECT id FROM assets WHERE id = ?", (asset_id,))
    if not await existing.fetchone():
        raise HTTPException(404, "资产不存在")
    body = await request.json()
    sets, vals = [], []
    if "status" in body:
        sets.append("status = ?")
        vals.append(body["status"])
    if "properties" in body:
        sets.append("properties = ?")
        vals.append(json.dumps(body["properties"], ensure_ascii=False) if isinstance(body["properties"], dict) else body["properties"])
    if "dependencies" in body:
        sets.append("dependencies = ?")
        vals.append(json.dumps(body["dependencies"], ensure_ascii=False) if isinstance(body["dependencies"], list) else body["dependencies"])
    if not sets:
        raise HTTPException(400, "没有要更新的字段")
    vals.append(asset_id)
    await db.execute(f"UPDATE assets SET {', '.join(sets)} WHERE id = ?", vals)
    await db.commit()
    return {"ok": True}


@router.post("/manual")
async def add_manual_asset(request: Request, user=Depends(require_role("admin"))):
    """手动添加资产"""
    body = await request.json()
    for field in ("type", "name"):
        if not body.get(field):
            raise HTTPException(400, f"缺少必填字段: {field}")
    db = await get_db()
    aid = body.get("id") or f"{body['type']}:{body['name']}"
    existing = await db.execute("SELECT id FROM assets WHERE id = ?", (aid,))
    if await existing.fetchone():
        raise HTTPException(409, f"资产 ID 已存在: {aid}")
    props = json.dumps(body.get("properties", {}), ensure_ascii=False)
    deps = json.dumps(body.get("dependencies", []), ensure_ascii=False)
    await db.execute(
        "INSERT INTO assets (id, type, name, status, properties, dependencies, is_manual) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        (aid, body["type"], body["name"], body.get("status", "unknown"), props, deps),
    )
    await db.commit()
    return {"ok": True, "id": aid}


@router.delete("/{asset_id:path}")
async def delete_asset(asset_id: str, user=Depends(require_role("admin"))):
    """删除资产（仅手动资产可删除）"""
    db = await get_db()
    cursor = await db.execute("SELECT is_manual FROM assets WHERE id = ?", (asset_id,))
    row = await cursor.fetchone()
    if not row:
        raise HTTPException(404, "资产不存在")
    if not row[0]:
        raise HTTPException(403, "自动发现的资产不能手动删除，下次发现会自动恢复")
    await db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
    await db.commit()
    return {"ok": True}

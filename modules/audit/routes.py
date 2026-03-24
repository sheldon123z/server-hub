"""
审计日志 API 路由
提供分页查询审计日志接口（仅管理员）
"""

from fastapi import APIRouter, Depends, Query

from auth.dependencies import require_role
from database import get_db

router = APIRouter(prefix="/api/audit", tags=["审计日志"])


@router.get("/")
async def list_audit_logs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    username: str | None = Query(default=None),
    action: str | None = Query(default=None),
    user=Depends(require_role("admin")),
):
    """
    分页查询审计日志（仅管理员）

    Args:
        page: 页码，默认 1
        limit: 每页条数，默认 50
        username: 按用户名筛选（可选）
        action: 按操作类型筛选（可选）
    """
    offset = (page - 1) * limit

    # 构建查询条件
    conditions = []
    params = []

    if username:
        conditions.append("username = ?")
        params.append(username)
    if action:
        conditions.append("action = ?")
        params.append(action)

    where_clause = ""
    if conditions:
        where_clause = "WHERE " + " AND ".join(conditions)

    db = await get_db()
    # 查询总数
    count_sql = f"SELECT COUNT(*) FROM audit_log {where_clause}"
    cursor = await db.execute(count_sql, params)
    row = await cursor.fetchone()
    total = row[0] if row else 0

    # 查询分页数据
    data_sql = (
        f"SELECT timestamp, username, action, target, details, ip_address, success "
        f"FROM audit_log {where_clause} "
        f"ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    )
    cursor = await db.execute(data_sql, params + [limit, offset])
    rows = await cursor.fetchall()

    items = [
        {
            "timestamp": row[0],
            "username": row[1],
            "action": row[2],
            "target": row[3],
            "details": row[4],
            "ip": row[5],
            "success": bool(row[6]),
        }
        for row in rows
    ]

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items,
    }


async def _get_audit_logs(page=1, limit=50, username=""):
    """供 main.py 页面路由调用的辅助函数"""
    db = await get_db()
    where_clause = ""
    params = []
    if username:
        where_clause = "WHERE username = ?"
        params = [username]

    offset = (page - 1) * limit
    cursor = await db.execute(f"SELECT COUNT(*) FROM audit_log {where_clause}", params)
    row = await cursor.fetchone()
    total = row[0] if row else 0

    cursor = await db.execute(
        f"SELECT timestamp, username, action, target, details, ip_address, success "
        f"FROM audit_log {where_clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    )
    rows = await cursor.fetchall()
    items = [
        {"timestamp": r[0], "username": r[1], "action": r[2], "target": r[3],
         "details": r[4], "ip_address": r[5], "success": bool(r[6])}
        for r in rows
    ]
    return {"total": total, "items": items}

"""Pipeline 编排模块 — API 路由占位（CRUD + 执行端点在后续 PR 实现）"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/pipelines", tags=["pipelines"])


@router.get("")
@router.get("/")
async def list_pipelines():
    """列表端点占位 — 完整实现在后续 PR"""
    return []

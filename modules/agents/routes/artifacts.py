"""Artifact 文件管理路由 — 查看、下载、列出 Agent 产出的文件制品"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path  # noqa: TC003 — used at runtime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from auth.dependencies import get_current_user
from database import get_db
from modules.agents.sandbox import SANDBOX_DIR

logger = logging.getLogger(__name__)

router = APIRouter()


MAX_TEXT_SIZE = 5 * 1024 * 1024  # 5MB — 文本读取上限


def _validate_sandbox_path(file_path: str) -> Path:
    """校验文件路径在沙箱内，防止目录穿越和符号链接逃逸。"""
    if not file_path:
        raise HTTPException(400, "file_path 不能为空")
    sandbox = SANDBOX_DIR.resolve()
    resolved = (sandbox / file_path.lstrip("/")).resolve()
    # is_relative_to 比 startswith 更安全，避免 /tmp/serverhub-sandbox-evil 绕过
    if not resolved.is_relative_to(sandbox):
        raise HTTPException(403, "路径越权: 只能访问沙箱目录内的文件")
    # 阻止指向沙箱外部的符号链接
    if resolved.is_symlink():
        link_target = resolved.resolve(strict=False)
        if not link_target.is_relative_to(sandbox):
            raise HTTPException(403, "符号链接指向沙箱外部")
    return resolved


@router.get("/artifacts/file")
async def get_artifact_file(
    path: str = Query(..., description="沙箱内的文件路径"),
    _user=Depends(get_current_user),
):
    """读取沙箱文件内容（文本）。"""
    resolved = _validate_sandbox_path(path)
    if not resolved.is_file():
        raise HTTPException(404, f"文件不存在: {path}")
    file_size = resolved.stat().st_size
    if file_size > MAX_TEXT_SIZE:
        raise HTTPException(413, f"文件过大 ({file_size} bytes), 最大支持 {MAX_TEXT_SIZE} bytes")
    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(500, f"读取文件失败: {e}") from e

    ext = resolved.suffix.lstrip(".").lower()
    return {"content": content, "language": ext, "size": file_size}


@router.get("/artifacts/download")
async def download_artifact(
    path: str = Query(..., description="沙箱内的文件路径"),
    _user=Depends(get_current_user),
):
    """下载沙箱文件（二进制）。"""
    resolved = _validate_sandbox_path(path)
    if not resolved.is_file():
        raise HTTPException(404, f"文件不存在: {path}")
    media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    return FileResponse(
        path=str(resolved),
        media_type=media_type,
        filename=resolved.name,
    )


@router.get("/artifacts/list")
async def list_artifacts(
    conversation_id: str = Query(..., description="对话 ID"),
    _user=Depends(get_current_user),
):
    """列出指定对话的所有 artifact（从 agent_run_events 聚合）。"""
    db = await get_db()
    rows = await db.execute_fetchall(
        """
        SELECT json_extract(payload_json, '$.file_path') AS file_path,
               json_extract(payload_json, '$.action')    AS action,
               created_at
        FROM agent_run_events
        WHERE conversation_id = ? AND event_type = 'artifact.update'
        ORDER BY created_at
        """,
        (conversation_id,),
    )
    # 去重: 同路径只保留最新条目
    seen: dict[str, dict] = {}
    for row in rows:
        fp = row[0]
        if fp:
            seen[fp] = {"file_path": fp, "action": row[1], "created_at": row[2]}
    return {"items": list(seen.values())}

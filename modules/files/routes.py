"""
文件管理器 API 路由
提供文件浏览、读写、上传、下载、搜索等接口
"""

import logging
import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from auth.dependencies import require_permission
from modules.audit.middleware import log_audit
from modules.files.security import (
    MAX_UPLOAD_SIZE,
    check_file_size_for_download,
    validate_path,
    validate_write_path,
)
from modules.files.services import (
    file_action,
    get_file_stat,
    grep_content,
    list_directory,
    read_file_content,
    search_files,
    upload_write_file,
    write_file_content,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["文件管理"])


# ─── 请求体模型 ───


class WriteFileRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)
    content: str = Field(default="")


class FileActionRequest(BaseModel):
    action: str = Field(..., description="mkdir|rename|copy|move|delete")
    source: str = Field(..., min_length=1, max_length=4096)
    target: str | None = Field(default=None, max_length=4096)


# ─── 只读端点 ───


@router.get("/list")
async def api_list_directory(
    path: str = Query(..., description="目录路径"),
    sort: str = Query(default="name", description="排序字段: name|size|mtime"),
    user=Depends(require_permission("files", "read")),
):
    """列出目录内容"""
    validated = validate_path(path)
    items = await list_directory(validated, sort=sort)
    return {
        "path": str(validated),
        "items": items,
        "total": len(items),
    }


@router.get("/read")
async def api_read_file(
    path: str = Query(..., description="文件路径"),
    user=Depends(require_permission("files", "read")),
):
    """读取文件内容（≤5MB）"""
    validated = validate_path(path)
    content = await read_file_content(validated)

    # 猜测 MIME 类型
    mime_type, _ = mimetypes.guess_type(str(validated))
    return {
        "path": str(validated),
        "content": content,
        "size": len(content.encode("utf-8")),
        "mime_type": mime_type or "text/plain",
    }


@router.get("/stat")
async def api_file_stat(
    path: str = Query(..., description="文件或目录路径"),
    user=Depends(require_permission("files", "read")),
):
    """获取文件/目录元信息"""
    validated = validate_path(path)
    return await get_file_stat(validated)


@router.get("/search")
async def api_search_files(
    path: str = Query(..., description="搜索起始目录"),
    query: str = Query(..., min_length=1, max_length=200, description="搜索关键字或 glob 模式"),
    user=Depends(require_permission("files", "read")),
):
    """按文件名搜索（支持 glob 通配符）"""
    validated = validate_path(path)
    results = await search_files(validated, query)
    return {
        "path": str(validated),
        "query": query,
        "results": results,
        "total": len(results),
    }


@router.get("/grep")
async def api_grep_content(
    path: str = Query(..., description="搜索起始路径（目录或文件）"),
    pattern: str = Query(..., min_length=1, max_length=200, description="正则表达式模式"),
    user=Depends(require_permission("files", "read")),
):
    """在文件内容中搜索（正则 grep）"""
    validated = validate_path(path)
    results = await grep_content(validated, pattern)
    return {
        "path": str(validated),
        "pattern": pattern,
        "results": results,
        "total": len(results),
    }


@router.get("/download")
async def api_download_file(
    path: str = Query(..., description="文件路径"),
    user=Depends(require_permission("files", "read")),
):
    """下载文件（≤500MB）"""
    validated = validate_path(path)

    if not validated.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    if validated.is_dir():
        raise HTTPException(status_code=400, detail="不支持直接下载目录，请先打包")

    check_file_size_for_download(validated)

    mime_type, _ = mimetypes.guess_type(str(validated))
    return FileResponse(
        path=str(validated),
        filename=validated.name,
        media_type=mime_type or "application/octet-stream",
    )


# ─── 写操作端点 ───


@router.put("/write")
async def api_write_file(
    body: WriteFileRequest,
    request: Request,
    user=Depends(require_permission("files", "write")),
):
    """写入/保存文件内容"""
    validated = validate_write_path(body.path)
    await write_file_content(validated, body.content)

    await log_audit(
        username=user["username"],
        action="files.write",
        target=str(validated),
        ip=request.client.host if request.client else "unknown",
        detail=f"size={len(body.content.encode())}B",
    )
    return {"ok": True, "path": str(validated), "size": len(body.content.encode("utf-8"))}


@router.post("/upload")
async def api_upload_file(
    request: Request,
    path: str = Query(..., description="上传目标目录"),
    file: UploadFile = File(...),
    user=Depends(require_permission("files", "write")),
):
    """上传文件到指定目录（≤100MB）"""
    validated_dir = validate_write_path(path)

    stat = await get_file_stat(validated_dir)
    if not stat["is_dir"]:
        raise HTTPException(status_code=400, detail="目标路径不是目录")

    # 安全文件名：仅保留基础名称，剔除路径成分
    safe_name = Path(file.filename or "upload").name
    if not safe_name or safe_name in (".", ".."):
        raise HTTPException(status_code=400, detail="文件名无效")

    dest = validated_dir / safe_name

    # 先读取所有 chunks 并检查总大小（避免在 async 函数中调用阻塞 open）
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(1024 * 1024):  # 1MB chunks
        total += len(chunk)
        if total > MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=413, detail="文件超过上传限制 100MB")
        chunks.append(chunk)

    try:
        written = await upload_write_file(dest, chunks)
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    await log_audit(
        username=user["username"],
        action="files.upload",
        target=str(dest),
        ip=request.client.host if request.client else "unknown",
        detail=f"size={written}B",
    )
    return {"ok": True, "path": str(dest), "size": written, "filename": safe_name}


@router.post("/action")
async def api_file_action(
    body: FileActionRequest,
    request: Request,
    user=Depends(require_permission("files", "write")),
):
    """执行文件操作: mkdir / rename / copy / move / delete"""
    # 删除/创建目录时 source 可能不存在（mkdir 场景）
    if body.action == "mkdir":
        source = validate_write_path(body.source)
        target = None
    else:
        source = validate_path(body.source)
        target: Path | None = None
        if body.target:
            target = validate_write_path(body.target)

    result = await file_action(body.action, source, target)

    await log_audit(
        username=user["username"],
        action=f"files.{body.action}",
        target=str(source),
        ip=request.client.host if request.client else "unknown",
        detail=f"target={body.target}" if body.target else "",
    )
    return result

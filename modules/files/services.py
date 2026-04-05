"""
文件管理器核心服务层
提供目录列表、文件读写、搜索、grep 和文件操作功能
"""

import asyncio
import fnmatch
import grp
import logging
import os
import pwd
import re
import shutil
import stat
from pathlib import Path

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# ─── 工具函数 ───


def _permissions_str(st: os.stat_result) -> str:
    """将 stat 模式转换为 rwxrwxrwx 字符串。"""
    mode = st.st_mode
    parts = []
    for who in ("USR", "GRP", "OTH"):
        r = "r" if mode & getattr(stat, f"S_IR{who}") else "-"
        w = "w" if mode & getattr(stat, f"S_IW{who}") else "-"
        x = "x" if mode & getattr(stat, f"S_IX{who}") else "-"
        parts.append(r + w + x)
    return "".join(parts)


def _owner_name(st: os.stat_result) -> str:
    """获取文件所有者用户名。"""
    try:
        return pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        return str(st.st_uid)


def _group_name(st: os.stat_result) -> str:
    """获取文件所有组名。"""
    try:
        return grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        return str(st.st_gid)


def _entry_info(entry: os.DirEntry) -> dict:
    """将 DirEntry 转换为前端所需的字典格式。"""
    try:
        st = entry.stat(follow_symlinks=False)
        is_link = entry.is_symlink()
        is_dir = entry.is_dir(follow_symlinks=True)
        size = st.st_size if not is_dir else 0
        return {
            "name": entry.name,
            "type": "symlink" if is_link else ("dir" if is_dir else "file"),
            "size": size,
            "mtime": st.st_mtime,
            "permissions": _permissions_str(st),
            "owner": _owner_name(st),
            "is_dir": is_dir,
        }
    except OSError:
        return {
            "name": entry.name,
            "type": "unknown",
            "size": 0,
            "mtime": 0.0,
            "permissions": "---------",
            "owner": "?",
            "is_dir": False,
        }


# ─── 同步工作函数（在 asyncio.to_thread 中调用）───


def _sync_list_directory(path: Path, sort: str) -> list[dict]:
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="路径不存在")
    if not path.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径不是目录")
    try:
        entries = list(os.scandir(path))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"权限不足: {e}") from e
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e

    items = [_entry_info(e) for e in entries]
    sort_key = sort if sort in ("name", "size", "mtime") else "name"

    def sort_fn(item: dict):
        primary = 0 if item["is_dir"] else 1
        secondary = item.get(sort_key, item["name"])
        if isinstance(secondary, str):
            secondary = secondary.lower()
        return (primary, secondary)

    items.sort(key=sort_fn)
    return items


def _sync_read_file(path: Path) -> str:
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    if path.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径是目录，无法读取内容")
    size = path.stat().st_size
    if size > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件超过预览/编辑限制 5MB（当前 {size // 1024 // 1024}MB）",
        )
    try:
        return path.read_text(errors="replace")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"权限不足: {e}") from e
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


def _sync_write_file(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"权限不足: {e}") from e
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


def _sync_file_stat(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="路径不存在")
    try:
        st = path.stat()
        lst = path.lstat()
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e
    return {
        "path": str(path),
        "name": path.name,
        "size": st.st_size,
        "permissions": _permissions_str(lst),
        "octal_permissions": oct(lst.st_mode & 0o777),
        "owner": _owner_name(lst),
        "group": _group_name(lst),
        "mtime": st.st_mtime,
        "ctime": st.st_ctime,
        "is_dir": path.is_dir(),
        "is_symlink": path.is_symlink(),
        "symlink_target": str(os.readlink(path)) if path.is_symlink() else None,
    }


def _sync_search_files(path: Path, query: str, max_results: int) -> list[dict]:
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="起始路径不是有效目录")
    pattern = query if ("*" in query or "?" in query) else f"*{query}*"
    results: list[dict] = []
    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith(".") or d == "."]
        for name in files:
            if fnmatch.fnmatch(name, pattern):
                full = Path(root) / name
                try:
                    st = full.stat()
                    results.append(
                        {
                            "path": str(full),
                            "name": name,
                            "size": st.st_size,
                            "mtime": st.st_mtime,
                            "type": "file",
                        }
                    )
                except OSError:
                    pass
            if len(results) >= max_results:
                return results
        for name in dirs:
            if fnmatch.fnmatch(name, pattern):
                full = Path(root) / name
                try:
                    st = full.stat()
                    results.append(
                        {
                            "path": str(full),
                            "name": name,
                            "size": 0,
                            "mtime": st.st_mtime,
                            "type": "dir",
                        }
                    )
                except OSError:
                    pass
            if len(results) >= max_results:
                return results
    return results


def _grep_file(file_path: Path, compiled: re.Pattern, results: list[dict], max_results: int) -> bool:
    """grep 单个文件，返回是否已达上限。"""
    try:
        size = file_path.stat().st_size
        if size > 10 * 1024 * 1024:
            return False
        with open(file_path, encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                if compiled.search(line):
                    results.append(
                        {
                            "file": str(file_path),
                            "line_no": line_no,
                            "content": line.rstrip("\n")[:300],
                        }
                    )
                    if len(results) >= max_results:
                        return True
    except (OSError, PermissionError):
        pass
    return False


def _sync_grep_content(path: Path, pattern: str, max_results: int) -> list[dict]:
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"正则表达式无效: {e}") from e

    results: list[dict] = []
    if path.is_file():
        _grep_file(path, compiled, results, max_results)
        return results

    for root, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if _grep_file(Path(root) / name, compiled, results, max_results):
                return results
    return results


def _sync_file_action(action: str, source: Path, target: Path | None) -> str:
    if action == "mkdir":
        source.mkdir(parents=True, exist_ok=True)
        return str(source)
    if action == "delete":
        if not source.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源路径不存在")
        if source.is_dir():
            shutil.rmtree(source)
        else:
            source.unlink()
        return str(source)
    if not source.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源路径不存在")
    if action == "rename":
        source.rename(target)
        return str(target)
    if action == "copy":
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)
        return str(target)
    if action == "move":
        shutil.move(str(source), str(target))
        return str(target)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"不支持的操作: {action}")


def _sync_upload_write(dest: Path, chunks: list[bytes]) -> int:
    written = 0
    with open(dest, "wb") as f:
        for chunk in chunks:
            f.write(chunk)
            written += len(chunk)
    return written


# ─── 公开异步服务函数 ───


async def list_directory(path: Path, sort: str = "name") -> list[dict]:
    """列出目录内容，目录优先，按指定字段排序。"""
    return await asyncio.to_thread(_sync_list_directory, path, sort)


async def read_file_content(path: Path) -> str:
    """读取文件文本内容（≤5MB）。"""
    return await asyncio.to_thread(_sync_read_file, path)


async def write_file_content(path: Path, content: str) -> bool:
    """写入文件内容，父目录不存在时自动创建。"""
    await asyncio.to_thread(_sync_write_file, path, content)
    return True


async def get_file_stat(path: Path) -> dict:
    """获取文件/目录元信息。"""
    return await asyncio.to_thread(_sync_file_stat, path)


async def search_files(path: Path, query: str, max_results: int = 200) -> list[dict]:
    """在指定目录下递归搜索文件名（glob 模式或关键字）。"""
    return await asyncio.to_thread(_sync_search_files, path, query, max_results)


async def grep_content(path: Path, pattern: str, max_results: int = 500) -> list[dict]:
    """在目录下递归 grep 文件内容（正则模式）。"""
    return await asyncio.to_thread(_sync_grep_content, path, pattern, max_results)


async def file_action(action: str, source: Path, target: Path | None = None) -> dict:
    """执行文件系统操作: mkdir / rename / copy / move / delete。"""
    valid_actions = {"mkdir", "rename", "copy", "move", "delete"}
    if action not in valid_actions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的操作: {action}，有效值: {', '.join(valid_actions)}",
        )
    if action in ("rename", "copy", "move") and target is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"操作 {action} 需要提供目标路径")
    try:
        result_path = await asyncio.to_thread(_sync_file_action, action, source, target)
        return {"ok": True, "action": action, "path": result_path}
    except HTTPException:
        raise
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"权限不足: {e}") from e
    except FileExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"目标路径已存在: {e}") from e
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)) from e


async def upload_write_file(dest: Path, chunks: list[bytes]) -> int:
    """将已收集的数据块写入目标文件，返回写入字节数。"""
    return await asyncio.to_thread(_sync_upload_write, dest, chunks)

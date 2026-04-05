"""
文件管理器安全层
提供路径遍历防护、敏感文件保护和访问控制
"""

import fnmatch
import logging
import os
from pathlib import Path

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

# 允许访问的根目录列表（用户可在这些路径下浏览）
ALLOWED_ROOTS = [
    Path("/home"),
    Path("/var/log"),
    Path("/etc"),
    Path("/tmp"),
    Path("/opt"),
    Path("/mnt"),
]

# 绝对禁止访问的敏感文件 glob 模式
PROTECTED_PATTERNS = [
    "**/.env",
    "**/.api_keys",
    "**/.telegram_config",
    "**/config.yaml",
    "**/*.key",
    "**/*.pem",
    "**/id_rsa",
    "**/id_rsa.pub",
    "**/id_ed25519",
    "**/id_ed25519.pub",
    "**/.ssh/authorized_keys",
    "**/.ssh/known_hosts",
    "**/secrets.yaml",
    "**/secrets.json",
    "**/.pgpass",
    "**/*.p12",
    "**/*.pfx",
    "**/*.jks",
]

# 最大文件大小限制
MAX_READ_SIZE = 5 * 1024 * 1024  # 5MB 预览/编辑
MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB 上传
MAX_DOWNLOAD_SIZE = 500 * 1024 * 1024  # 500MB 下载


def is_protected(path: Path) -> bool:
    """检查路径是否匹配敏感文件模式。"""
    path_str = str(path)
    path_name = path.name
    for pattern in PROTECTED_PATTERNS:
        # 用 fnmatch 匹配文件名部分
        if fnmatch.fnmatch(path_name, pattern.lstrip("*/")):
            return True
        # 用完整路径匹配
        if fnmatch.fnmatch(path_str, pattern):
            return True
    return False


def _resolve_safe(raw_path: str) -> Path:
    """解析并返回 resolved Path，不跟随符号链接到允许根目录之外。"""
    try:
        p = Path(raw_path)
        # 先做逻辑解析（不要求文件存在）
        resolved = p.resolve()
    except (ValueError, OSError) as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"路径无效: {e}") from e

    # 检查是否在允许的根目录下
    in_allowed = any(_is_relative_to(resolved, root) for root in ALLOWED_ROOTS)
    if not in_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="路径超出允许范围",
        )

    # 符号链接检测：如果路径存在且是符号链接，检查链接目标也在允许范围内
    if resolved.exists() and resolved.is_symlink():
        link_target = Path(os.readlink(resolved)).resolve()
        target_allowed = any(_is_relative_to(link_target, root) for root in ALLOWED_ROOTS)
        if not target_allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="符号链接目标超出允许范围",
            )

    return resolved


def _is_relative_to(path: Path, parent: Path) -> bool:
    """兼容 Python 3.9+ 的 is_relative_to。"""
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_path(raw_path: str | None) -> Path:
    """
    验证并返回安全的 Path 对象。

    检查顺序:
    1. 路径不能为空
    2. 解析绝对路径（防穿越）
    3. 必须在 ALLOWED_ROOTS 范围内
    4. 不能是受保护文件
    5. 符号链接目标检查
    """
    if not raw_path or not raw_path.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="路径不能为空")

    resolved = _resolve_safe(raw_path.strip())

    if is_protected(resolved):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="该文件受保护，禁止访问",
        )

    return resolved


def validate_write_path(raw_path: str | None) -> Path:
    """验证写操作路径（包含父目录检查）。"""
    resolved = validate_path(raw_path)

    # 父目录也需要在允许范围内
    parent = resolved.parent
    parent_allowed = any(_is_relative_to(parent, root) for root in ALLOWED_ROOTS)
    if not parent_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="目标父目录超出允许范围",
        )

    return resolved


def check_file_size_for_read(path: Path) -> None:
    """检查文件大小是否超过预览/编辑限制。"""
    try:
        size = path.stat().st_size
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文件不存在: {e}") from e

    if size > MAX_READ_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件超过预览限制 (5MB)，当前大小: {size // 1024 // 1024}MB",
        )


def check_file_size_for_download(path: Path) -> None:
    """检查文件大小是否超过下载限制。"""
    try:
        size = path.stat().st_size
    except OSError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"文件不存在: {e}") from e

    if size > MAX_DOWNLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件超过下载限制 (500MB)，当前大小: {size // 1024 // 1024}MB",
        )

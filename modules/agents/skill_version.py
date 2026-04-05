"""技能版本管理：快照保存、回滚、版本列表、旧版清理。"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from config import BASE_DIR
from database import get_db
from modules.agents.run_service import now_iso
from modules.agents.skill_service import (
    INSTALLED_SKILLS_ROOT,
    _copy_skill_tree,
    get_skill,
)

logger = logging.getLogger(__name__)

SKILL_VERSIONS_ROOT = BASE_DIR / "data" / "skill-versions"


async def snapshot_version(skill_id: str, version: str, source_path: Path) -> Path:
    """保存版本快照到 data/skill-versions/{skill_id}/{version}/。

    如果同一 skill_id + version 的快照已存在，则跳过。
    返回快照目录路径。
    """
    snapshot_dir = SKILL_VERSIONS_ROOT / skill_id / version
    if snapshot_dir.exists():
        logger.debug("版本快照已存在，跳过: %s/%s", skill_id, version)
        return snapshot_dir

    snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
    _copy_skill_tree(source_path, snapshot_dir)

    # 记录到数据库（如果 agent_skill_versions 表中无对应记录则插入）
    db = await get_db()
    cursor = await db.execute(
        "SELECT id FROM agent_skill_versions WHERE skill_id = ? AND version = ?",
        (skill_id, version),
    )
    existing = await cursor.fetchone()
    if not existing:
        await db.execute(
            """
            INSERT INTO agent_skill_versions (skill_id, version, manifest_json, source_type, source_ref)
            VALUES (?, ?, '{}', 'snapshot', ?)
            """,
            (skill_id, version, str(snapshot_dir)),
        )
        await db.commit()

    logger.info("已保存版本快照: %s v%s -> %s", skill_id, version, snapshot_dir)
    return snapshot_dir


async def rollback_skill(skill_id: str, target_version: str) -> dict[str, Any]:
    """回滚到指定版本。

    1. 从快照目录复制到 installed/
    2. 更新数据库
    3. 调用 reset_agent_cache()

    返回更新后的技能信息。
    """
    snapshot_dir = SKILL_VERSIONS_ROOT / skill_id / target_version
    if not snapshot_dir.is_dir():
        raise ValueError(f"版本快照不存在: {skill_id} v{target_version}")

    # 确认技能存在于数据库
    skill = await get_skill(skill_id)
    if not skill:
        raise ValueError(f"技能未注册: {skill_id}")

    # 先快照当前版本（如果不同于目标版本）
    current_path = Path(skill["install_path"])
    if skill["version"] != target_version and current_path.is_dir():  # noqa: ASYNC240 — 管理员操作，非热路径
        await snapshot_version(skill_id, skill["version"], current_path)

    # 复制快照到 installed 目录
    target_path = INSTALLED_SKILLS_ROOT / skill_id
    _copy_skill_tree(snapshot_dir, target_path)

    # 更新数据库版本
    db = await get_db()
    await db.execute(
        """
        UPDATE agent_skills
        SET version = ?, install_path = ?, updated_at = ?
        WHERE id = ?
        """,
        (target_version, str(target_path), now_iso(), skill_id),
    )
    await db.commit()

    # 记录安装日志
    await db.execute(
        """
        INSERT INTO agent_skill_installs (skill_id, action, status, details_json, created_by)
        VALUES (?, 'rollback', 'success', ?, 'system')
        """,
        (skill_id, json.dumps({"target_version": target_version}, ensure_ascii=False)),
    )
    await db.commit()

    # 刷新 agent 缓存
    from modules.agents.deep_agent import reset_agent_cache

    reset_agent_cache()

    logger.info("技能已回滚: %s → v%s", skill_id, target_version)
    return await get_skill(skill_id, include_content=True)  # type: ignore[return-value]


async def list_versions(skill_id: str) -> list[dict[str, Any]]:
    """列出所有版本快照。

    优先从文件系统 + 数据库联合获取，返回按版本排序的列表。
    """
    versions: dict[str, dict[str, Any]] = {}

    # 从文件系统扫描
    skill_versions_dir = SKILL_VERSIONS_ROOT / skill_id
    if skill_versions_dir.is_dir():
        for ver_dir in sorted(skill_versions_dir.iterdir()):
            if ver_dir.is_dir():
                versions[ver_dir.name] = {
                    "skill_id": skill_id,
                    "version": ver_dir.name,
                    "snapshot_path": str(ver_dir),
                    "has_snapshot": True,
                    "created_at": None,
                }

    # 从数据库补充元数据
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT version, source_type, source_ref, created_at
        FROM agent_skill_versions
        WHERE skill_id = ?
        ORDER BY created_at ASC
        """,
        (skill_id,),
    )
    rows = await cursor.fetchall()
    for row in rows:
        ver = row[0]
        if ver in versions:
            versions[ver]["source_type"] = row[1]
            versions[ver]["source_ref"] = row[2]
            versions[ver]["created_at"] = row[3]
        else:
            versions[ver] = {
                "skill_id": skill_id,
                "version": ver,
                "snapshot_path": None,
                "has_snapshot": False,
                "source_type": row[1],
                "source_ref": row[2],
                "created_at": row[3],
            }

    return sorted(versions.values(), key=lambda v: v.get("created_at") or "")


async def cleanup_old_versions(skill_id: str, keep: int = 10) -> int:
    """清理旧版本快照，保留最近 N 个。

    返回删除的版本数量。
    """
    skill_versions_dir = SKILL_VERSIONS_ROOT / skill_id
    if not skill_versions_dir.is_dir():
        return 0

    # 获取所有版本目录，按修改时间排序（最新在后）
    ver_dirs = sorted(
        [d for d in skill_versions_dir.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
    )

    if len(ver_dirs) <= keep:
        return 0

    to_remove = ver_dirs[: len(ver_dirs) - keep]
    removed = 0
    for ver_dir in to_remove:
        try:
            shutil.rmtree(ver_dir)
            removed += 1
            logger.info("已清理旧版本快照: %s/%s", skill_id, ver_dir.name)
        except Exception as exc:
            logger.warning("清理版本快照失败 (%s/%s): %s", skill_id, ver_dir.name, exc)

    # 清理空目录
    if skill_versions_dir.exists() and not any(skill_versions_dir.iterdir()):
        skill_versions_dir.rmdir()

    return removed

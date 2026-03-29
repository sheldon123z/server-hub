"""Skill 生命周期与推荐服务。"""

from __future__ import annotations

import io
import json
import logging
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from config import BASE_DIR, settings
from database import get_db
from modules.agents.run_service import now_iso

logger = logging.getLogger(__name__)

SKILLS_ROOT = BASE_DIR / "skills"
INSTALLED_SKILLS_ROOT = BASE_DIR / "data" / "skills" / "installed"
SKILL_SOURCE_FILE = Path(settings.db_path).parent / "skill-source-roots.json"
ALLOWED_UPLOAD_SUFFIXES = {".zip", ".tar", ".gz", ".tgz"}


def _safe_read_manifest(path: Path) -> dict[str, Any]:
    manifest_path = path / "skill.yaml"
    if not manifest_path.exists():
        raise ValueError(f"{path} 缺少 skill.yaml")
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    required = ["id", "name", "version", "summary"]
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError(f"manifest 缺少字段: {', '.join(missing)}")
    if not (path / "SKILL.md").exists():
        raise ValueError(f"{path} 缺少 SKILL.md")
    data.setdefault("triggers", {})
    data.setdefault("capabilities", [])
    data.setdefault("required_tools", [])
    data.setdefault("allowed_roles", ["admin", "user"])
    data.setdefault("entrypoints", {"type": "prompt"})
    return data


def _default_skill_sources() -> list[str]:
    return [str(SKILLS_ROOT)]


def get_skill_sources() -> list[str]:
    roots = _default_skill_sources()
    if SKILL_SOURCE_FILE.exists():
        try:
            payload = json.loads(SKILL_SOURCE_FILE.read_text(encoding="utf-8"))
            for item in payload.get("roots", []):
                if item not in roots:
                    roots.append(item)
        except Exception as exc:
            logger.warning("技能源读取失败: %s", exc)
    return roots


def save_skill_sources(roots: list[str]) -> list[str]:
    cleaned: list[str] = []
    for root in roots:
        value = str(Path(root).expanduser())
        if value not in cleaned:
            cleaned.append(value)
    SKILL_SOURCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SKILL_SOURCE_FILE.write_text(json.dumps({"roots": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8")
    return get_skill_sources()


def _scan_root(root: Path) -> list[dict[str, Any]]:
    if not root.exists() or not root.is_dir():
        return []
    candidates: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        try:
            manifest = _safe_read_manifest(child)
            candidates.append(
                {
                    "path": str(child),
                    "manifest": manifest,
                    "source_type": "repo",
                    "source_ref": str(root),
                }
            )
        except Exception as e:
            logger.debug("跳过无效 skill 目录 %s: %s", child, e)
            continue
    return candidates


async def discover_skills(*, roots: list[str] | None = None) -> list[dict[str, Any]]:
    search_roots = roots or get_skill_sources()
    installed = {item["id"] for item in await list_skills()}
    discovered: list[dict[str, Any]] = []
    for root_str in search_roots:
        root = Path(root_str).expanduser()  # noqa: ASYNC240 — 启动时扫描，非热路径
        for item in _scan_root(root):
            item["installed"] = item["manifest"]["id"] in installed
            discovered.append(item)
    return discovered


async def list_skills() -> list[dict[str, Any]]:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, version, name, summary, enabled, source_type, source_ref, install_path, manifest_json,
               created_at, updated_at
        FROM agent_skills
        ORDER BY name ASC
        """
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "version": row[1],
            "name": row[2],
            "summary": row[3],
            "enabled": bool(row[4]),
            "source_type": row[5],
            "source_ref": row[6],
            "install_path": row[7],
            "manifest": json.loads(row[8]),
            "created_at": row[9],
            "updated_at": row[10],
        }
        for row in rows
    ]


async def get_skill(skill_id: str, *, include_content: bool = False) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, version, name, summary, enabled, source_type, source_ref, install_path, manifest_json,
               created_at, updated_at
        FROM agent_skills WHERE id = ?
        """,
        (skill_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    install_path = Path(row[7])
    result = {
        "id": row[0],
        "version": row[1],
        "name": row[2],
        "summary": row[3],
        "enabled": bool(row[4]),
        "source_type": row[5],
        "source_ref": row[6],
        "install_path": row[7],
        "manifest": json.loads(row[8]),
        "created_at": row[9],
        "updated_at": row[10],
    }
    if include_content:
        result["skill_markdown"] = (install_path / "SKILL.md").read_text(encoding="utf-8")
    return result


async def _log_install(skill_id: str, action: str, status: str, details: dict[str, Any], created_by: str) -> None:
    db = await get_db()
    await db.execute(
        """
        INSERT INTO agent_skill_installs (skill_id, action, status, details_json, created_by)
        VALUES (?, ?, ?, ?, ?)
        """,
        (skill_id, action, status, json.dumps(details, ensure_ascii=False), created_by),
    )
    await db.commit()


async def _upsert_skill(
    manifest: dict[str, Any],
    *,
    install_path: Path,
    source_type: str,
    source_ref: str,
    created_by: str,
) -> dict[str, Any]:
    db = await get_db()
    payload = json.dumps(manifest, ensure_ascii=False)
    await db.execute(
        """
        INSERT INTO agent_skills (
            id, version, name, summary, enabled, source_type, source_ref, install_path,
            manifest_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            version = excluded.version,
            name = excluded.name,
            summary = excluded.summary,
            source_type = excluded.source_type,
            source_ref = excluded.source_ref,
            install_path = excluded.install_path,
            manifest_json = excluded.manifest_json,
            updated_at = excluded.updated_at
        """,
        (
            manifest["id"],
            manifest["version"],
            manifest["name"],
            manifest["summary"],
            source_type,
            source_ref,
            str(install_path),
            payload,
            now_iso(),
            now_iso(),
        ),
    )
    await db.execute(
        """
        INSERT INTO agent_skill_versions (skill_id, version, manifest_json, source_type, source_ref)
        VALUES (?, ?, ?, ?, ?)
        """,
        (manifest["id"], manifest["version"], payload, source_type, source_ref),
    )
    await db.commit()
    await _log_install(manifest["id"], "install", "success", {"install_path": str(install_path)}, created_by)
    return await get_skill(manifest["id"], include_content=True)  # type: ignore[return-value]


def _copy_skill_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


async def install_skill_from_repo(repo_path: str, *, created_by: str) -> dict[str, Any]:
    source = Path(repo_path).expanduser().resolve()  # noqa: ASYNC240 — 管理员操作，非热路径
    manifest = _safe_read_manifest(source)
    target = INSTALLED_SKILLS_ROOT / manifest["id"]
    target.parent.mkdir(parents=True, exist_ok=True)
    _copy_skill_tree(source, target)
    return await _upsert_skill(
        manifest,
        install_path=target,
        source_type="repo",
        source_ref=str(source),
        created_by=created_by,
    )


def _safe_extract_archive(source_name: str, content: bytes, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if source_name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            for member in archive.namelist():
                member_path = Path(member)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError("上传压缩包包含非法路径")
            archive.extractall(destination)  # noqa: S202 — 已逐项校验路径安全
    elif any(source_name.endswith(suffix) for suffix in (".tar", ".tar.gz", ".tgz", ".gz")):
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
            for member in archive.getmembers():
                member_path = Path(member.name)
                if member_path.is_absolute() or ".." in member_path.parts:
                    raise ValueError("上传压缩包包含非法路径")
            archive.extractall(destination, filter="data")  # noqa: S202
    else:
        raise ValueError("仅支持 zip/tar.gz/tgz 上传")

    children = [child for child in destination.iterdir() if child.is_dir()]
    if len(children) == 1 and not (destination / "skill.yaml").exists():
        return children[0]
    return destination


async def install_skill_from_upload(filename: str, content: bytes, *, created_by: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES and not filename.endswith((".tar.gz", ".tgz")):
        raise ValueError("仅支持 zip/tar.gz/tgz 技能包")
    with tempfile.TemporaryDirectory(prefix="serverhub-skill-") as tmpdir:
        unpack_root = Path(tmpdir) / "upload"
        skill_root = _safe_extract_archive(filename, content, unpack_root)
        manifest = _safe_read_manifest(skill_root)
        target = INSTALLED_SKILLS_ROOT / manifest["id"]
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_skill_tree(skill_root, target)
        return await _upsert_skill(
            manifest,
            install_path=target,
            source_type="upload",
            source_ref=filename,
            created_by=created_by,
        )


async def set_skill_enabled(skill_id: str, enabled: bool, *, created_by: str) -> bool:
    db = await get_db()
    await db.execute(
        "UPDATE agent_skills SET enabled = ?, updated_at = ? WHERE id = ?",
        (1 if enabled else 0, now_iso(), skill_id),
    )
    await db.commit()
    await _log_install(skill_id, "enable" if enabled else "disable", "success", {}, created_by)
    return True


async def remove_skill(skill_id: str, *, created_by: str) -> bool:
    current = await get_skill(skill_id)
    if not current:
        return False
    install_path = Path(current["install_path"])
    if install_path.exists():  # noqa: ASYNC240 — 管理员操作，非热路径
        shutil.rmtree(install_path)
    db = await get_db()
    await db.execute("DELETE FROM agent_skills WHERE id = ?", (skill_id,))
    await db.commit()
    await _log_install(skill_id, "uninstall", "success", {}, created_by)
    return True


async def recommend_skills(
    *,
    message: str,
    page_context: str | None = None,
    user_role: str = "admin",
    limit: int = 4,
) -> list[dict[str, Any]]:
    candidates = []
    message_lower = message.lower()
    for skill in await list_skills():
        if not skill["enabled"]:
            continue
        manifest = skill["manifest"]
        if user_role not in manifest.get("allowed_roles", ["admin", "user"]):
            continue
        triggers = manifest.get("triggers", {})
        score = 0
        reasons: list[str] = []
        for keyword in triggers.get("keywords", []):
            if keyword.lower() in message_lower:
                score += 2
                reasons.append(f"命中关键词 {keyword}")
        for ctx in triggers.get("page_contexts", []):
            if page_context and ctx == page_context:
                score += 3
                reasons.append(f"适配页面 {ctx}")
        if score > 0:
            candidates.append(
                {
                    "id": skill["id"],
                    "name": skill["name"],
                    "summary": skill["summary"],
                    "score": score,
                    "reasons": reasons,
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["name"]))
    return candidates[:limit]


async def load_skill_context(skill_id: str) -> str:
    skill = await get_skill(skill_id, include_content=True)
    if not skill or not skill["enabled"]:
        return ""
    return f"[已启用技能: {skill['name']}]\n摘要: {skill['summary']}\n\n{skill['skill_markdown']}\n"

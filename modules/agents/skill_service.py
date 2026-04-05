"""Skill 生命周期与推荐服务。

统一使用 SKILL.md YAML frontmatter 作为技能入口格式，
废弃 skill.yaml。支持三级隔离（system/shared/private）和
description 全文搜索推荐。
"""

from __future__ import annotations

import io
import json
import logging
import re
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

SKILLS_ROOT = BASE_DIR / "data" / "skills"
INSTALLED_SKILLS_ROOT = SKILLS_ROOT / "installed"
SYSTEM_SKILLS_ROOT = SKILLS_ROOT / "system"
USER_SKILLS_ROOT = SKILLS_ROOT / "users"
SKILL_VERSIONS_ROOT = SKILLS_ROOT / "skill-versions"
SKILL_SOURCE_FILE = Path(settings.db_path).parent / "skill-source-roots.json"
ALLOWED_UPLOAD_SUFFIXES = {".zip", ".tar", ".gz", ".tgz"}

# frontmatter 分隔符
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# 附属文件子目录白名单
_ASSET_DIRS = ("references", "scripts", "assets", "evals")


# ---------------------------------------------------------------------------
# SKILL.md 解析
# ---------------------------------------------------------------------------


def parse_skill_md(path: Path) -> dict[str, Any]:
    """解析 SKILL.md 的 YAML frontmatter，返回标准化 manifest 字典。

    标准字段（Agent Skills Spec）：name, description, allowed-tools, license, compatibility, metadata
    ServerHub 扩展字段从 metadata 中提取：version, allowed-roles, page-contexts, capabilities, compose, owner
    """
    skill_md = path / "SKILL.md"
    if not skill_md.exists():
        raise ValueError(f"{path} 缺少 SKILL.md")

    content = skill_md.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(content)
    if not match:
        raise ValueError(f"{skill_md} 缺少 YAML frontmatter (--- ... ---)")

    raw = yaml.safe_load(match.group(1)) or {}

    # 标准字段
    name = raw.get("name", "")
    if not name:
        raise ValueError(f"{skill_md} frontmatter 缺少 name 字段")
    description = raw.get("description", "")
    if not description:
        raise ValueError(f"{skill_md} frontmatter 缺少 description 字段")

    allowed_tools_raw = raw.get("allowed-tools", "")
    if isinstance(allowed_tools_raw, str):
        allowed_tools = allowed_tools_raw.split() if allowed_tools_raw.strip() else []
    else:
        allowed_tools = list(allowed_tools_raw or [])

    metadata = raw.get("metadata", {}) or {}

    # ServerHub 扩展字段
    version = str(metadata.get("version", "0.1.0"))

    allowed_roles_raw = metadata.get("allowed-roles", "admin user")
    if isinstance(allowed_roles_raw, str):
        allowed_roles = allowed_roles_raw.split() if allowed_roles_raw.strip() else ["admin", "user"]
    else:
        allowed_roles = list(allowed_roles_raw or ["admin", "user"])

    page_contexts_raw = metadata.get("page-contexts", "")
    if isinstance(page_contexts_raw, str):
        page_contexts = page_contexts_raw.split() if page_contexts_raw.strip() else []
    else:
        page_contexts = list(page_contexts_raw or [])

    capabilities_raw = metadata.get("capabilities", "")
    if isinstance(capabilities_raw, str):
        capabilities = capabilities_raw.split() if capabilities_raw.strip() else []
    else:
        capabilities = list(capabilities_raw or [])

    compose_raw = metadata.get("compose", "")
    if isinstance(compose_raw, str):
        compose = compose_raw.split() if compose_raw.strip() else []
    else:
        compose = list(compose_raw or [])

    owner = metadata.get("owner", "shared")

    return {
        "id": name,
        "name": name,
        "version": version,
        "summary": description,
        "description": description,
        "allowed_tools": allowed_tools,
        "license": raw.get("license", ""),
        "compatibility": raw.get("compatibility", ""),
        "allowed_roles": allowed_roles,
        "page_contexts": page_contexts,
        "capabilities": capabilities,
        "compose": compose,
        "owner": owner,
        # 兼容旧代码的 triggers 结构
        "triggers": {
            "keywords": [],
            "page_contexts": page_contexts,
        },
        "required_tools": allowed_tools,
        "entrypoints": {"type": "prompt"},
    }


# ---------------------------------------------------------------------------
# Skill source 管理
# ---------------------------------------------------------------------------


def _default_skill_sources() -> list[str]:
    return [str(SYSTEM_SKILLS_ROOT), str(INSTALLED_SKILLS_ROOT)]


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


# ---------------------------------------------------------------------------
# 目录扫描
# ---------------------------------------------------------------------------


def _scan_root(root: Path) -> list[dict[str, Any]]:
    """扫描目录下的技能子目录，优先用 SKILL.md frontmatter，回退兼容 skill.yaml。"""
    if not root.exists() or not root.is_dir():
        return []
    candidates: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        try:
            manifest = parse_skill_md(child)
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


# ---------------------------------------------------------------------------
# 数据库 CRUD
# ---------------------------------------------------------------------------


async def list_skills() -> list[dict[str, Any]]:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, version, name, summary, enabled, source_type, source_ref, install_path, manifest_json,
               created_at, updated_at, owner
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
            "owner": row[11] or "system",
        }
        for row in rows
    ]


async def get_skill(skill_id: str, *, include_content: bool = False) -> dict[str, Any] | None:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, version, name, summary, enabled, source_type, source_ref, install_path, manifest_json,
               created_at, updated_at, owner
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
        "owner": row[11] or "system",
    }
    if include_content:
        skill_md = install_path / "SKILL.md"
        if skill_md.exists():
            result["skill_markdown"] = skill_md.read_text(encoding="utf-8")
        else:
            result["skill_markdown"] = ""
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
    owner: str = "shared",
) -> dict[str, Any]:
    db = await get_db()
    payload = json.dumps(manifest, ensure_ascii=False)
    now = now_iso()

    # 保存版本快照
    snapshot_dir = SKILL_VERSIONS_ROOT / manifest["id"] / manifest["version"]
    snapshot_path = ""
    try:
        if install_path.exists():  # noqa: ASYNC240 — 管理员操作，非热路径
            snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir)
            shutil.copytree(install_path, snapshot_dir)
            snapshot_path = str(snapshot_dir)
    except Exception as exc:
        logger.warning("版本快照保存失败 %s@%s: %s", manifest["id"], manifest["version"], exc)

    await db.execute(
        """
        INSERT INTO agent_skills (
            id, version, name, summary, enabled, source_type, source_ref, install_path,
            manifest_json, owner, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            version = excluded.version,
            name = excluded.name,
            summary = excluded.summary,
            source_type = excluded.source_type,
            source_ref = excluded.source_ref,
            install_path = excluded.install_path,
            manifest_json = excluded.manifest_json,
            owner = excluded.owner,
            updated_at = excluded.updated_at
        """,
        (
            manifest["id"],
            manifest["version"],
            manifest.get("name", manifest["id"]),
            manifest.get("summary", manifest.get("description", "")),
            source_type,
            source_ref,
            str(install_path),
            payload,
            owner,
            now,
            now,
        ),
    )
    await db.execute(
        """
        INSERT INTO agent_skill_versions (skill_id, version, manifest_json, source_type, source_ref, snapshot_path)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (manifest["id"], manifest["version"], payload, source_type, source_ref, snapshot_path),
    )
    await db.commit()
    await _log_install(manifest["id"], "install", "success", {"install_path": str(install_path)}, created_by)
    return await get_skill(manifest["id"], include_content=True)  # type: ignore[return-value]


def _copy_skill_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)


# ---------------------------------------------------------------------------
# 安装
# ---------------------------------------------------------------------------


async def install_skill_from_repo(repo_path: str, *, created_by: str) -> dict[str, Any]:
    source = Path(repo_path).expanduser().resolve()  # noqa: ASYNC240 — 管理员操作，非热路径
    manifest = parse_skill_md(source)
    target = INSTALLED_SKILLS_ROOT / manifest["id"]
    target.parent.mkdir(parents=True, exist_ok=True)
    _copy_skill_tree(source, target)
    return await _upsert_skill(
        manifest,
        install_path=target,
        source_type="repo",
        source_ref=str(source),
        created_by=created_by,
        owner=manifest.get("owner", "shared"),
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
            archive.extractall(destination, filter="data")
    else:
        raise ValueError("仅支持 zip/tar.gz/tgz 上传")

    children = [child for child in destination.iterdir() if child.is_dir()]
    if len(children) == 1 and not (destination / "SKILL.md").exists():
        return children[0]
    return destination


async def install_skill_from_upload(filename: str, content: bytes, *, created_by: str) -> dict[str, Any]:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_UPLOAD_SUFFIXES and not filename.endswith((".tar.gz", ".tgz")):
        raise ValueError("仅支持 zip/tar.gz/tgz 技能包")
    with tempfile.TemporaryDirectory(prefix="serverhub-skill-") as tmpdir:
        unpack_root = Path(tmpdir) / "upload"
        skill_root = _safe_extract_archive(filename, content, unpack_root)
        manifest = parse_skill_md(skill_root)
        target = INSTALLED_SKILLS_ROOT / manifest["id"]
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_skill_tree(skill_root, target)
        return await _upsert_skill(
            manifest,
            install_path=target,
            source_type="upload",
            source_ref=filename,
            created_by=created_by,
            owner=manifest.get("owner", "shared"),
        )


# ---------------------------------------------------------------------------
# 启禁 / 删除
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 新增 CRUD：create / update / export / list_files / get_visible_skills
# ---------------------------------------------------------------------------


async def create_skill(
    name: str,
    skill_md: str,
    files: dict[str, str] | None = None,
    *,
    created_by: str,
) -> dict[str, Any]:
    """创建一个新技能，将 skill_md 写入 SKILL.md。

    根据 frontmatter 中 metadata.owner 决定存储位置:
    - system → data/skills/system/{name}/
    - shared → data/skills/installed/{name}/
    - 其他 → data/skills/users/{owner}/{name}/
    """
    # 先从 frontmatter 解析 owner
    match = _FRONTMATTER_RE.match(skill_md)
    owner = "shared"
    if match:
        raw = yaml.safe_load(match.group(1)) or {}
        metadata = raw.get("metadata", {}) or {}
        owner = metadata.get("owner", "shared")

    if owner == "system":
        target = SYSTEM_SKILLS_ROOT / name
    elif owner == "shared":
        target = INSTALLED_SKILLS_ROOT / name
    else:
        target = USER_SKILLS_ROOT / owner / name

    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(skill_md, encoding="utf-8")

    # 创建可选子目录
    for sub in _ASSET_DIRS:
        (target / sub).mkdir(exist_ok=True)

    # 写入附属文件
    if files:
        _write_skill_files(target, files)

    manifest = parse_skill_md(target)
    return await _upsert_skill(
        manifest,
        install_path=target,
        source_type="created",
        source_ref="",
        created_by=created_by,
        owner=owner,
    )


async def update_skill(
    skill_id: str,
    skill_md: str | None = None,
    files: dict[str, str] | None = None,
    *,
    updated_by: str,
) -> dict[str, Any] | None:
    """更新技能的 SKILL.md 内容和/或附属文件，重新解析 manifest 并写入数据库。"""
    current = await get_skill(skill_id)
    if not current:
        return None

    install_path = Path(current["install_path"])
    if not install_path.exists():  # noqa: ASYNC240 — 管理员操作，非热路径
        return None

    if skill_md is not None:
        (install_path / "SKILL.md").write_text(skill_md, encoding="utf-8")

    if files:
        _write_skill_files(install_path, files)

    manifest = parse_skill_md(install_path)
    return await _upsert_skill(
        manifest,
        install_path=install_path,
        source_type=current["source_type"],
        source_ref=current["source_ref"],
        created_by=updated_by,
        owner=current.get("owner", "shared"),
    )


def _write_skill_files(root: Path, files: dict[str, str]) -> None:
    """将 {相对路径: 内容} 写入技能目录，只允许 _ASSET_DIRS 子目录。"""
    for rel_path, content in files.items():
        p = Path(rel_path)
        if p.is_absolute() or ".." in p.parts:
            raise ValueError(f"非法文件路径: {rel_path}")
        # 安全检查：必须在白名单子目录下
        if p.parts and p.parts[0] not in _ASSET_DIRS:
            raise ValueError(f"文件路径必须在 {'/'.join(_ASSET_DIRS)} 子目录下: {rel_path}")
        target = root / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


async def export_skill(skill_id: str) -> bytes:
    """导出技能为 zip 字节流。"""
    current = await get_skill(skill_id)
    if not current:
        raise ValueError(f"技能 {skill_id} 不存在")

    install_path = Path(current["install_path"])
    if not install_path.exists():  # noqa: ASYNC240 — 管理员操作，非热路径
        raise ValueError(f"技能目录不存在: {install_path}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in install_path.rglob("*"):  # noqa: ASYNC240
            if file.is_file():
                arcname = file.relative_to(install_path)
                zf.write(file, arcname)
    return buf.getvalue()


async def export_skill_zip(skill_id: str) -> dict[str, Any] | None:
    """导出技能为 zip，返回 {stream, filename} 或 None。"""
    current = await get_skill(skill_id)
    if not current:
        return None
    try:
        data = await export_skill(skill_id)
    except ValueError:
        return None
    return {
        "stream": io.BytesIO(data),
        "filename": f"{skill_id}.zip",
    }


def _list_skill_files(install_path: str) -> list[dict[str, Any]]:
    """列出 references/, scripts/, assets/, evals/ 中的文件。"""
    root = Path(install_path)
    files: list[dict[str, Any]] = []
    for sub in _ASSET_DIRS:
        sub_dir = root / sub
        if not sub_dir.is_dir():
            continue
        for file in sorted(sub_dir.rglob("*")):
            if file.is_file():
                rel = str(file.relative_to(root))
                files.append(
                    {
                        "path": rel,
                        "category": sub,
                        "size": file.stat().st_size,
                    }
                )
    return files


# 保留旧名兼容
list_skill_files = _list_skill_files


async def get_skill_files(skill_id: str) -> list[dict[str, Any]] | None:
    """异步获取技能附属文件列表。"""
    current = await get_skill(skill_id)
    if not current:
        return None
    return _list_skill_files(current["install_path"])


async def upload_skill_file(*, skill_id: str, file_path: str, content: str) -> bool:
    """上传/更新技能附属文件。"""
    current = await get_skill(skill_id)
    if not current:
        return False
    install_path = Path(current["install_path"])
    p = Path(file_path)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"非法文件路径: {file_path}")
    if p.parts and p.parts[0] not in _ASSET_DIRS:
        raise ValueError(f"文件路径必须在 {'/'.join(_ASSET_DIRS)} 子目录下: {file_path}")
    target = install_path / p
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return True


async def delete_skill_file(*, skill_id: str, file_path: str) -> bool:
    """删除技能附属文件。"""
    current = await get_skill(skill_id)
    if not current:
        return False
    install_path = Path(current["install_path"])
    p = Path(file_path)
    if p.is_absolute() or ".." in p.parts:
        return False
    target = install_path / p
    if not target.exists() or not target.is_file():
        return False
    target.unlink()
    return True


async def list_enabled_skills(*, user_role: str = "admin") -> list[dict[str, Any]]:
    """返回 enabled 技能的 name+description（给 /skill: 菜单用）。"""
    result = []
    for skill in await list_skills():
        if not skill["enabled"]:
            continue
        manifest = skill["manifest"]
        if user_role not in manifest.get("allowed_roles", ["admin", "user"]):
            continue
        result.append(
            {
                "id": skill["id"],
                "name": skill["name"],
                "description": manifest.get("description", skill["summary"]),
            }
        )
    return result


# ---------------------------------------------------------------------------
# 版本管理与回滚
# ---------------------------------------------------------------------------


async def get_skill_versions(skill_id: str) -> list[dict[str, Any]] | None:
    """列出技能的版本记录。"""
    current = await get_skill(skill_id)
    if not current:
        return None
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, version, manifest_json, source_type, source_ref, snapshot_path, created_at
        FROM agent_skill_versions
        WHERE skill_id = ?
        ORDER BY created_at DESC
        """,
        (skill_id,),
    )
    rows = await cursor.fetchall()
    return [
        {
            "id": row[0],
            "version": row[1],
            "manifest": json.loads(row[2]),
            "source_type": row[3],
            "source_ref": row[4],
            "snapshot_path": row[5] or "",
            "created_at": row[6],
        }
        for row in rows
    ]


async def rollback_skill(*, skill_id: str, version: str, rolled_back_by: str) -> bool:
    """回滚技能到指定版本快照。"""
    current = await get_skill(skill_id)
    if not current:
        return False

    # 查找目标版本的快照路径
    db = await get_db()
    cursor = await db.execute(
        "SELECT snapshot_path FROM agent_skill_versions WHERE skill_id = ? AND version = ? ORDER BY created_at DESC LIMIT 1",
        (skill_id, version),
    )
    row = await cursor.fetchone()
    if not row or not row[0]:
        return False

    snapshot_dir = Path(row[0])
    if not snapshot_dir.exists():  # noqa: ASYNC240 — 管理员操作
        return False

    install_path = Path(current["install_path"])
    _copy_skill_tree(snapshot_dir, install_path)

    manifest = parse_skill_md(install_path)
    await _upsert_skill(
        manifest,
        install_path=install_path,
        source_type=current["source_type"],
        source_ref=current["source_ref"],
        created_by=rolled_back_by,
        owner=current.get("owner", "shared"),
    )
    await _log_install(skill_id, "rollback", "success", {"target_version": version}, rolled_back_by)
    return True


# ---------------------------------------------------------------------------
# 评测（stub 实现，完整评测引擎在 skill_eval.py）
# ---------------------------------------------------------------------------


async def get_skill_evals(skill_id: str) -> dict[str, Any] | None:
    """获取技能评测用例集（从 evals/evals.json 读取）。"""
    current = await get_skill(skill_id)
    if not current:
        return None
    evals_path = Path(current["install_path"]) / "evals" / "evals.json"
    if evals_path.exists():
        try:
            return json.loads(evals_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("读取评测用例失败 %s: %s", skill_id, exc)
    return {"skill_name": skill_id, "evals": []}


async def save_skill_evals(*, skill_id: str, evals_data: dict) -> bool:
    """保存技能评测用例集到 evals/evals.json。"""
    current = await get_skill(skill_id)
    if not current:
        return False
    evals_dir = Path(current["install_path"]) / "evals"
    evals_dir.mkdir(exist_ok=True)
    (evals_dir / "evals.json").write_text(
        json.dumps(evals_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return True


async def run_skill_eval(
    *,
    skill_id: str,
    eval_id: int | None = None,
    mode: str = "ab",
    triggered_by: str = "admin",
) -> dict[str, Any] | None:
    """执行技能评测（桩实现，完整引擎在后续 Phase 3）。"""
    current = await get_skill(skill_id)
    if not current:
        return None
    # 返回异步任务占位
    import uuid

    task_id = str(uuid.uuid4())
    logger.info("评测任务已创建 %s (skill=%s, mode=%s, by=%s)", task_id, skill_id, mode, triggered_by)
    return {"task_id": task_id, "status": "pending", "message": "评测引擎将在 Phase 3 完整实现"}


async def get_skill_eval_results(skill_id: str) -> list[dict[str, Any]] | None:
    """获取技能评测结果列表（桩实现）。"""
    current = await get_skill(skill_id)
    if not current:
        return None
    return []


async def get_visible_skills(user: dict) -> list[dict[str, Any]]:
    """按用户角色和 owner 过滤返回可见技能。

    - admin: 看所有
    - user: system 技能 + shared 中 allowed_roles 含 user 的 + 自己的私有技能
    """
    all_skills = await list_skills()
    role = user.get("role", "user")
    username = user.get("username", "")

    if role == "admin":
        return all_skills

    visible = []
    for skill in all_skills:
        if not skill["enabled"]:
            continue
        owner = skill.get("owner", "system")
        manifest = skill.get("manifest", {})
        allowed_roles = manifest.get("allowed_roles", ["admin", "user"])

        # system 技能：按 allowed_roles 过滤
        if owner == "system" or owner == "shared":
            if role in allowed_roles:
                visible.append(skill)
        # 私有技能：仅 owner 本人可见
        elif owner == username:
            visible.append(skill)
    return visible


# ---------------------------------------------------------------------------
# 推荐（description 全文搜索 + 简单评分）
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """简单分词：中文逐字、英文按空格/标点。"""
    tokens: list[str] = []
    buf = ""
    for ch in text.lower():
        if "\u4e00" <= ch <= "\u9fff":
            if buf:
                tokens.append(buf)
                buf = ""
            tokens.append(ch)
        elif ch.isalnum() or ch == "-":
            buf += ch
        else:
            if buf:
                tokens.append(buf)
                buf = ""
    if buf:
        tokens.append(buf)
    return tokens


async def recommend_skills(
    *,
    message: str,
    page_context: str | None = None,
    user_role: str = "admin",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """基于 description 全文搜索 + page_context 匹配推荐技能。"""
    candidates = []
    msg_tokens = set(_tokenize(message))

    for skill in await list_skills():
        if not skill["enabled"]:
            continue
        manifest = skill["manifest"]
        if user_role not in manifest.get("allowed_roles", ["admin", "user"]):
            continue

        score = 0.0
        reasons: list[str] = []

        # description 全文搜索评分
        description = manifest.get("description", manifest.get("summary", ""))
        desc_tokens = set(_tokenize(description))
        matched = msg_tokens & desc_tokens
        if matched:
            # 每命中一个 token 加分，中文字权重 1.5，英文词权重 2.0
            for tok in matched:
                if len(tok) == 1 and "\u4e00" <= tok <= "\u9fff":
                    score += 1.5
                else:
                    score += 2.0
            reasons.append(f"描述匹配: {', '.join(sorted(matched)[:5])}")

        # capabilities 匹配
        for cap in manifest.get("capabilities", []):
            cap_tokens = set(_tokenize(cap))
            cap_matched = msg_tokens & cap_tokens
            if cap_matched:
                score += 1.5
                reasons.append(f"能力匹配: {cap}")

        # page_context 精确匹配
        for ctx in manifest.get("page_contexts", manifest.get("triggers", {}).get("page_contexts", [])):
            if page_context and ctx == page_context:
                score += 3.0
                reasons.append(f"适配页面 {ctx}")

        # name 精确匹配
        skill_name_tokens = set(_tokenize(skill["name"]))
        name_matched = msg_tokens & skill_name_tokens
        if name_matched:
            score += 3.0
            reasons.append(f"名称匹配: {skill['name']}")

        if score > 0:
            candidates.append(
                {
                    "id": skill["id"],
                    "name": skill["name"],
                    "summary": skill["summary"],
                    "score": round(score, 1),
                    "reasons": reasons,
                }
            )
    candidates.sort(key=lambda item: (-item["score"], item["name"]))
    return candidates[:limit]


# ---------------------------------------------------------------------------
# 上下文加载（不变）
# ---------------------------------------------------------------------------


async def load_skill_context(skill_id: str) -> str:
    skill = await get_skill(skill_id, include_content=True)
    if not skill or not skill["enabled"]:
        return ""
    return f"[已启用技能: {skill['name']}]\n摘要: {skill['summary']}\n\n{skill['skill_markdown']}\n"

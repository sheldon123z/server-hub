"""技能市场：远程 registry 同步、市场安装、更新检查、自动更新循环。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from config import BASE_DIR, settings
from modules.agents.run_service import now_iso
from modules.agents.skill_service import (
    INSTALLED_SKILLS_ROOT,
    _copy_skill_tree,
    _upsert_skill,
    get_skill,
    list_skills,
    parse_skill_md,
)
from modules.agents.skill_version import snapshot_version

logger = logging.getLogger(__name__)

SKILL_CACHE_ROOT = BASE_DIR / "data" / "skill-cache"
MARKET_SOURCES_FILE = BASE_DIR / "data" / "skill-market-sources.json"


def _parse_version(v: str) -> tuple[int, ...]:
    """将语义化版本字符串拆为整数元组，便于比较。"""
    try:
        from packaging.version import Version

        pv = Version(v)
        return (pv.major, pv.minor, pv.micro)
    except Exception:
        parts: list[int] = []
        for seg in v.strip().split("."):
            try:
                parts.append(int(seg))
            except ValueError:
                parts.append(0)
        return tuple(parts)


def _version_gt(a: str, b: str) -> bool:
    """a > b 则返回 True。"""
    return _parse_version(a) > _parse_version(b)


# ---------------------------------------------------------------------------
# 远程源管理
# ---------------------------------------------------------------------------


def load_market_sources() -> list[dict[str, str]]:
    """加载已配置的远程源列表。"""
    if not MARKET_SOURCES_FILE.exists():
        return []
    try:
        data = json.loads(MARKET_SOURCES_FILE.read_text(encoding="utf-8"))
        return data.get("sources", [])
    except Exception as exc:
        logger.warning("市场源文件读取失败: %s", exc)
        return []


def save_market_sources(sources: list[dict[str, str]]) -> None:
    """持久化远程源列表。"""
    MARKET_SOURCES_FILE.parent.mkdir(parents=True, exist_ok=True)
    MARKET_SOURCES_FILE.write_text(
        json.dumps({"sources": sources}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# 同步远程市场索引
# ---------------------------------------------------------------------------


async def sync_market(source_url: str, source_type: str = "git") -> dict[str, Any]:
    """同步远程技能市场索引。

    source_type: "git" | "http" | "local"
      git   — git clone --depth 1 或 git pull 到 data/skill-cache/
      http  — GET registry.json 保存到 data/skill-cache/
      local — 直接扫描目录
    返回: {"skills_count": N, "updated_at": "..."}
    """
    SKILL_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    if source_type == "git":
        return await _sync_git(source_url)
    if source_type == "http":
        return await _sync_http(source_url)
    if source_type == "local":
        return await _sync_local(source_url)
    raise ValueError(f"不支持的源类型: {source_type}")


async def _sync_git(repo_url: str) -> dict[str, Any]:
    """通过 git 同步远程仓库。"""
    repo_name = repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")
    target = SKILL_CACHE_ROOT / repo_name

    if (target / ".git").is_dir():
        # 已经克隆过，执行 pull
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            str(target),
            "pull",
            "--ff-only",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("git pull 失败 (%s): %s", repo_url, stderr.decode(errors="replace"))
    else:
        # 首次克隆
        target.parent.mkdir(parents=True, exist_ok=True)
        proc = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            "--depth",
            "1",
            repo_url,
            str(target),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"git clone 失败: {stderr.decode(errors='replace')}")

    registry = _load_registry_from_dir(target)
    return {"skills_count": len(registry), "updated_at": now_iso(), "source": repo_url}


async def _sync_http(url: str) -> dict[str, Any]:
    """通过 HTTP 下载 registry.json。"""
    import urllib.error
    import urllib.request

    registry_url = url.rstrip("/")
    if not registry_url.endswith("registry.json"):
        registry_url += "/registry.json"

    # 在线程池中执行阻塞 HTTP 请求
    loop = asyncio.get_running_loop()

    def _download() -> bytes:
        req = urllib.request.Request(registry_url, headers={"User-Agent": "ServerHub-SkillMarket/1.0"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            return resp.read()

    data = await loop.run_in_executor(None, _download)

    # 保存到缓存
    cache_name = hashlib.sha256(url.encode()).hexdigest()[:12]
    cache_dir = SKILL_CACHE_ROOT / f"http-{cache_name}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    registry_file = cache_dir / "registry.json"
    registry_file.write_bytes(data)

    registry = json.loads(data)
    skills = registry.get("skills", [])
    return {"skills_count": len(skills), "updated_at": now_iso(), "source": url}


async def _sync_local(dir_path: str) -> dict[str, Any]:
    """扫描本地目录作为技能源。"""
    source = Path(dir_path).expanduser().resolve()  # noqa: ASYNC240 — 管理员操作，非热路径
    if not source.is_dir():
        raise ValueError(f"本地目录不存在: {dir_path}")

    registry = _load_registry_from_dir(source)
    return {"skills_count": len(registry), "updated_at": now_iso(), "source": dir_path}


def _load_registry_from_dir(root: Path) -> list[dict[str, Any]]:
    """从目录加载 registry.json 或扫描子目录构建索引。"""
    registry_file = root / "registry.json"
    if registry_file.exists():
        try:
            data = json.loads(registry_file.read_text(encoding="utf-8"))
            return data.get("skills", [])
        except Exception as exc:
            logger.warning("registry.json 解析失败: %s", exc)

    # 没有 registry.json，扫描子目录
    skills: list[dict[str, Any]] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.exists():
            continue
        skills.append(
            {
                "name": child.name,
                "version": "0.0.0",
                "path": str(child),
            }
        )
    return skills


# ---------------------------------------------------------------------------
# 获取已缓存的市场索引
# ---------------------------------------------------------------------------


async def get_market_index() -> list[dict[str, Any]]:
    """获取已缓存的市场索引，与本地安装状态对比。"""
    installed_map: dict[str, dict[str, Any]] = {}
    for skill in await list_skills():
        installed_map[skill["id"]] = skill

    index: list[dict[str, Any]] = []

    if not SKILL_CACHE_ROOT.exists():
        return index

    for cache_dir in sorted(SKILL_CACHE_ROOT.iterdir()):
        if not cache_dir.is_dir():
            continue
        registry = _load_registry_from_dir(cache_dir)
        for entry in registry:
            name = entry.get("name", "")
            remote_version = entry.get("version", "0.0.0")
            local = installed_map.get(name)
            item: dict[str, Any] = {
                **entry,
                "installed": local is not None,
                "local_version": local["version"] if local else None,
                "update_available": False,
                "source_cache": str(cache_dir),
            }
            if local and _version_gt(remote_version, local["version"]):
                item["update_available"] = True
            index.append(item)

    return index


# ---------------------------------------------------------------------------
# 从市场安装技能
# ---------------------------------------------------------------------------


def _verify_checksum(file_path: Path, expected: str) -> bool:
    """校验文件 SHA-256 checksum。"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest() == expected.lower()


def _find_skill_in_cache(skill_name: str) -> Path | None:
    """在缓存目录中查找技能包目录。"""
    if not SKILL_CACHE_ROOT.exists():
        return None
    for cache_dir in SKILL_CACHE_ROOT.iterdir():
        if not cache_dir.is_dir():
            continue
        # 查找 registry.json 中记录的路径
        registry_file = cache_dir / "registry.json"
        if registry_file.exists():
            try:
                data = json.loads(registry_file.read_text(encoding="utf-8"))
                for entry in data.get("skills", []):
                    if entry.get("name") == skill_name:
                        # 如果有 download_url，需要先下载
                        # 如果有 path，直接使用
                        pkg_path = entry.get("path")
                        if pkg_path:
                            p = Path(pkg_path)
                            if not p.is_absolute():
                                p = cache_dir / p
                            if p.is_dir():
                                return p
            except Exception as exc:
                logger.debug("解析 registry.json 失败 (%s): %s", cache_dir, exc)
        # 直接查找子目录
        candidate = cache_dir / skill_name
        if candidate.is_dir() and (candidate / "SKILL.md").exists():
            return candidate
    return None


async def install_from_market(
    skill_name: str,
    version: str | None = None,
    *,
    created_by: str = "system",
) -> dict[str, Any]:
    """从市场安装技能。

    1. 从缓存目录找到技能包
    2. 校验 checksum（如果 registry 中有提供）
    3. 复制到 data/skills/installed/
    4. 调用 skill_service 注册到数据库
    """
    skill_dir = _find_skill_in_cache(skill_name)
    if skill_dir is None:
        raise ValueError(f"在市场缓存中未找到技能: {skill_name}。请先执行 sync_market 同步索引。")

    # 读取 manifest
    manifest = parse_skill_md(skill_dir)
    if version and manifest.get("version") != version:
        logger.warning(
            "请求版本 %s，但缓存中为 %s，将使用缓存版本",
            version,
            manifest.get("version"),
        )

    # 如果该技能已安装，先做版本快照
    existing = await get_skill(manifest["id"])
    if existing:
        existing_path = Path(existing["install_path"])
        if existing_path.is_dir():  # noqa: ASYNC240 — 管理员操作，非热路径
            await snapshot_version(manifest["id"], existing["version"], existing_path)

    # 校验 checksum（从 registry 中读取）
    checksum = _get_registry_checksum(skill_name)
    if checksum:
        # 对整个目录做简单校验（校验 SKILL.md）
        skill_md = skill_dir / "SKILL.md"
        if skill_md.exists() and not _verify_checksum(skill_md, checksum):
            logger.warning("技能 %s 的 SKILL.md checksum 不匹配，继续安装", skill_name)

    # 复制到 installed 目录
    target = INSTALLED_SKILLS_ROOT / manifest["id"]
    target.parent.mkdir(parents=True, exist_ok=True)
    _copy_skill_tree(skill_dir, target)

    # 注册到数据库
    result = await _upsert_skill(
        manifest,
        install_path=target,
        source_type="market",
        source_ref=skill_name,
        created_by=created_by,
    )

    # 保存版本快照
    await snapshot_version(manifest["id"], manifest["version"], target)

    logger.info("从市场安装技能: %s v%s", skill_name, manifest["version"])
    return result


def _get_registry_checksum(skill_name: str) -> str | None:
    """从缓存的 registry.json 中获取技能的 checksum。"""
    if not SKILL_CACHE_ROOT.exists():
        return None
    for cache_dir in SKILL_CACHE_ROOT.iterdir():
        registry_file = cache_dir / "registry.json"
        if not registry_file.exists():
            continue
        try:
            data = json.loads(registry_file.read_text(encoding="utf-8"))
            for entry in data.get("skills", []):
                if entry.get("name") == skill_name:
                    return entry.get("checksum")
        except Exception as exc:
            logger.debug("读取 registry checksum 失败 (%s): %s", cache_dir, exc)
    return None


# ---------------------------------------------------------------------------
# 检查可用更新
# ---------------------------------------------------------------------------


async def check_updates() -> list[dict[str, Any]]:
    """对比本地已安装版本与 registry，返回可更新列表。

    返回: [{"skill_id": "...", "local_version": "0.1.0", "remote_version": "0.2.0"}, ...]
    """
    installed_map: dict[str, dict[str, Any]] = {}
    for skill in await list_skills():
        installed_map[skill["id"]] = skill

    updates: list[dict[str, Any]] = []

    if not SKILL_CACHE_ROOT.exists():
        return updates

    for cache_dir in SKILL_CACHE_ROOT.iterdir():
        if not cache_dir.is_dir():
            continue
        registry = _load_registry_from_dir(cache_dir)
        for entry in registry:
            name = entry.get("name", "")
            remote_version = entry.get("version", "0.0.0")
            local = installed_map.get(name)
            if local and _version_gt(remote_version, local["version"]):
                updates.append(
                    {
                        "skill_id": name,
                        "skill_name": local.get("name", name),
                        "local_version": local["version"],
                        "remote_version": remote_version,
                        "source_cache": str(cache_dir),
                    }
                )

    return updates


# ---------------------------------------------------------------------------
# 自动更新循环
# ---------------------------------------------------------------------------

_UPDATE_CHECK_INTERVAL = 24 * 60 * 60  # 24 小时


async def skill_update_check_loop() -> None:
    """自动更新循环 — 每 24h 检查一次。

    读取 settings.skill_auto_update: manual/notify/auto
      manual — 不做任何事
      notify — 调用 send_notification 通知管理员
      auto   — 自动安装更新（先 snapshot 旧版本）
    """
    logger.info("技能自动更新检查循环已启动")
    while True:
        try:
            await asyncio.sleep(_UPDATE_CHECK_INTERVAL)

            policy = getattr(settings, "skill_auto_update", "manual")
            if policy == "manual":
                continue

            # 先同步所有已配置的远程源
            sources = load_market_sources()
            for src in sources:
                try:
                    await sync_market(src.get("url", ""), src.get("type", "git"))
                except Exception as exc:
                    logger.warning("同步远程源失败 (%s): %s", src.get("url"), exc)

            # 检查可用更新
            updates = await check_updates()
            if not updates:
                logger.debug("无技能更新可用")
                continue

            if policy == "notify":
                await _notify_updates(updates)
            elif policy == "auto":
                await _auto_install_updates(updates)

        except asyncio.CancelledError:
            logger.info("技能自动更新循环已停止")
            break
        except Exception as exc:
            logger.exception("技能更新检查异常: %s", exc)


async def _notify_updates(updates: list[dict[str, Any]]) -> None:
    """发送更新通知给管理员。"""
    try:
        from modules.notifications.services import send_notification

        lines = ["🔧 ServerHub 技能市场有可用更新:"]
        for u in updates:
            lines.append(f"  • {u['skill_id']}: {u['local_version']} → {u['remote_version']}")
        lines.append("\n请前往管理面板手动更新。")
        await send_notification("\n".join(lines))
        logger.info("已发送 %d 个技能更新通知", len(updates))
    except Exception as exc:
        logger.warning("发送技能更新通知失败: %s", exc)


async def _auto_install_updates(updates: list[dict[str, Any]]) -> None:
    """自动安装所有可用更新（先快照旧版本）。"""
    from modules.agents.deep_agent import reset_agent_cache

    success_count = 0
    for u in updates:
        try:
            await install_from_market(u["skill_id"], u["remote_version"], created_by="auto-update")
            success_count += 1
            logger.info("自动更新技能: %s %s → %s", u["skill_id"], u["local_version"], u["remote_version"])
        except Exception as exc:
            logger.warning("自动更新技能失败 (%s): %s", u["skill_id"], exc)

    if success_count > 0:
        reset_agent_cache()
        logger.info("自动更新完成，共更新 %d 个技能", success_count)

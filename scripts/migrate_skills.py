#!/usr/bin/env python3
"""skill.yaml → SKILL.md frontmatter 迁移脚本。

扫描 data/skills/ 下所有含 skill.yaml 的目录，将其字段合并到
SKILL.md 的 YAML frontmatter 中。完成后删除 skill.yaml。

用法:
    python scripts/migrate_skills.py           # 执行迁移
    python scripts/migrate_skills.py --dry-run  # 仅预览，不修改文件
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

SKILLS_ROOT = Path(__file__).resolve().parent.parent / "data" / "skills"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _load_yaml_file(path: Path) -> dict:
    """安全加载 YAML 文件。"""
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _build_frontmatter(old_yaml: dict, existing_fm: dict | None) -> dict:
    """将 skill.yaml 字段映射为 SKILL.md frontmatter 格式，与已有 frontmatter 合并。"""
    fm: dict = dict(existing_fm) if existing_fm else {}

    # 标准字段映射: skill.yaml → SKILL.md frontmatter
    if "id" in old_yaml and "name" not in fm:
        fm["name"] = old_yaml["id"]
    if "name" in old_yaml and "name" not in fm:
        # skill.yaml 的 name 是显示名，frontmatter 的 name 应是 kebab-case id
        fm.setdefault("name", old_yaml.get("id", old_yaml["name"]))

    if "summary" in old_yaml and "description" not in fm:
        fm["description"] = old_yaml["summary"]

    # allowed-tools 从 required_tools 映射
    if "required_tools" in old_yaml and "allowed-tools" not in fm:
        tools = old_yaml["required_tools"]
        if isinstance(tools, list):
            fm["allowed-tools"] = " ".join(tools)
        else:
            fm["allowed-tools"] = str(tools)

    # metadata 子字段
    metadata = fm.get("metadata", {}) or {}

    if "version" in old_yaml:
        metadata.setdefault("version", old_yaml["version"])
    if "allowed_roles" in old_yaml:
        roles = old_yaml["allowed_roles"]
        if isinstance(roles, list):
            metadata.setdefault("allowed-roles", " ".join(roles))
        else:
            metadata.setdefault("allowed-roles", str(roles))
    if "capabilities" in old_yaml:
        caps = old_yaml["capabilities"]
        if isinstance(caps, list):
            metadata.setdefault("capabilities", " ".join(caps))
        else:
            metadata.setdefault("capabilities", str(caps))

    # triggers → page-contexts
    triggers = old_yaml.get("triggers", {})
    if isinstance(triggers, dict):
        page_ctxs = triggers.get("page_contexts", [])
        if page_ctxs and "page-contexts" not in metadata:
            if isinstance(page_ctxs, list):
                metadata["page-contexts"] = " ".join(page_ctxs)
            else:
                metadata["page-contexts"] = str(page_ctxs)

    # 触发关键词追加到 description（让 description 全文搜索能覆盖）
    keywords = triggers.get("keywords", []) if isinstance(triggers, dict) else []
    if keywords and "description" in fm:
        existing_desc = fm["description"]
        kw_text = "、".join(keywords) if keywords else ""
        # 如果 description 中还没包含这些关键词，追加触发场景说明
        if kw_text and not all(kw in existing_desc for kw in keywords[:2]):
            fm["description"] = f"{existing_desc}\n  触发场景：{kw_text}"

    metadata.setdefault("owner", "shared")

    if metadata:
        fm["metadata"] = metadata

    return fm


def _dump_frontmatter(fm: dict) -> str:
    """将 frontmatter dict 序列化为 YAML 字符串（保持可读性）。"""
    return yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False).strip()


def migrate_skill_dir(skill_dir: Path, *, dry_run: bool = False) -> bool:
    """迁移单个技能目录。返回 True 表示有变更。"""
    yaml_path = skill_dir / "skill.yaml"
    md_path = skill_dir / "SKILL.md"

    if not yaml_path.exists():
        return False

    print(f"  处理: {skill_dir.relative_to(SKILLS_ROOT)}")

    # 读取 skill.yaml
    old_yaml = _load_yaml_file(yaml_path)
    print(f"    skill.yaml 字段: {list(old_yaml.keys())}")

    # 读取已有 SKILL.md
    existing_fm = None
    body = ""
    if md_path.exists():
        content = md_path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(content)
        if match:
            existing_fm = yaml.safe_load(match.group(1)) or {}
            body = content[match.end() :]
            print(f"    SKILL.md 已有 frontmatter: {list(existing_fm.keys())}")
        else:
            body = content
            print("    SKILL.md 无 frontmatter，将新建")
    else:
        print("    SKILL.md 不存在，将从 skill.yaml 创建")
        # 用 summary 作为默认正文
        display_name = old_yaml.get("name", old_yaml.get("id", skill_dir.name))
        summary = old_yaml.get("summary", "")
        body = f"\n# {display_name}\n\n{summary}\n"

    # 合并 frontmatter
    merged_fm = _build_frontmatter(old_yaml, existing_fm)
    print(f"    合并后 frontmatter: {list(merged_fm.keys())}")

    # 生成新 SKILL.md
    new_content = f"---\n{_dump_frontmatter(merged_fm)}\n---\n{body}"

    if dry_run:
        print(f"    [dry-run] 将写入 SKILL.md ({len(new_content)} 字符)")
        print("    [dry-run] 将删除 skill.yaml")
        return True

    # 写入
    md_path.write_text(new_content, encoding="utf-8")
    print(f"    已写入 SKILL.md ({len(new_content)} 字符)")

    # 删除 skill.yaml
    yaml_path.unlink()
    print("    已删除 skill.yaml")

    return True


def main():
    parser = argparse.ArgumentParser(description="skill.yaml → SKILL.md frontmatter 迁移")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不修改文件")
    args = parser.parse_args()

    print(f"技能根目录: {SKILLS_ROOT}")
    print(f"模式: {'dry-run (预览)' if args.dry_run else '执行迁移'}")
    print()

    if not SKILLS_ROOT.exists():
        print("技能根目录不存在，无需迁移。")
        sys.exit(0)

    migrated = 0
    # 递归扫描所有含 skill.yaml 的目录
    for yaml_file in sorted(SKILLS_ROOT.rglob("skill.yaml")):
        skill_dir = yaml_file.parent
        if migrate_skill_dir(skill_dir, dry_run=args.dry_run):
            migrated += 1

    print()
    if migrated == 0:
        print("未找到需要迁移的 skill.yaml 文件。")
    else:
        action = "将迁移" if args.dry_run else "已迁移"
        print(f"{action} {migrated} 个技能目录。")


if __name__ == "__main__":
    main()

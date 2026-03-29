"""资产台账与故障案例工具"""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
async def get_asset_inventory(asset_type: str = "") -> str:
    """查询服务器资产清单。返回所有已发现的服务、容器、端口、存储等资产。

    Args:
        asset_type: 可选，按类型过滤（service/container/compose/port/storage）。留空返回全部。
    """
    from modules.assets.services import get_assets

    assets = await get_assets(asset_type)
    if not assets:
        return f"没有找到{'类型为 ' + asset_type + ' 的' if asset_type else ''}资产。请先执行资产发现。"

    type_names = {
        "service": "系统服务",
        "container": "Docker容器",
        "compose": "Compose堆栈",
        "port": "监听端口",
        "storage": "存储挂载",
    }
    lines = ["## 资产清单\n"]

    current_type = ""
    for a in assets:
        if a["type"] != current_type:
            current_type = a["type"]
            lines.append(f"\n### {type_names.get(current_type, current_type)}\n")
            lines.append("| 名称 | 状态 | 详情 |")
            lines.append("|---|---|---|")
        props = a.get("properties", {})
        detail = ", ".join(f"{k}={v}" for k, v in (props.items() if isinstance(props, dict) else []))[:80]
        status_icon = {"running": "🟢", "stopped": "🔴", "listening": "🔵", "ok": "🟢", "warning": "🟡"}.get(
            a["status"], "⚪"
        )
        lines.append(f"| {a['name']} | {status_icon} {a['status']} | {detail} |")

    lines.append(f"\n共 {len(assets)} 项资产")
    return "\n".join(lines)


@tool
async def get_asset_topology() -> str:
    """生成服务器资产拓扑关系图（Mermaid 格式）并分析潜在风险（单点故障、冗余不足等）。"""
    from modules.assets.services import generate_topology_mermaid, get_assets

    assets = await get_assets()
    if not assets:
        return "没有资产数据。请先执行资产发现。"

    mermaid = await generate_topology_mermaid()

    risks = []
    type_counts = {}
    stopped = []
    for a in assets:
        type_counts[a["type"]] = type_counts.get(a["type"], 0) + 1
        if a["status"] in ("stopped", "unknown"):
            stopped.append(a)

    if stopped:
        risks.append(f"⚠️ {len(stopped)} 个资产处于停止/未知状态: {', '.join(a['name'] for a in stopped[:5])}")

    for t, count in type_counts.items():
        if t == "compose" and count > 0:
            risks.append(f"ℹ️ {count} 个 Compose 堆栈（单节点部署，无高可用）")

    risk_text = "\n".join(risks) if risks else "未发现明显风险"
    return f"## 资产拓扑图\n\n```mermaid\n{mermaid}\n```\n\n## 风险分析\n{risk_text}\n\n共 {len(assets)} 项资产"


@tool
async def save_fault_case(
    title: str, category: str, symptoms: str, root_cause: str, solution: str, tags: str = ""
) -> str:
    """将故障案例保存到案例库。

    Args:
        title: 案例标题（简短描述问题）
        category: 分类（memory/docker/service/network/security/gpu）
        symptoms: 症状描述
        root_cause: 根本原因
        solution: 解决方案
        tags: 标签（逗号分隔，如 "内存,超限,kill"）
    """
    import aiosqlite

    from config import settings

    try:
        async with aiosqlite.connect(settings.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO fault_cases (title, category, symptoms, root_cause, solution, tags, source) "
                "VALUES (?, ?, ?, ?, ?, ?, 'manual') RETURNING id",
                (title, category, symptoms, root_cause, solution, tags),
            )
            row = await cursor.fetchone()
            case_id = row[0] if row else None

            if case_id:
                try:
                    await db.execute(
                        "INSERT INTO fault_cases_fts(rowid, title, symptoms, root_cause, solution, tags) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (case_id, title, symptoms, root_cause, solution, tags),
                    )
                except Exception as e:
                    logger.debug("FTS5 索引写入失败: %s", e)

            await db.commit()
            return f"案例已保存 (ID: {case_id})。标题: {title}"
    except Exception as e:
        return f"保存案例失败: {e}"


@tool
async def search_fault_cases(query: str) -> str:
    """搜索故障案例库。从历史故障案例中检索匹配的问题和解决方案。

    Args:
        query: 搜索关键词（如 "内存超限"、"Docker 重启"、"SSH 连接"）
    """
    import aiosqlite

    from config import settings

    try:
        async with aiosqlite.connect(settings.db_path) as db:
            try:
                cursor = await db.execute(
                    "SELECT fc.id, fc.title, fc.category, fc.symptoms, fc.root_cause, fc.solution, fc.tags "
                    "FROM fault_cases_fts fts JOIN fault_cases fc ON fts.rowid = fc.id "
                    "WHERE fault_cases_fts MATCH ? ORDER BY rank LIMIT 5",
                    (query,),
                )
            except Exception:
                like = f"%{query}%"
                cursor = await db.execute(
                    "SELECT id, title, category, symptoms, root_cause, solution, tags "
                    "FROM fault_cases WHERE title LIKE ? OR symptoms LIKE ? OR root_cause LIKE ? OR tags LIKE ? "
                    "ORDER BY created_at DESC LIMIT 5",
                    (like, like, like, like),
                )

            rows = await cursor.fetchall()

        if not rows:
            return f'没有找到与 "{query}" 相关的故障案例。'

        lines = [f'## 故障案例搜索: "{query}" ({len(rows)} 条结果)\n']
        for r in rows:
            lines.append(f"### [{r[2] or '通用'}] {r[1]}")
            if r[3]:
                lines.append(f"**症状**: {r[3][:200]}")
            if r[4]:
                lines.append(f"**根因**: {r[4][:200]}")
            if r[5]:
                lines.append(f"**解决方案**: {r[5][:300]}")
            if r[6]:
                lines.append(f"**标签**: {r[6]}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"搜索案例库失败: {e}"

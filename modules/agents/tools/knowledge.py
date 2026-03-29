"""RAG 知识库检索工具"""

import asyncio

from langchain_core.tools import tool


@tool
async def retrieve_knowledge(query: str, source: str = "", top_k: int = 5) -> str:
    """从知识库检索相关信息。使用语义搜索+关键词搜索混合检索运维文档、故障案例、巡检报告、API文档等。

    比 search_fault_cases 更强大：覆盖全部知识源，支持语义理解。

    Args:
        query: 搜索查询（如 "Docker 容器频繁重启怎么排查"、"nginx 配置在哪里"）
        source: 可选，限定数据源。可选值: ops-docs, api-docs, fault_case, patrol_history, compliance, agent-memory。留空搜索全部。
        top_k: 返回结果数量，默认5
    """
    from modules.agents.rag import hybrid_search

    results = await asyncio.to_thread(hybrid_search, query, top_k, source)
    if not results:
        return f'知识库中没有找到与 "{query}" 相关的信息。'
    lines = [f'## 知识检索: "{query}" ({len(results)} 条结果)\n']
    for i, r in enumerate(results, 1):
        meta = r["metadata"]
        src = meta.get("source", "unknown")
        title = meta.get("title", meta.get("file", ""))
        lines.append(f"### [{i}] [{src}] {title}")
        lines.append(r["content"][:500])
        lines.append(f"*相关度: {r['score']:.2f} | 检索方式: {r['search_type']}*\n")
    return "\n".join(lines)


@tool
async def reindex_knowledge_base() -> str:
    """手动触发知识库全量重建索引。管理员在更新了运维文档或导入新故障案例后使用。"""
    from modules.agents.rag import build_full_index

    stats = await asyncio.to_thread(build_full_index, True)
    lines = ["## 知识库重建完成\n"]
    for key, count in stats.items():
        if key not in ("total", "build_time_seconds", "skipped"):
            lines.append(f"- {key}: {count} 个文档")
    lines.append(f"\n总计: {stats.get('total', 0)} 个文档")
    lines.append(f"耗时: {stats.get('build_time_seconds', 0):.1f} 秒")
    return "\n".join(lines)

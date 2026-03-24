"""RAG 知识库 — 基于 ChromaDB + Ollama Embeddings 的混合检索系统

数据源:
  - ~/ops-docs/*.md        (运维文档)
  - docs/api/*.md          (API 文档)
  - fault_cases 表          (故障案例，FTS5 + 向量双索引)
  - agent_patrol_history 表 (巡检历史报告)
  - data/compliance_baselines.json (合规基线)
  - data/agent-memory.md   (Agent 长期记忆)

索引策略:
  - 启动时全量构建（collection 存在则跳过，除非强制重建）
  - 新增 fault_case / patrol_history 时增量索引
  - 管理员可手动触发全量重建
  - Ollama 不可用时降级为 FTS5-only 搜索
"""

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# 单例
_embeddings = None
_vectorstore = None
_last_index_stats: dict = {}
_last_index_time: float = 0


# ─── Embedding ───

def get_embeddings():
    """获取或创建 OllamaEmbeddings 单例"""
    global _embeddings
    if _embeddings is None:
        from langchain_ollama import OllamaEmbeddings
        from config import settings
        model = getattr(settings, "rag_embedding_model", "bge-m3")
        base_url = getattr(settings, "rag_ollama_url", "http://localhost:11434")
        _embeddings = OllamaEmbeddings(model=model, base_url=base_url)
        logger.info(f"OllamaEmbeddings 已创建: model={model}, url={base_url}")
    return _embeddings


# ─── Vector Store ───

def _get_persist_dir() -> str:
    from config import settings
    return str(Path(settings.db_path).parent / "chroma_db")


def get_vectorstore():
    """获取或创建 ChromaDB 向量存储单例"""
    global _vectorstore
    if _vectorstore is None:
        from langchain_chroma import Chroma
        persist_dir = _get_persist_dir()
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        _vectorstore = Chroma(
            collection_name="serverhub_knowledge",
            embedding_function=get_embeddings(),
            persist_directory=persist_dir,
        )
        logger.info(f"ChromaDB 已创建: {persist_dir}")
    return _vectorstore


def _reset_vectorstore():
    """重置向量存储单例（重建索引前调用）"""
    global _vectorstore
    _vectorstore = None


# ─── 文档分块 ───

def _split_markdown(text: str, file_path: str, source_tag: str) -> list[dict]:
    """按 Markdown 标题拆分文档，返回 [{text, metadata}, ...]"""
    from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
    from config import settings

    chunk_size = getattr(settings, "rag_chunk_size", 800)
    chunk_overlap = getattr(settings, "rag_chunk_overlap", 100)

    # 按标题层级拆分
    headers = [("#", "h1"), ("##", "h2"), ("###", "h3")]
    md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers, strip_headers=False)
    md_chunks = md_splitter.split_text(text)

    # 对过长的块进行二次拆分
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "；", " "],
    )

    results = []
    file_name = Path(file_path).name
    for chunk in md_chunks:
        content = chunk.page_content
        if len(content) > chunk_size * 1.5:
            sub_chunks = text_splitter.split_text(content)
            for i, sc in enumerate(sub_chunks):
                title = chunk.metadata.get("h2") or chunk.metadata.get("h1") or file_name
                results.append({
                    "text": sc,
                    "metadata": {
                        "source": source_tag,
                        "file": file_name,
                        "title": title,
                        "chunk_index": i,
                        **{k: v for k, v in chunk.metadata.items() if k in ("h1", "h2", "h3")},
                    },
                })
        else:
            title = chunk.metadata.get("h2") or chunk.metadata.get("h1") or file_name
            results.append({
                "text": content,
                "metadata": {
                    "source": source_tag,
                    "file": file_name,
                    "title": title,
                    **{k: v for k, v in chunk.metadata.items() if k in ("h1", "h2", "h3")},
                },
            })
    return results


# ─── 索引函数 ───

def _add_documents_to_store(docs: list[dict]) -> int:
    """批量添加文档到向量存储，返回添加数量"""
    if not docs:
        return 0
    store = get_vectorstore()
    texts = [d["text"] for d in docs]
    metadatas = [d["metadata"] for d in docs]
    # 用 source + 内容哈希作为 ID，避免重复
    import hashlib
    ids = [
        f"{d['metadata'].get('source', 'unknown')}_{hashlib.md5(d['text'][:200].encode()).hexdigest()[:12]}"
        for d in docs
    ]
    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)
    return len(docs)


def index_markdown_files(directory: str, source_tag: str) -> int:
    """索引目录下所有 Markdown 文件"""
    dir_path = Path(directory).expanduser()
    if not dir_path.is_dir():
        logger.warning(f"目录不存在，跳过索引: {directory}")
        return 0

    all_docs = []
    for md_file in sorted(dir_path.glob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
            if not text.strip():
                continue
            chunks = _split_markdown(text, str(md_file), source_tag)
            all_docs.extend(chunks)
        except Exception as e:
            logger.warning(f"索引文件失败 {md_file}: {e}")

    return _add_documents_to_store(all_docs)


def index_fault_cases_sync(db_path: str) -> int:
    """从 fault_cases 表索引故障案例（同步版本，启动时用）"""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, category, symptoms, root_cause, solution, tags "
            "FROM fault_cases ORDER BY id"
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f"fault_cases 索引失败: {e}")
        return 0

    docs = []
    for row in rows:
        text = (
            f"# {row['title']}\n\n"
            f"**分类**: {row['category'] or '未分类'}\n"
            f"**症状**: {row['symptoms'] or ''}\n"
            f"**根因**: {row['root_cause'] or ''}\n"
            f"**解决方案**: {row['solution'] or ''}\n"
            f"**标签**: {row['tags'] or ''}"
        )
        docs.append({
            "text": text,
            "metadata": {
                "source": "fault_case",
                "id": str(row["id"]),
                "title": row["title"],
                "category": row["category"] or "未分类",
            },
        })
    return _add_documents_to_store(docs)


def index_patrol_history_sync(db_path: str, limit: int = 200) -> int:
    """索引最近的巡检报告"""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, task_id, timestamp, status, report "
            "FROM agent_patrol_history ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
    except Exception as e:
        logger.warning(f"patrol_history 索引失败: {e}")
        return 0

    docs = []
    for row in rows:
        report = row["report"] or ""
        if not report.strip():
            continue
        # 截取前 1500 字符避免过长
        docs.append({
            "text": report[:1500],
            "metadata": {
                "source": "patrol_history",
                "task_id": row["task_id"],
                "title": f"巡检报告: {row['task_id']} ({row['timestamp']})",
                "status": row["status"],
            },
        })
    return _add_documents_to_store(docs)


def index_compliance_baselines() -> int:
    """索引合规基线 JSON"""
    from config import BASE_DIR
    baseline_path = BASE_DIR / "data" / "compliance_baselines.json"
    if not baseline_path.exists():
        return 0

    try:
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"compliance_baselines 加载失败: {e}")
        return 0

    docs = []
    items = data if isinstance(data, list) else data.get("baselines", data.get("checks", []))
    for item in items:
        if isinstance(item, dict):
            text = json.dumps(item, ensure_ascii=False, indent=2)
            docs.append({
                "text": text,
                "metadata": {
                    "source": "compliance",
                    "id": str(item.get("id", "")),
                    "title": item.get("name", item.get("title", "合规检查项")),
                    "severity": item.get("severity", ""),
                    "category": item.get("category", ""),
                },
            })
    return _add_documents_to_store(docs)


def index_agent_memory() -> int:
    """索引 Agent 长期记忆文件"""
    from config import BASE_DIR
    memory_path = BASE_DIR / "data" / "agent-memory.md"
    if not memory_path.exists():
        return 0
    try:
        text = memory_path.read_text(encoding="utf-8")
        if not text.strip():
            return 0
        chunks = _split_markdown(text, str(memory_path), "agent-memory")
        return _add_documents_to_store(chunks)
    except Exception as e:
        logger.warning(f"agent-memory 索引失败: {e}")
        return 0


# ─── 全量构建 ───

def build_full_index(force: bool = False) -> dict:
    """全量构建索引

    Args:
        force: True 时删除旧索引重建，False 时若 collection 已有数据则跳过

    Returns:
        {"ops_docs": N, "api_docs": N, ...} 各源文档数
    """
    global _last_index_stats, _last_index_time
    start = time.time()

    store = get_vectorstore()

    # 检查是否需要重建
    try:
        existing_count = store._collection.count()
    except Exception:
        existing_count = 0

    if existing_count > 0 and not force:
        logger.info(f"ChromaDB 已有 {existing_count} 条文档，跳过重建（使用 force=True 强制重建）")
        _last_index_stats = {"total": existing_count, "skipped": True}
        _last_index_time = time.time()
        return _last_index_stats

    # 强制重建：删除旧 collection 并重建
    if force and existing_count > 0:
        logger.info(f"强制重建：删除 {existing_count} 条旧文档...")
        try:
            import chromadb
            persist_dir = _get_persist_dir()
            client = chromadb.PersistentClient(path=persist_dir)
            client.delete_collection("serverhub_knowledge")
            _reset_vectorstore()
        except Exception as e:
            logger.warning(f"删除旧 collection 失败: {e}")
            # 尝试直接删除目录
            import shutil
            persist_dir = _get_persist_dir()
            if Path(persist_dir).exists():
                shutil.rmtree(persist_dir)
            _reset_vectorstore()

    from config import BASE_DIR

    stats = {}

    # 1. 运维文档
    try:
        stats["ops_docs"] = index_markdown_files("~/ops-docs", "ops-docs")
    except Exception as e:
        logger.warning(f"ops-docs 索引失败: {e}")
        stats["ops_docs"] = 0

    # 2. API 文档
    try:
        stats["api_docs"] = index_markdown_files(str(BASE_DIR / "docs" / "api"), "api-docs")
    except Exception as e:
        logger.warning(f"api-docs 索引失败: {e}")
        stats["api_docs"] = 0

    # 3. 故障案例
    try:
        from config import settings
        stats["fault_cases"] = index_fault_cases_sync(settings.db_path)
    except Exception as e:
        logger.warning(f"fault_cases 索引失败: {e}")
        stats["fault_cases"] = 0

    # 4. 巡检历史
    try:
        from config import settings
        stats["patrol_history"] = index_patrol_history_sync(settings.db_path)
    except Exception as e:
        logger.warning(f"patrol_history 索引失败: {e}")
        stats["patrol_history"] = 0

    # 5. 合规基线
    try:
        stats["compliance"] = index_compliance_baselines()
    except Exception as e:
        logger.warning(f"compliance 索引失败: {e}")
        stats["compliance"] = 0

    # 6. Agent 记忆
    try:
        stats["agent_memory"] = index_agent_memory()
    except Exception as e:
        logger.warning(f"agent-memory 索引失败: {e}")
        stats["agent_memory"] = 0

    stats["total"] = sum(stats.values())
    elapsed = time.time() - start
    stats["build_time_seconds"] = round(elapsed, 2)

    _last_index_stats = stats
    _last_index_time = time.time()

    logger.info(f"RAG 索引构建完成: {stats}")
    return stats


# ─── 增量索引 ───

def index_single_document(text: str, metadata: dict) -> None:
    """增量索引单个文档（新增 fault_case 或 patrol_history 时调用）"""
    try:
        _add_documents_to_store([{"text": text, "metadata": metadata}])
    except Exception as e:
        logger.warning(f"增量索引失败: {e}")


# ─── 检索 ───

def vector_search(query: str, top_k: int = 5, filter_dict: dict | None = None) -> list[dict]:
    """纯向量语义搜索"""
    store = get_vectorstore()
    kwargs = {"k": top_k}
    if filter_dict:
        kwargs["filter"] = filter_dict
    try:
        results = store.similarity_search_with_relevance_scores(query, **kwargs)
    except Exception as e:
        logger.warning(f"向量搜索失败: {e}")
        return []

    return [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": round(float(score), 4),
            "search_type": "vector",
        }
        for doc, score in results
        if score > 0.1  # 过滤低相关度
    ]


def fts5_search(query: str, top_k: int = 5) -> list[dict]:
    """FTS5 关键词搜索（复用 fault_cases_fts）"""
    import sqlite3
    from config import settings

    try:
        conn = sqlite3.connect(settings.db_path)
        conn.row_factory = sqlite3.Row
    except Exception:
        return []

    results = []
    try:
        rows = conn.execute(
            "SELECT fc.id, fc.title, fc.category, fc.symptoms, fc.root_cause, fc.solution, fc.tags, "
            "rank "
            "FROM fault_cases_fts fts JOIN fault_cases fc ON fts.rowid = fc.id "
            "WHERE fault_cases_fts MATCH ? ORDER BY rank LIMIT ?",
            (query, top_k)
        ).fetchall()

        for row in rows:
            content = (
                f"# {row['title']}\n"
                f"症状: {row['symptoms'] or ''}\n"
                f"根因: {row['root_cause'] or ''}\n"
                f"方案: {row['solution'] or ''}"
            )
            results.append({
                "content": content,
                "metadata": {
                    "source": "fault_case",
                    "id": str(row["id"]),
                    "title": row["title"],
                    "category": row["category"] or "",
                },
                "score": round(abs(float(row["rank"])), 4),  # FTS5 rank 是负数
                "search_type": "fts5",
            })
    except Exception as e:
        # FTS5 不可用时静默失败（表可能不存在）
        logger.debug(f"FTS5 搜索不可用: {e}")
    finally:
        conn.close()

    return results


def hybrid_search(query: str, top_k: int = 5, source_filter: str = "") -> list[dict]:
    """混合检索: 向量语义搜索 + FTS5 关键词搜索，结果合并去重

    Args:
        query: 搜索查询
        top_k: 返回结果数量
        source_filter: 可选，限定数据源 ("ops-docs", "api-docs", "fault_case", etc.)

    Returns:
        [{"content", "metadata", "score", "search_type"}, ...]
    """
    results = []

    # 1. 向量搜索（可能因 Ollama 不可用而失败）
    filter_dict = {"source": source_filter} if source_filter else None
    try:
        vec_results = vector_search(query, top_k=top_k, filter_dict=filter_dict)
        results.extend(vec_results)
    except Exception as e:
        logger.warning(f"向量搜索降级: {e}")

    # 2. FTS5 关键词搜索（仅搜索 fault_cases，始终可用）
    if not source_filter or source_filter == "fault_case":
        fts_results = fts5_search(query, top_k=top_k)
        results.extend(fts_results)

    # 3. 去重（基于内容前 100 字符）
    seen = set()
    unique = []
    for r in results:
        key = r["content"][:100]
        if key not in seen:
            seen.add(key)
            unique.append(r)

    # 4. 排序：向量搜索结果优先（语义匹配通常更精准），然后按分数降序
    type_priority = {"vector": 0, "fts5": 1}
    unique.sort(key=lambda r: (type_priority.get(r["search_type"], 2), -r["score"]))

    return unique[:top_k]


# ─── 统计信息 ───

def get_index_stats() -> dict:
    """返回索引统计信息（供前端面板和 API）

    返回格式（匹配前端 agents.html 期望字段）:
        status: "ready" | "building" | "error"
        total_docs: int
        storage_mb: float
        embedding_model: str
        last_indexed: str (ISO 时间)
        sources: {source_tag: count, ...}
    """
    raw = dict(_last_index_stats) if _last_index_stats else {}

    # 获取当前 collection 的实际文档数
    try:
        store = get_vectorstore()
        current_count = store._collection.count()
    except Exception:
        current_count = 0

    # 存储大小
    persist_dir = Path(_get_persist_dir())
    if persist_dir.exists():
        total_size = sum(f.stat().st_size for f in persist_dir.rglob("*") if f.is_file())
        storage_mb = round(total_size / 1024 / 1024, 2)
    else:
        storage_mb = 0

    # 各数据源统计
    source_keys = ("ops_docs", "api_docs", "fault_cases", "patrol_history", "compliance", "agent_memory")
    sources = {k: raw.get(k, 0) for k in source_keys if raw.get(k, 0) > 0}

    # 上次索引时间
    last_indexed = ""
    if _last_index_time > 0:
        from datetime import datetime
        last_indexed = datetime.fromtimestamp(_last_index_time).strftime("%Y-%m-%d %H:%M:%S")

    # Embedding 模型
    try:
        embedding_model = getattr(get_embeddings(), "model", "unknown")
    except Exception:
        embedding_model = "unknown"

    return {
        "status": "ready" if current_count > 0 else ("error" if raw.get("skipped") is None and not raw else "ready"),
        "total_docs": current_count,
        "storage_mb": storage_mb,
        "embedding_model": embedding_model,
        "last_indexed": last_indexed,
        "sources": sources,
        "build_time_seconds": raw.get("build_time_seconds", 0),
    }

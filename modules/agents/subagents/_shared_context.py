"""SubAgent 共享上下文 — 通过 AsyncSqliteStore 在 SubAgent 间传递发现

解决问题: 多个异步 SubAgent 无法共享中间发现（如 security-auditor 发现的异常端口
无法传递给 correlation-analyzer）。

使用 AsyncSqliteStore (data/agent-store.db) 作为通信桥，
namespace=("shared_findings", conversation_id) 隔离不同对话。
"""

import json
import logging
import time
from contextvars import ContextVar

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 当前对话 ID — 由 chat 路由在调用前设置
_current_conversation_id: ContextVar[str] = ContextVar("shared_ctx_conversation_id", default="default")


def set_conversation_id(conversation_id: str) -> None:
    """设置当前对话 ID（由 chat 路由调用）"""
    _current_conversation_id.set(conversation_id)


def _get_store():
    """获取 AsyncSqliteStore 单例（复用 deep_agent 中的实例）"""
    from modules.agents.deep_agent import _store

    if _store is None:
        logger.warning("AsyncSqliteStore 尚未初始化，共享上下文不可用")
    return _store


def _namespace() -> tuple[str, str]:
    """返回当前对话的 namespace"""
    return ("shared_findings", _current_conversation_id.get())


@tool
async def share_finding(category: str, summary: str, details: str = "") -> str:
    """将发现写入共享上下文，供其他 SubAgent 读取。

    Args:
        category: 分类，如 security, performance, network, docker, service, user
        summary: 一句话摘要，描述发现的核心内容
        details: 可选的详细信息，如具体端口号、进程名、日志片段等
    """
    store = _get_store()
    if store is None:
        return "Error: 共享存储未就绪，发现未保存"

    namespace = _namespace()
    key = f"{category}_{int(time.time() * 1000)}"
    value = {
        "category": category,
        "summary": summary,
        "details": details,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        await store.aput(namespace, key, value)
        logger.info("共享发现已写入: ns=%s, key=%s, category=%s", namespace, key, category)
        return f"已共享发现 [{category}]: {summary}"
    except Exception as e:
        logger.error("写入共享发现失败: %s", e)
        return f"Error: 写入失败 — {e}"


@tool
async def read_shared_findings(category: str = "") -> str:
    """读取其他 SubAgent 共享的发现。

    Args:
        category: 可选，按分类过滤（如 security, performance）。留空返回所有发现。
    """
    store = _get_store()
    if store is None:
        return "共享存储未就绪，无可用发现"

    namespace = _namespace()

    try:
        items = await store.alist(namespace)
        if not items:
            return "当前对话中尚无共享发现"

        findings = []
        for _key, item in items:
            value = item if isinstance(item, dict) else json.loads(item) if isinstance(item, str) else {}
            # LangGraph store item 可能包装在 .value 属性中
            if hasattr(item, "value"):
                value = item.value
            if category and value.get("category") != category:
                continue
            findings.append(value)

        if not findings:
            return f"未找到分类为 '{category}' 的共享发现"

        output = f"共享发现 ({len(findings)} 条):\n"
        for i, f in enumerate(findings, 1):
            output += f"\n[{i}] [{f.get('category', '?')}] {f.get('summary', '?')}"
            if f.get("details"):
                output += f"\n    详情: {f['details']}"
            if f.get("timestamp"):
                output += f"\n    时间: {f['timestamp']}"
        return output
    except Exception as e:
        logger.error("读取共享发现失败: %s", e)
        return f"Error: 读取失败 — {e}"

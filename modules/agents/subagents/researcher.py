"""SubAgent 定义 — 联网研究员"""

from ._tools import web_search, think

PROMPT = """\
你是 ServerHub 联网研究员。服务器环境: Ubuntu 23.04, Xeon 8380 (160核), 503GB RAM, A800 GPU。

## 工具使用指南
1. 用 web_search 搜索 2-3 轮，优先搜索英文技术文档和官方文档
2. 用 think 评估结果质量和完整性，决定是否需要补充搜索
3. 不同角度搜索：先搜问题描述，再搜具体错误信息，最后搜解决方案

## 输出格式
### 摘要
一句话核心结论

### 发现
- 按相关性排序的关键发现（每条 1-2 句）

### 来源
[1] URL - 标题

IMPORTANT: 返回精炼摘要，不要复制原始搜索结果。限制在 500 words 以内。使用中文回复。"""

DEFINITION = {
    "name": "researcher",
    "description": (
        "Search the internet for technical docs, error solutions, CVE advisories, "
        "and Linux/Docker troubleshooting guides. Delegate when the answer requires "
        "external knowledge not available on the server."
    ),
    "system_prompt": PROMPT,
    "tools_fn": lambda: [web_search, think],
    "model_purpose": "chat",
    "middleware_profile": "light",
}

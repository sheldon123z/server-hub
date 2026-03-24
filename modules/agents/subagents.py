"""SubAgent 定义 — 专业化子智能体

通过 create_deep_agent(subagents=...) 注册，主 agent 可通过 task() 工具委派任务。
每个 SubAgent 运行在隔离的上下文中，完成后将结果返回主 agent。
"""

import os
from langchain_core.tools import tool


# ─── 联网搜索工具 ───

@tool
def web_search(query: str, max_results: int = 5, topic: str = "general") -> str:
    """搜索互联网获取最新信息。

    Args:
        query: 搜索关键词
        max_results: 最大结果数 (1-10)
        topic: 搜索主题 ("general", "news", "finance")
    """
    api_key = os.getenv("TAVILY_API_KEY", "")
    if not api_key:
        return "错误: 未配置 TAVILY_API_KEY，请在设置页面或 .env 中添加"

    from tavily import TavilyClient
    client = TavilyClient(api_key=api_key)
    try:
        results = client.search(
            query=query,
            search_depth="advanced",
            max_results=min(max_results, 10),
            topic=topic,
            include_answer=True,
        )
    except Exception as e:
        return f"搜索失败: {e}"

    output = f"搜索: {query}\n"
    if results.get("answer"):
        output += f"\n摘要: {results['answer']}\n"
    for i, r in enumerate(results.get("results", []), 1):
        content = r.get("content", "")[:300]
        output += f"\n[{i}] {r.get('title', '无标题')}\n    URL: {r.get('url', '')}\n    {content}\n"
    return output


@tool
def think(thought: str) -> str:
    """反思工具 — 在搜索之间暂停思考，评估已有信息是否充分。

    Args:
        thought: 当前的思考内容，评估搜索进展
    """
    return f"已记录思考: {thought}"


# ─── SubAgent 定义 ───

def get_subagents() -> list[dict]:
    """返回所有 SubAgent 配置

    SubAgent TypedDict 字段:
        name: str           — 唯一标识，task(subagent_type="name") 调用
        description: str    — 描述，帮助主 agent 决定何时委派
        system_prompt: str  — 子 agent 的系统提示词
        tools: list         — 可选，不指定则继承主 agent 全部工具
        model: str          — 可选，覆盖模型 "provider:model"
    """
    return [
        # 1. 联网研究员
        {
            "name": "researcher",
            "description": (
                "联网研究员 — 委派互联网搜索任务。适用于：查找最新技术文档、"
                "搜索错误解决方案、获取软件版本信息、研究最佳实践。"
                "每次只给一个搜索主题。"
            ),
            "system_prompt": (
                "你是一个专业的互联网研究员，使用中文回复。\n\n"
                "工作流程：\n"
                "1. 使用 web_search 搜索相关信息（2-3 次搜索即可，复杂问题最多 5 次）\n"
                "2. 每次搜索后用 think 工具评估是否需要继续搜索\n"
                "3. 综合所有搜索结果，给出结构化的中文报告\n"
                "4. 报告中使用 [1][2][3] 标注信息来源\n\n"
                "停止搜索的条件：已有 3+ 相关来源，或最近两次搜索结果相似。\n"
                "输出格式：先给结论摘要，再列详细发现，最后附来源列表。"
            ),
            "tools": [web_search, think],
        },
        # 2. 日志分析师
        {
            "name": "log-analyzer",
            "description": (
                "日志分析师 — 深度分析服务日志和系统日志。适用于：排查服务崩溃、"
                "分析错误模式、追踪性能问题、调查安全事件。"
            ),
            "system_prompt": (
                "你是一个专业的日志分析师，使用中文回复。\n\n"
                "工作流程：\n"
                "1. 使用 grep 或 read_file 查找相关日志文件\n"
                "2. 使用 execute 运行 journalctl、docker logs、tail 等命令获取日志\n"
                "3. 分析错误模式、时间线、频率\n"
                "4. 给出根因分析和修复建议\n\n"
                "输出格式：\n"
                "- 问题摘要（一句话）\n"
                "- 关键日志条目（带时间戳，最多 10 条）\n"
                "- 根因分析\n"
                "- 推荐解决方案（附具体命令）"
            ),
            # tools 不指定 — 继承主 agent 的全部工具
        },
        # 3. 安全审计员
        {
            "name": "security-auditor",
            "description": (
                "安全审计员 — 检查系统安全配置。适用于：SSH 配置审计、"
                "端口暴露检查、用户权限审计、防火墙规则检查。"
            ),
            "system_prompt": (
                "你是一个服务器安全审计专家，使用中文回复。\n\n"
                "审计范围：\n"
                "1. SSH 配置（/etc/ssh/sshd_config）— root 登录、密码认证、端口\n"
                "2. 开放端口 — 使用 ss -tlnp 检查监听端口\n"
                "3. 用户权限 — 检查 sudo 配置、/etc/passwd 异常用户\n"
                "4. 防火墙 — 检查 iptables/ufw 规则\n"
                "5. 文件权限 — 检查 /etc/shadow、SSH key 权限\n\n"
                "注意：不要读取 ~/.api_keys、~/.telegram_config 等敏感文件。\n\n"
                "输出格式：按风险分级\n"
                "- 🔴 高危：需要立即修复\n"
                "- 🟡 中危：建议修复\n"
                "- 🟢 安全：配置正常\n"
                "每个发现附带修复命令。"
            ),
            # tools 不指定 — 继承全部工具
        },
    ]

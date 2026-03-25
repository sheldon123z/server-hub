"""SubAgent 定义 — 专业化子智能体

遵循 LangChain 官方 SubAgent 规范 (https://docs.langchain.com/oss/python/deepagents/subagents):
- name/description/system_prompt/tools 四个 Required 字段必须显式指定
- tools 保持 minimal 集合
- system_prompt 包含输出格式和长度限制
- description 具体且 action-oriented

Per-SubAgent 高级配置 (https://docs.langchain.com/oss/python/deepagents/context-engineering):
- model: 按任务复杂度分配不同成本的模型
- middleware: 重试策略和调用次数限制
- interrupt_on: 危险操作审批拦截
"""

import json
import logging
import os
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# ─── SubAgent 专属工具 ───

_tavily_client = None


def _get_tavily_client():
    global _tavily_client
    if _tavily_client is None:
        api_key = os.getenv("TAVILY_API_KEY", "")
        if not api_key:
            return None
        from tavily import TavilyClient
        _tavily_client = TavilyClient(api_key=api_key)
    return _tavily_client


@tool
def web_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
) -> str:
    """Search the web for up-to-date information on any topic."""
    client = _get_tavily_client()
    if client is None:
        return "Error: TAVILY_API_KEY not configured"
    try:
        results = client.search(
            query=query,
            search_depth="advanced",
            max_results=min(max_results, 10),
            topic=topic,
            include_answer=True,
        )
    except Exception as e:
        return f"Search failed: {e}"

    output = f"Search: {query}\n"
    if results.get("answer"):
        output += f"\nSummary: {results['answer']}\n"
    for i, r in enumerate(results.get("results", []), 1):
        content = r.get("content", "")[:300]
        output += f"\n[{i}] {r.get('title', 'Untitled')}\n    URL: {r.get('url', '')}\n    {content}\n"
    return output


@tool
def think(thought: str) -> str:
    """Pause and reflect on research progress before deciding next steps."""
    return f"Reflected: {thought}"


# ─── 需要从主 agent 工具集中引用的工具 ───

def _get_tools_by_names(names: list[str]) -> list:
    """从主 agent 的工具集中按名称提取工具对象"""
    from modules.agents.tools import get_server_tools
    server_tools = {t.name: t for t in get_server_tools()}
    result = []
    for name in names:
        if name in server_tools:
            result.append(server_tools[name])
        elif name in TOOL_REGISTRY:
            result.append(TOOL_REGISTRY[name])
    return result


# ─── Per-SubAgent Middleware 配置 ───

def _build_subagent_middleware(profile: str) -> list:
    """根据 profile 构建 SubAgent 专属 middleware 栈

    Args:
        profile: "heavy"(工具密集) / "light"(轻量) / "ops"(操作型)
    """
    from langchain.agents.middleware import (
        ModelRetryMiddleware,
        ToolRetryMiddleware,
        ModelCallLimitMiddleware,
    )

    if profile == "heavy":
        return [
            ModelRetryMiddleware(max_retries=2, backoff_factor=1.0),
            ToolRetryMiddleware(max_retries=2, backoff_factor=1.0),
            ModelCallLimitMiddleware(run_limit=30),
        ]
    elif profile == "light":
        return [
            ModelRetryMiddleware(max_retries=2, backoff_factor=1.0),
            ModelCallLimitMiddleware(run_limit=15),
        ]
    else:  # ops
        return [
            ModelRetryMiddleware(max_retries=2, backoff_factor=1.0),
            ToolRetryMiddleware(max_retries=1, backoff_factor=1.0),
            ModelCallLimitMiddleware(run_limit=20),
        ]


def _get_subagent_model(purpose: str):
    """获取 SubAgent 模型实例，失败返回 None（由框架回退到主模型）"""
    try:
        from modules.agents.llm import get_chat_model
        return get_chat_model(purpose)
    except Exception:
        return None


# ─── SubAgent 提示词 ───

RESEARCHER_PROMPT = """\
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

LOG_ANALYZER_PROMPT = """\
你是 ServerHub 日志分析专家。分析服务日志以诊断崩溃、错误模式和性能问题。

## 服务器上下文
- 关键服务: nginx, docker, clash, ollama, jupyterlab, mysql, fail2ban
- Docker 堆栈: Dify (docker-worker-1 有已知重启问题), LobeChat, Grid AutoPilot
- 日志路径: systemd journal, Docker 容器日志

## 工具使用指南
1. 先用 get_container_logs / get_service_logs 获取相关日志（指定 tail 行数）
2. 关注: ERROR/FATAL/CRITICAL 级别、OOM Kill、segfault、连接拒绝、超时
3. 时间线分析: 关联多个服务的错误时间戳，定位首发故障点

## 输出格式
### 诊断结论
一句话根因判断

### 错误模式
- 错误类型 | 频率 | 首次/末次出现时间

### 根因分析
按证据链推导根因

### 建议
优先级排序的修复步骤

IMPORTANT: 返回结构化诊断报告，不要粘贴大段原始日志。限制在 500 words 以内。使用中文回复。"""

SECURITY_AUDITOR_PROMPT = """\
你是 ServerHub 安全审计专家。审计 Linux 服务器安全配置。

## 审计范围
- SSH: 密钥认证、root 登录禁用、端口配置、协议版本
- 网络: 防火墙规则、开放端口、fail2ban 状态
- 用户: 权限分离、sudo 配置、密码策略、students 组资源限制
- 文件: 敏感文件权限（.api_keys, .telegram_config, config.yaml 不应全局可读）
- 服务: 不必要的外部暴露服务、Docker daemon 安全

## 工具使用指南
- 用 get_system_overview 获取系统全貌，用 check_compliance 执行 CIS Benchmark 检查
- 重点关注: 外部可访问端口、默认/弱凭据、未加密通信、过时软件

## 输出格式
### 安全评分
X/10 综合评分

### 发现（按严重程度排序）
- [CRITICAL/HIGH/MEDIUM/LOW] 问题描述 → 修复建议

### 合规状态
CIS Benchmark 关键项达标情况概要

IMPORTANT: 返回精炼审计报告，不是原始命令输出。限制在 500 words 以内。使用中文回复。"""

CORRELATION_ANALYZER_PROMPT = """\
你是 ServerHub 多源关联分析专家。跨维度关联系统指标、日志、容器、用户行为以定位复杂问题根因。

## 分析方法论（按顺序执行）
1. 资源层: analyze_resource_trend → 识别趋势异常点和转折时间
2. 系统层: get_system_overview → 获取当前状态作为基线
3. 容器层: list_docker_containers + get_container_logs → 容器健康和错误日志
4. 服务层: list_systemd_services + get_service_logs → 服务状态和依赖链
5. 用户层: get_active_sessions_tool + get_user_login_history_tool → 用户行为时间线
6. 网络层: list_docker_networks + get_service_dependencies_tool → 网络拓扑和依赖
7. 历史层: search_fault_cases → 匹配历史相似案例

## 关联规则
- 时间关联: 多个异常在同一时间窗口(±5min)出现 → 可能共因
- 资源关联: CPU/内存峰值 + 服务异常 → 资源竞争
- 依赖关联: 上游服务故障 → 级联影响下游服务

## 输出格式
### 根因判断
一句话根因 + 置信度(高/中/低)

### 关联证据链
时间线 → 各维度关键证据 → 逻辑推导

### 影响范围
受影响的组件和服务列表

### 处置建议
紧急措施 → 短期修复 → 长期优化

IMPORTANT: 综合分析后返回精炼结论，不要罗列原始数据。限制在 500 words 以内。使用中文回复。"""

OPS_SCHEDULER_PROMPT = """\
你是 ServerHub 定时任务管理专家。管理和优化 cron 定时任务。

## 服务器上下文
- 现有关键 cron: 每日早报(8:00), 内存紧急释放(每5min), 健康检查(每12h), GPU监控(每1h)
- 脚本中心: ~/scripts/ (monitoring/, notification/, docker/, resource-control/)
- 避免冲突: 不要与现有高频任务在同一分钟运行

## 工具使用流程
1. list_cron_jobs → 查看现有任务，确认无冲突
2. validate_cron_expr → 验证 cron 表达式正确性
3. create_cron_job / modify_cron_schedule → 执行变更
4. 变更后再次 list_cron_jobs 确认结果

## 安全规则
- 脚本路径必须使用绝对路径
- 不允许创建频率高于每分钟的任务
- 删除前确认任务不被其他脚本依赖

## 输出格式
### 执行摘要
完成了什么操作

### 变更详情
旧配置 → 新配置

### 验证结果
确认任务已生效

IMPORTANT: 返回操作摘要，不要输出完整 crontab 内容。限制在 500 words 以内。使用中文回复。"""

KNOWLEDGE_RETRIEVER_PROMPT = """\
你是 ServerHub 知识检索专家。多策略检索本地知识库和互联网信息回答运维问题。

## 检索策略（按优先级）
1. 语义检索: retrieve_knowledge → 本地运维文档和知识库
2. 案例匹配: search_fault_cases → 历史故障案例库，匹配相似问题
3. 补充搜索: web_search → 仅在本地无结果或需要最新信息时使用
4. 反思评估: think → 评估已收集信息的完整性，决定是否补充检索

## 输出格式
### 答案
直接回答查询问题（简明扼要）

### 来源
- [本地知识库/历史案例/互联网] 信息来源标注

### 相关案例
匹配的历史故障案例摘要（如有）

IMPORTANT: 综合多源信息给出精炼答案，本地知识优先。限制在 500 words 以内。使用中文回复。"""


# ─── SubAgent 定义 ───

def get_subagents() -> list[dict]:
    """返回所有 SubAgent 配置（含 per-subagent model/middleware/interrupt_on）"""
    chat_model = _get_subagent_model("chat")
    patrol_model = _get_subagent_model("patrol")

    return [
        # 1. 联网研究员 — 搜索策略需要强推理，用 chat 模型
        {
            "name": "researcher",
            "description": (
                "Search the internet for technical docs, error solutions, CVE advisories, "
                "and Linux/Docker troubleshooting guides. Delegate when the answer requires "
                "external knowledge not available on the server."
            ),
            "system_prompt": RESEARCHER_PROMPT,
            "tools": [web_search, think],
            "model": chat_model,
            "middleware": _build_subagent_middleware("light"),
        },
        # 2. 日志分析师 — 模式匹配为主，用 patrol 模型
        {
            "name": "log-analyzer",
            "description": (
                "Diagnose service crashes and error patterns by analyzing Docker container logs "
                "and systemd service logs. Delegate for any log-based investigation."
            ),
            "system_prompt": LOG_ANALYZER_PROMPT,
            "tools": _get_tools_by_names(["get_container_logs", "get_service_logs"]),
            "model": patrol_model,
            "middleware": _build_subagent_middleware("heavy"),
        },
        # 3. 安全审计员 — 结构化审计，用 patrol 模型
        {
            "name": "security-auditor",
            "description": (
                "Audit SSH, firewall, user permissions, open ports, and file permissions "
                "against security baselines. Delegate for security assessments and compliance checks."
            ),
            "system_prompt": SECURITY_AUDITOR_PROMPT,
            "tools": _get_tools_by_names(["get_system_overview", "check_compliance"]),
            "model": patrol_model,
            "middleware": _build_subagent_middleware("ops"),
        },
        # 4. 多源关联分析 — 复杂多维推理，用 chat 模型
        {
            "name": "correlation-analyzer",
            "description": (
                "Correlate system metrics, container health, service logs, user activity, "
                "and network topology to find root causes of complex multi-component failures. "
                "Delegate for hard-to-diagnose issues involving multiple subsystems."
            ),
            "system_prompt": CORRELATION_ANALYZER_PROMPT,
            "tools": _get_tools_by_names([
                "analyze_resource_trend", "get_system_overview",
                "list_docker_containers", "get_container_logs",
                "list_systemd_services", "get_service_logs",
                "search_fault_cases", "get_user_login_history_tool",
                "get_active_sessions_tool", "list_docker_networks",
                "get_service_dependencies_tool",
            ]),
            "model": chat_model,
            "middleware": _build_subagent_middleware("heavy"),
        },
        # 5. 定时任务调度专家 — 结构化 CRUD + 写操作需审批
        {
            "name": "ops-scheduler",
            "description": (
                "Create, modify, delete, and validate cron scheduled tasks with conflict checking "
                "and safety rules. Delegate for any cron task management."
            ),
            "system_prompt": OPS_SCHEDULER_PROMPT,
            "tools": _get_tools_by_names([
                "list_cron_jobs", "validate_cron_expr",
                "create_cron_job", "modify_cron_schedule",
                "delete_cron_job_tool", "toggle_cron_job_tool",
            ]),
            "model": patrol_model,
            "middleware": _build_subagent_middleware("ops"),
            "interrupt_on": {
                "create_cron_job": True,
                "delete_cron_job_tool": True,
            },
        },
        # 6. 知识检索专家 — 检索+综合，用 patrol 模型
        {
            "name": "knowledge-retriever",
            "description": (
                "Search local knowledge base, historical fault cases, and internet for "
                "operational knowledge and troubleshooting references. Delegate for "
                "best-practice lookups and historical case matching."
            ),
            "system_prompt": KNOWLEDGE_RETRIEVER_PROMPT,
            "tools": _get_tools_by_names([
                "retrieve_knowledge", "search_fault_cases",
            ]) + [web_search, think],
            "model": patrol_model,
            "middleware": _build_subagent_middleware("light"),
        },
    ]


TOOL_REGISTRY = {
    "web_search": web_search,
    "think": think,
}


# ─── Middleware profile 名称映射（用于配置持久化） ───

MIDDLEWARE_PROFILES = {"heavy", "light", "ops"}


def _build_subagents_from_config(configs: list[dict]) -> list[dict]:
    """从 JSON 配置重建 SubAgent 对象列表"""
    result = []
    for cfg in configs:
        agent_def = {
            "name": cfg["name"],
            "description": cfg["description"],
            "system_prompt": cfg["system_prompt"],
        }
        # 工具
        tool_names = cfg.get("tools", [])
        if tool_names:
            agent_def["tools"] = _get_tools_by_names(tool_names)
        # 模型 — 按 purpose 获取实例
        model_purpose = cfg.get("model_purpose")
        if model_purpose:
            model = _get_subagent_model(model_purpose)
            if model:
                agent_def["model"] = model
        # Middleware — 按 profile 构建
        mw_profile = cfg.get("middleware_profile")
        if mw_profile and mw_profile in MIDDLEWARE_PROFILES:
            agent_def["middleware"] = _build_subagent_middleware(mw_profile)
        # interrupt_on
        interrupt_on = cfg.get("interrupt_on")
        if interrupt_on:
            agent_def["interrupt_on"] = interrupt_on
        result.append(agent_def)
    return result


def load_subagents() -> list[dict]:
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    if custom_path.exists():
        try:
            configs = json.loads(custom_path.read_text(encoding="utf-8"))
            return _build_subagents_from_config(configs)
        except Exception as e:
            logger.warning(f"自定义 SubAgent 配置加载失败: {e}")
    return get_subagents()


# ─── 模型 purpose 反向映射（从模型实例推断 purpose） ───

_MODEL_PURPOSE_MAP = {
    "researcher": "chat",
    "log-analyzer": "patrol",
    "security-auditor": "patrol",
    "correlation-analyzer": "chat",
    "ops-scheduler": "patrol",
    "knowledge-retriever": "patrol",
}

_MIDDLEWARE_PROFILE_MAP = {
    "researcher": "light",
    "log-analyzer": "heavy",
    "security-auditor": "ops",
    "correlation-analyzer": "heavy",
    "ops-scheduler": "ops",
    "knowledge-retriever": "light",
}


def save_subagents_config(configs: list[dict]):
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    custom_path.parent.mkdir(parents=True, exist_ok=True)
    serializable = []
    for cfg in configs:
        name = cfg["name"]
        serializable.append({
            "name": name,
            "description": cfg["description"],
            "system_prompt": cfg["system_prompt"],
            "tools": [t.name if hasattr(t, 'name') else str(t) for t in cfg.get("tools", [])],
            "model_purpose": cfg.get("model_purpose", _MODEL_PURPOSE_MAP.get(name)),
            "middleware_profile": cfg.get("middleware_profile", _MIDDLEWARE_PROFILE_MAP.get(name)),
            "interrupt_on": cfg.get("interrupt_on"),
        })
    custom_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def get_subagents_config() -> list[dict]:
    """返回可序列化的 SubAgent 配置（供 admin API 使用）"""
    from config import settings
    custom_path = Path(settings.db_path).parent / "custom_subagents.json"
    if custom_path.exists():
        try:
            return json.loads(custom_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    defaults = get_subagents()
    return [
        {
            "name": d["name"],
            "description": d["description"],
            "system_prompt": d["system_prompt"],
            "tools": [t.name for t in d.get("tools", [])],
            "model_purpose": _MODEL_PURPOSE_MAP.get(d["name"]),
            "middleware_profile": _MIDDLEWARE_PROFILE_MAP.get(d["name"]),
            "interrupt_on": d.get("interrupt_on"),
        }
        for d in defaults
    ]


def get_available_tools() -> list[dict]:
    from modules.agents.tools import get_server_tools
    from modules.agents.safety import TOOL_RISK_MAP
    tools = []
    for t in get_server_tools():
        tools.append({
            "name": t.name,
            "description": (t.description or "")[:100],
            "risk": TOOL_RISK_MAP.get(t.name, "safe"),
            "source": "custom",
        })
    for name, t in TOOL_REGISTRY.items():
        tools.append({"name": name, "description": (t.description or "")[:100], "risk": "safe", "source": "subagent"})
    builtins = [("execute","danger"),("read_file","safe"),("write_file","moderate"),
                ("edit_file","moderate"),("ls","safe"),("glob","safe"),("grep","safe")]
    for name, risk in builtins:
        tools.append({"name": name, "description": f"内置: {name}", "risk": risk, "source": "builtin"})
    return tools

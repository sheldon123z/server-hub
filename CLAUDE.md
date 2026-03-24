# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

ServerHub 是一个基于 FastAPI 的 Linux 服务器全功能 Web 管理系统，集成了 AI 运维智能体。面向实验室/团队场景，提供系统监控、Docker/服务管理、用户资源控制、AI 自动巡检等能力。

**技术栈**: FastAPI + Jinja2 + HTMX + Alpine.js + SQLite(aiosqlite) + Deep Agents(LangGraph) + xterm.js

## 运行与开发

```bash
# 环境: 必须使用 serverhub conda 环境 (Python 3.11)，deepagents 不兼容 3.10
conda activate serverhub

# 开发模式 (自动重载)
python main.py
# 或
uvicorn main:app --host 0.0.0.0 --port 9900 --reload --workers 1

# 生产部署 (systemd)
sudo cp server-hub.service /etc/systemd/system/
sudo systemctl enable --now server-hub
```

**workers 必须为 1** — SQLite 不支持多进程写入，且 agent checkpoint 需要单进程内存一致性。

## 核心架构

### 模块自发现机制

`modules/__init__.py` 在启动时扫描 `modules/*/` 子目录，每个模块通过 `__init__.py` 导出：

```python
from modules.xxx.routes import router  # FastAPI APIRouter

MODULE_INFO = {
    "name": "xxx",              # 路由前缀标识
    "display_name": "模块名",    # 侧边栏显示
    "icon": "icon-name",        # Tabler Icons 名称
    "category": "分类",          # 侧边栏分组
    "required_role": "admin",   # "admin" 或 "user"
    "order": 10,                # 侧边栏排序
}
```

`main.py` 的 `lifespan` 中调用 `discover_modules()` 自动注册所有 router。新增模块只需创建 `modules/新模块/` 目录并导出 `MODULE_INFO` + `router`。

### 页面渲染模式

页面路由在 `main.py` 中直接定义（非模块 router）。每个页面使用 `_page_context()` 构建渲染上下文，包含 `user`、`sidebar_items`、`active_module`。

模板继承链: `base.html` → 各页面。`base.html` 包含侧边栏、顶栏、暗色主题 CSS 变量。交互模式：
- **HTMX**: 局部刷新（仪表盘卡片、Docker 状态）
- **Alpine.js**: 客户端交互逻辑（对话、Cron 编辑、设置页面）

### AI 智能体架构 (modules/agents/)

基于 **Deep Agents 框架**，通过 `create_deep_agent()` 构建：

```
deep_agent.py   → 工厂函数，组装 model + tools + backend + middleware + subagents + memory + store
llm.py          → 8 家 LLM 服务商注册表，parse_model_id("provider:model")
tools.py        → 37 个 @tool 服务器管理工具（只读 + 操作 + 危险三级）
subagents.py    → 5 个 SubAgent 定义 + web_search/think 工具 + 配置序列化
safety.py       → build_interrupt_config() 生成审批规则 + Shell 黑名单
sandbox.py      → SafeLocalShellBackend（继承 LocalShellBackend，剥离敏感环境变量 + ulimit 资源限制）
prompts.py      → 系统提示词 + get_system_prompt() 优先读自定义文件
patrol.py       → 6 个内置巡检任务 + asyncio 调度循环（每 60s 检查）
routes.py       → SSE 对话流 + 审批 + 巡检 + 设置 + 管理 API + WebSocket 终端
terminal.py     → pty.fork() WebTerminal 类
```

**Backend**: `SafeLocalShellBackend(root_dir=~)` — 继承 `LocalShellBackend`，剥离 `*API_KEY*`/`*SECRET*`/`*TOKEN*` 环境变量，沙箱目录 `/tmp/serverhub-sandbox/` 内执行自动添加 ulimit 资源限制。

**SubAgent 系统** (遵循 LangChain 官方规范):
- `researcher` — 联网搜索（Tavily），tools: `[web_search, think]`
- `log-analyzer` — 日志分析，tools: `[get_container_logs, get_service_logs]`
- `security-auditor` — 安全审计，tools: `[get_system_overview]`
- `correlation-analyzer` — 多源关联分析（11 个工具），跨维度定位根因
- `ops-scheduler` — 定时任务管理（6 个 cron 工具），创建/修改/删除/启禁 cron 任务
- 创建新 SubAgent 需遵循 `/create-subagent` skill 的 checklist

**Middleware 栈** (12 个):
- 框架自动: TodoList, Filesystem, SubAgent, Summarization, PatchToolCalls, AnthropicPromptCaching, HumanInTheLoop, Memory
- 手动注入: ModelRetry(3次), ToolRetry(2次), ModelCallLimit(chat:50/patrol:100), ContextEditing(60K token), [ModelFallback]

**记忆系统**:
- 短期: `AsyncSqliteSaver` checkpoint（per-conversation state）
- 长期: `data/agent-memory.md` + `MemoryMiddleware`（agent 通过 edit_file 自动更新）
- 结构化: `AsyncSqliteStore`（namespace+key-value → `data/agent-store.db`）

**内置工具** (由 middleware 注入): `execute`, `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`, `write_todos`, `task`。

**SSE 事件类型**: `message`, `tool_call`, `tool_result`, `todo_update`, `approval_request`, `done`, `error`。

**模型 ID 格式**: `provider:model_name`，如 `openrouter:deepseek/deepseek-chat`。所有服务商通过 OpenAI 兼容 API 统一接入 `ChatOpenAI`。

### 认证系统 (auth/)

JWT Cookie 认证 + RBAC。`access_token` 存于 HttpOnly Cookie。角色: `admin`(完全控制) / `user`(只读监控)。

依赖注入: `get_current_user` (验证登录), `require_role("admin")` (验证角色)。

### 脚本桥接 (scripts_bridge/)

`registry.py` 白名单注册可执行的运维脚本，`executor.py` 提供沙箱化执行。AI agent 的 `execute_ops_script` 工具通过此桥接调用预定义脚本。

### 管理面板 (agents.html 第四标签页「管理」)

通过 `/api/agents/admin/*` 端点管理 agent 配置，无需重启服务：
- `GET/PUT /api/agents/admin/prompt` — 系统提示词（持久化到 `data/custom_prompt.txt`）
- `GET/PUT /api/agents/admin/subagents` — SubAgent 配置 + 可用工具 + 供应商列表（持久化到 `data/custom_subagents.json`）
- `GET/PUT /api/agents/admin/memory` — `data/agent-memory.md` 运行时长期记忆
- 巡检提示词/工具/间隔通过 `PUT /api/agents/patrols/{id}` 扩展字段修改

保存后调用 `reset_agent_cache()` 使新配置在下次对话生效。

### 前端布局 (agents.html)

三栏统一布局: `侧边栏(180px) | 聊天(1fr, 始终可见) | 右栏(1fr, 按标签切换)`
- 标签页: [巡检] [管理]，终端通过聊天头部按钮调出
- 快捷指令: 输入 `/` 弹出菜单（10 个内置指令，模糊搜索 + 键盘导航）
- Todo 面板: 进度条 + 脉冲动画 + 完成闪绿
- 自主模式切换: 页内 modal 确认弹窗

### 数据库

三个 SQLite 数据库:
- `data/server-hub.db` — 应用数据（用户、审计、指标、通知、agent 对话/审批/巡检、告警规则/历史、巡检模板）
- `data/agent-checkpoints.db` — LangGraph checkpoint（agent 会话状态持久化）
- `data/agent-store.db` — AsyncSqliteStore（agent 结构化长期存储）

表结构在 `database.py:init_tables()` 中定义，应用启动时自动创建。新增表: `alert_rules`, `alert_history`, `patrol_templates`, `cron_job_log`。

### 四大管理模块能力

| 模块 | 路径 | Web 管理能力 | AI 工具能力 |
|------|------|------------|-----------|
| 用户管理 | `modules/users/` | 资源监控 + 配额管理 + 用户增删改 + 登录历史 + 单进程 kill | `manage_linux_user`, `get_user_login_history_tool`, `get_active_sessions_tool`, `kill_single_process_tool` |
| Docker | `modules/docker/` | 容器/堆栈/镜像 + 网络/卷 + 容器 exec + 镜像 pull + 资源清理 | `list_docker_networks`, `docker_container_exec`, `docker_prune` |
| 服务管理 | `modules/services/` | systemd 启停/重启 + enable/disable + reload + 依赖树 + 资源使用 | `service_enable_disable_tool`, `get_service_dependencies_tool` |
| 定时任务 | `modules/cron/` | cron CRUD + 启禁 + 表达式验证 + 执行历史 + 备份 | `list_cron_jobs`, `validate_cron_expr`, `create_cron_job`, `modify_cron_schedule`, `toggle_cron_job_tool`, `delete_cron_job_tool` |

## 关键约定

- **敏感文件禁读**: `.env`, `~/.api_keys`, `~/.telegram_config`, `~/config.yaml`
- **环境变量前缀**: `SERVERHUB_*`（应用配置），各服务商 API Key 用各自的 env var（见 `llm.py` PROVIDERS）
- **API 路由前缀**: 每个模块 `APIRouter(prefix="/api/模块名")`
- **审计中间件**: 所有 POST/PUT/DELETE `/api/*` 请求自动记录到 `audit_log` 表
- **Agent 安全层**: `supervised` 模式下危险操作触发 `interrupt_on` 审批；`autonomous` 模式（巡检用）不中断但仍有 Shell 黑名单底线防护
- **Cron 服务**: Python 3.11 的 f-string 不支持反斜杠，匹配正则时先提取 match 对象再在 f-string 中引用

## 开发原则

- **框架优先**: 在实现新功能前，必须先查阅 Deep Agents 框架已有的实现方式（查看 `deepagents` 包源码或用 Context7 查文档），优先使用框架提供的机制，而非自己从零实现。例如：代码执行应通过框架的 Backend 架构（`write_file` + `execute`），而非自造 `run_code` 工具
- **继承扩展**: 需要定制框架行为时，优先继承框架的类并 override 具体方法（如 `SafeLocalShellBackend` 继承 `LocalShellBackend`），而非绕过框架
- **提示词引导**: 对于行为规范（如代码应写入哪个目录），优先通过系统提示词引导 agent 行为，而非硬编码到工具中
- **运行时 agent 记忆位于 `data/agent-memory.md`**: 该文件是 AI 运维助手的长期记忆，由 Deep Agents MemoryMiddleware 加载到系统提示词。Agent 通过 `edit_file()` 自动更新。仓库根目录 `AGENTS.md` 留给外部编码助手/仓库协作说明使用
- **SubAgent 规范**: 创建新 SubAgent 必须使用 `/create-subagent` skill，遵循 LangChain 官方 SubAgent 规范（4 个 Required 字段 + 最小工具集 + 500 词输出限制）。详见 `~/.claude/skills/create-subagent/`
- **配置持久化**: 自定义配置存 `data/` 目录（.gitignore 已排除），不修改源码文件。优先读自定义文件，不存在则用源码默认值

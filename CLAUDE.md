# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

ServerHub 是一个基于 FastAPI 的 Linux 服务器全功能 Web 管理系统，集成了 AI 运维智能体。面向实验室/团队场景，提供系统监控、Docker/服务管理、用户资源控制、AI 自动巡检等能力。

**技术栈**: FastAPI + React 18 + TypeScript + Tailwind CSS + SQLite(aiosqlite) + Deep Agents(LangGraph) + xterm.js

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

### React 前端 (frontend/)

全站已从 Jinja2 + HTMX + Alpine.js 迁移至 React 18 + TypeScript + Tailwind CSS。

**开发**:
```bash
cd frontend && npm run dev   # Vite dev server :5173, proxy → :9900
npm run build                # 生产构建 → frontend/dist/
```

**架构**:
- 路由: React Router v7, 19 条路由 + 代码分割 (React.lazy)
- 状态: TanStack Query (API 缓存) + Zustand (客户端状态)
- 认证: Cookie auth (HttpOnly JWT), 401 自动 refresh + 重定向
- 实时: WebSocket (/ws/metrics) + SSE (POST /api/agents/chat)
- 图表: echarts-for-react + 暗色主题
- Markdown: marked.js + highlight.js + mermaid.js + DOMPurify
- 终端: @xterm/xterm WebSocket

**关键文件**:
- `src/App.tsx` — 路由配置 + 认证守卫
- `src/api/client.ts` — Axios 实例 (cookie auth, 401 refresh, 请求队列)
- `src/hooks/useSSEChat.ts` — SSE 流解析 (7 种事件类型)
- `src/hooks/useWebSocket.ts` — 指标 WebSocket (60 点缓冲区)
- `src/pages/agents/` — Agent 页面 14 个子组件
- `src/lib/markdown.ts` — Markdown 渲染配置 (mermaid + artifact)

**后端为 React 添加的端点**:
- `GET /api/sidebar` — 侧边栏菜单项 (按角色过滤)
- SPA catch-all 路由 (生产模式, 服务 frontend/dist/)

### AI 智能体架构 (modules/agents/)

基于 **Deep Agents 框架**，通过 `create_deep_agent()` 构建。模块已拆分为结构化子目录：

```
modules/agents/
├── deep_agent.py    → 工厂函数，组装 model + tools + backend + middleware + subagents + memory + store
├── llm.py           → 8 家 LLM 服务商注册表，parse_model_id("provider:model")
├── tools/           → 50+ 个 @tool 服务器管理工具（11 个子模块：system/docker/services/users/cron/assets/knowledge/security/notifications/scripts/servers）
├── subagents/       → 6 个 SubAgent 定义（researcher/log-analyzer/security-auditor/correlation-analyzer/ops-scheduler/knowledge-retriever）+ 配置管理
├── async_graphs/    → 3 个异步 SubAgent 图（researcher/security-auditor/correlation-analyzer）
├── lg_compat.py     → LangGraph 兼容 HTTP 服务器（异步任务执行）
├── safety.py        → build_interrupt_config() 生成审批规则 + Shell 黑名单
├── sandbox.py       → SafeLocalShellBackend（继承 LocalShellBackend，剥离敏感环境变量 + ulimit 资源限制）
├── prompts.py       → 系统提示词 + get_system_prompt() 优先读自定义文件
├── patrol.py        → 6 个内置巡检任务 + asyncio 调度循环（每 60s 检查）
├── routes/          → 9 个 HTTP 端点子模块（chat/conversations/approvals/patrols/config/alerts/fault/async_tasks/terminal）
└── terminal.py      → pty.fork() WebTerminal 类
```

**Backend**: `SafeLocalShellBackend(root_dir=~)` — 继承 `LocalShellBackend`，剥离 `*API_KEY*`/`*SECRET*`/`*TOKEN*` 环境变量，沙箱目录 `/tmp/serverhub-sandbox/` 内执行自动添加 ulimit 资源限制。

**SubAgent 系统** (已拆分为 `subagents/` 子目录，每个 SubAgent 独立文件):
- `researcher` — 联网搜索（Tavily），tools: `[web_search, think]`，middleware: light
- `log-analyzer` — 日志分析，tools: `[get_container_logs, get_service_logs]`，middleware: heavy
- `security-auditor` — 安全审计，tools: `[get_system_overview, check_compliance]`，middleware: ops
- `correlation-analyzer` — 多源关联分析（11 个工具），middleware: heavy
- `ops-scheduler` — 定时任务管理（6 个 cron 工具），middleware: ops
- `knowledge-retriever` — RAG 知识检索，tools: `[retrieve_knowledge, search_fault_cases, web_search, think]`，middleware: light
- 异步 SubAgent: researcher/security-auditor/correlation-analyzer 可通过 `async_graphs/` + `lg_compat.py` 后台执行
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

### 管理面板 (Agent 页面「管理」标签)

通过 `/api/agents/admin/*` 端点管理 agent 配置，无需重启服务：
- `GET/PUT /api/agents/admin/prompt` — 系统提示词（持久化到 `data/custom_prompt.txt`）
- `GET/PUT /api/agents/admin/subagents` — SubAgent 配置 + 可用工具 + 供应商列表（持久化到 `data/custom_subagents.json`）
- `GET/PUT /api/agents/admin/memory` — `data/agent-memory.md` 运行时长期记忆
- 巡检提示词/工具/间隔通过 `PUT /api/agents/patrols/{id}` 扩展字段修改

保存后调用 `reset_agent_cache()` 使新配置在下次对话生效。

### 前端布局 (Agent 页面)

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

表结构在 `database.py:init_tables()` 中定义，启动时自动创建 (30 张表)。关键新增: `servers`, `server_groups`, `server_group_members`; metrics 表含 `server_id` 列 (DEFAULT 'local')。

**注意**: `_ensure_column` 添加新列后才能创建依赖该列的索引（不能放在同一个 `executescript` 中）。

### 多服务器管理 (modules/servers/)

Hub-Agent 架构：中心 Hub (本项目) + 每台被管理服务器部署 `serverhub-agent/` 守护进程。

- `modules/servers/` — 服务器注册/分组/连通性测试/心跳(30s)
- `modules/servers/agent_client.py` — HTTP 客户端 (Fernet Token 加密鉴权)
- `modules/servers/heartbeat.py` — 三层健康检查: 存活→鉴权→业务
- `serverhub-agent/` — 独立包 (FastAPI :9901, 12 个结构化端点, Bearer Token 认证)
- `modules/monitoring/scheduler.py` — 本地采集(60s) + 远程采集(60s, 并行 executemany)
- `modules/monitoring/metrics_store.py` — 指标抽象层 (fleet 查询/批量/聚合)
- `frontend/src/pages/FleetDashboardPage.tsx` — 舰队总览 (概览网格/对比图表/热力图)

**server_id 贯穿全栈**: TopBar 选择器 → Zustand serverStore → TanStack Query queryKey → API params → 后端 dispatch → AgentClient/本地执行

**远程执行安全**: 所有远程操作通过 Agent 结构化端点 (create_subprocess_exec)，不用 shell 拼接。/execute 端点默认关闭。

**Token 生命周期**: `secrets.token_urlsafe(32)` 生成 → Fernet 加密存 `agent_token_encrypted` → `decrypt_agent_token()` 解密 → Bearer header 发给 Agent

### 启动架构 (main.py lifespan)

关键路径（阻塞 ready）: `get_db()` → `ensure_admin()` → `discover_modules()` → 路由注册
后台初始化（非阻塞）: 通知/监控/RAG/巡检/剧本/心跳/远程采集 — 各自 try/except，失败不影响服务
健康检查: `GET /api/health` (无需认证) → `{"status": "ok", "subsystems": {...}, "uptime": N}`

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

## 代码质量工具

### Ruff (lint + format)

配置在 `pyproject.toml`，替代 flake8 + black + isort。

```bash
make check          # ruff check + format --check
make lint-fix       # 自动修复
make format         # 格式化
```

### RoboRev (AI 代码评审)

- **配置**: `.roborev.toml` (agent=codex, backup=claude-code)
- **触发**: 每次 `git commit` 自动通过 `.git/hooks/post-commit` 触发
- **评审失败**: hook 自动调用 `.roborev-issue.sh` 创建 GitHub Issue + 启动 Claude Code 修复
- **手动评审**: `/roborev-review HEAD` 或 `/roborev-review --type security`
- **手动修复**: `/roborev-fix <job_id>`
- **注意**: `roborev config set` 会重写 toml 文件，修改后需检查 `[[hooks]]` 是否被清空

## 已知陷阱

- **LangChain content 格式**: `AIMessage.content` 可能是 `string` 或 `[{type:"text", text:"..."}]` 数组。前端必须用 `extractContent()` 统一处理，不能 `as string` 强转
- **API 返回值类型**: 后端返回 `{items: [...]}` 对象包裹时，前端不能直接 `.map()`。所有 useQuery 必须加 `Array.isArray(raw) ? raw : raw?.fieldName ?? []`
- **SQLite `_ensure_column` 时序**: 先 `_ensure_column` 添加列，再 `CREATE INDEX`。不能放在同一个 `executescript` 中
- **路径安全**: Agent `/var/log` 路径检查必须用 `/var/log/` (带斜杠) 防止 `/var/log2` 绕过
- **远程执行**: 所有远程命令必须通过 Agent 结构化端点 (`create_subprocess_exec`)，禁止 shell 拼接
- **Fernet vs SHA256**: `agent_token_encrypted` 是 Fernet 可逆加密（需解密传给 Agent），不是 hash
- **WebSocket 订阅**: Fleet 页面订阅 `["*"]`，Dashboard 只订阅 `[selectedServerId]`，默认 `{"local"}`
- **`groups` 字段类型**: 后端返回 `string`（逗号分隔），前端需 `Array.isArray(x) ? x : x.split(',')` 兼容

## 开发原则

- **框架优先**: 在实现新功能前，必须先查阅 Deep Agents 框架已有的实现方式（查看 `deepagents` 包源码或用 Context7 查文档），优先使用框架提供的机制，而非自己从零实现。例如：代码执行应通过框架的 Backend 架构（`write_file` + `execute`），而非自造 `run_code` 工具
- **继承扩展**: 需要定制框架行为时，优先继承框架的类并 override 具体方法（如 `SafeLocalShellBackend` 继承 `LocalShellBackend`），而非绕过框架
- **提示词引导**: 对于行为规范（如代码应写入哪个目录），优先通过系统提示词引导 agent 行为，而非硬编码到工具中
- **运行时 agent 记忆位于 `data/agent-memory.md`**: 该文件是 AI 运维助手的长期记忆，由 Deep Agents MemoryMiddleware 加载到系统提示词。Agent 通过 `edit_file()` 自动更新。仓库根目录 `AGENTS.md` 留给外部编码助手/仓库协作说明使用
- **SubAgent 规范**: 创建新 SubAgent 必须使用 `/create-subagent` skill，遵循 LangChain 官方 SubAgent 规范（4 个 Required 字段 + 最小工具集 + 500 词输出限制）。详见 `~/.claude/skills/create-subagent/`
- **配置持久化**: 自定义配置存 `data/` 目录（.gitignore 已排除），不修改源码文件。优先读自定义文件，不存在则用源码默认值

## 必须遵循的开发规范

所有开发工作都必须遵循 [docs/CONTRIBUTING.md](/home/zhengxiaodong/scripts/server-hub/docs/CONTRIBUTING.md)；以下规则是协作时必须直接执行的摘要：

- **编码风格**: Python 遵循 PEP 8、4 空格缩进、单行不超过 120 字符；文件头使用三引号说明模块功能；导入顺序为标准库、第三方库、本地模块；模块顶层优先定义 `logger = logging.getLogger(__name__)`
- **命名规范**: 函数和变量使用 `snake_case`，类使用 `PascalCase`，常量使用 `UPPER_CASE`，模块目录保持小写 `snake_case`
- **API 规范**: APIRouter 前缀统一为 `/api/<module>`；路径段用 kebab-case，查询参数和路径参数用 snake_case；POST/PUT/DELETE 返回 `{"ok": true, ...}`；GET 直接返回数据；错误统一使用 `HTTPException`
- **认证与审计**: 认证和鉴权必须通过依赖注入声明，优先使用 `get_current_user`、`require_role("admin")`；不要在 handler 内手动解析 token；写操作由审计中间件自动记录，不要重复造日志逻辑
- **数据库规范**: 统一通过 `get_db()` 访问主库；新增表写入 `database.py:init_tables()`；SQL 必须参数化；写操作先 `commit` 再执行通知等副作用
- **模块结构**: `routes.py` 只处理 HTTP 层，业务逻辑放入 `services.py`；新增模块需导出 `MODULE_INFO` 和 `router`
- **前端规范**: React 18 + TypeScript + Tailwind CSS；使用 TanStack Query 管理服务端状态，Zustand 管理客户端状态；API 调用通过 `@/api/client` Axios 实例；避免 `any`，使用可选链防御性访问
- **提交与文档**: Git 提交消息遵循 `feat|fix|docs|refactor|perf|test|chore|style: 中文描述`；新增 API、Agent 工具、模块或架构变化时，必须同步更新 `docs/` 中对应文档

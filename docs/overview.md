# ServerHub 系统总体概述

ServerHub 是一个面向实验室/团队场景的 Linux 服务器全功能 Web 管理系统，集成了 AI 运维智能体，提供从系统监控到 AI 自动巡检的一站式服务器管理能力。

---

## 目录

1. [项目定位](#1-项目定位)
2. [技术栈](#2-技术栈)
3. [功能全景](#3-功能全景)
4. [部署环境](#4-部署环境)

---

## 1. 项目定位

### 面向的场景

ServerHub 专为以下场景设计：

- **实验室服务器管理**：多用户共享的 GPU 服务器，需要监控资源使用、限制用户配额、管理 Docker 容器
- **团队运维自动化**：通过 AI 智能体自动执行巡检任务，减少人工运维成本
- **轻量化替代方案**：相比 Zabbix、Prometheus 等重型监控系统，ServerHub 开箱即用、无需复杂配置

### 核心能力

- **实时监控**：CPU、内存、GPU、磁盘、网络的实时和历史指标
- **服务管理**：systemd 服务、Docker 容器的启停和状态查看
- **用户资源控制**：基于 cgroup 的用户内存/进程配额管理
- **AI 运维助手**：通过自然语言与服务器交互，执行运维操作、分析日志
- **自动巡检**：定时执行内存、Docker、GPU、磁盘、安全合规等巡检任务
- **告警通知**：通过 Telegram 推送告警和日报

---

## 2. 技术栈

### 后端

| 组件 | 版本/说明 |
|------|---------|
| **FastAPI** | 异步 Web 框架，提供 REST API 和 SSE 流式响应 |
| **Pydantic** | 请求/响应数据模型验证 |
| **SQLite + aiosqlite** | 轻量级异步数据库，3 个独立数据库文件 |
| **Deep Agents (LangGraph)** | AI 智能体框架，支持工具调用、SubAgent、记忆系统 |
| **LangChain** | LLM 集成层，统一接入 8 家服务商 |
| **Python 3.11** | 运行环境，conda 环境名 `serverhub` |

### 前端

| 组件 | 版本/说明 |
|------|---------|
| **React** | ^19.2 SPA，React Router v7，React.lazy 代码分割 |
| **TypeScript** | ~5.9，严格类型检查 |
| **Tailwind CSS** | ^4.2，暗色主题 |
| **Vite** | ^8.0 构建工具，开发服务 :5173 代理到后端 :9900 |
| **TanStack Query** | ^5.95 API 数据缓存和状态管理 |
| **Zustand** | ^5.0 客户端状态管理 |
| **echarts-for-react** | ^3.0 监控图表 + 暗色主题 |
| **@xterm/xterm** | ^6.0 浏览器内 WebTerminal（WebSocket + pty） |
| **Lucide React** | ^1.6 UI 图标库 |
| **Vitest** | ^3.2 前端单元测试框架 |

### AI 智能体

| 组件 | 说明 |
|------|------|
| **Deep Agents** | 核心框架，提供 LangGraph 编排、Middleware、SubAgent |
| **AsyncSqliteSaver** | LangGraph checkpoint 持久化（短期记忆） |
| **MemoryMiddleware** | data/agent-memory.md 长期记忆加载 |
| **AsyncSqliteStore** | 结构化键值存储（长期记忆） |
| **SafeLocalShellBackend** | 安全沙箱 Shell 执行后端 |

---

## 3. 功能全景

### 3.1 功能模块列表

| 模块 | 目录 | 说明 | 所需角色 |
|------|------|------|---------|
| 仪表盘 | `modules/dashboard/` | 系统资源实时概览（CPU/内存/GPU/磁盘） | user |
| 监控 | `modules/monitoring/` | 历史指标图表，60s 采集间隔，保留 90 天 | user |
| Docker | `modules/docker/` | 容器列表、启停、日志查看；compose 堆栈管理 | admin |
| 系统服务 | `modules/services/` | systemd 服务状态、启停、日志 | admin |
| 用户资源 | `modules/users/` | 用户内存/进程使用统计与配额管理 | admin |
| 日志 | `modules/logs/` | 系统和应用日志浏览（白名单目录） | admin |
| Cron | `modules/cron/` | 定时任务查看与编辑 | admin |
| 网络 | `modules/network/` | 网络连接、端口占用、防火墙状态 | admin |
| 代理 | `modules/proxy/` | Clash 代理状态与切换 | admin |
| 通知 | `modules/notifications/` | Telegram 通知历史与手动推送 | admin |
| 审计 | `modules/audit/` | 所有写操作的审计日志 | admin |
| 面板用户 | `modules/panel_users/` | ServerHub 账户管理（增删改角色） | admin |
| 设置 | `modules/settings/` | 系统配置（配额文件、服务列表等） | admin |
| 资产 | `modules/assets/` | 服务器资产信息管理 | admin |
| AI 智能体 | `modules/agents/` | AI 对话、自动巡检、WebTerminal | admin |
| 服务器管理 | `modules/servers/` | 多服务器注册、分组、心跳、舰队概览 | admin |
| 运维剧本 | `modules/playbooks/` | 参数化运维剧本、定时触发、执行历史 | admin |

### 3.2 AI 智能体能力

**自定义工具（49 个，分布在 14 个子模块）**

按安全级别分为三类：

| 级别 | 数量 | 说明 |
|------|------|------|
| safe | 25 | 只读查询（系统状态、Docker、服务、用户、资产、知识库、服务器列表等） |
| moderate | 12 | 可逆操作（容器/服务启停、配额修改、cron 管理、容器 exec 等），supervised 模式需审批 |
| danger | 7 | 高风险不可逆操作（kill 进程、合规修复、脚本执行、Docker 清理、用户管理、cron 删除），always 需审批 |

工具子模块：system(3) / docker(7) / services(5) / users(10) / cron(6) / assets(4) / knowledge(2) / security(2) / notifications(1) / scripts(1) / playbook(5) / servers(2) / page_context(1)

框架注入工具（9 个）：`execute`, `read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`, `write_todos`, `task`

**SubAgent（6 个）**

| SubAgent | 功能 | 工具 |
|----------|------|------|
| `researcher` | 联网搜索和研究 | `web_search`, `think` |
| `log-analyzer` | 日志分析 | `get_container_logs`, `get_service_logs` |
| `security-auditor` | 安全审计 | `get_system_overview`, `check_compliance` |
| `correlation-analyzer` | 多源关联分析 | 11 个工具 |
| `ops-scheduler` | 定时任务管理 | 6 个 cron 工具 |
| `knowledge-retriever` | RAG 知识检索 | `retrieve_knowledge`, `search_fault_cases`, `web_search`, `think` |

### 3.3 巡检任务（8 个）

| 巡检任务 | 执行间隔 | 说明 |
|----------|---------|------|
| 内存巡检 | 每 30 分钟 | 系统内存 + 用户配额超限告警 |
| Docker 容器健康 | 每 15 分钟 | 检测 restarting/exited 状态容器 |
| GPU 监控 | 每小时 | 温度（>80°C 警告）+ 显存（>95% 告警） |
| 服务状态巡检 | 每 30 分钟 | systemd 服务意外停止告警 |
| 磁盘空间巡检 | 每 6 小时 | 挂载点使用率 >90% 告警 |
| 每日综合报告 | 每天 | 全面状态报告，发送 Telegram |
| 安全合规检查 | 每天 | 基于 CIS Benchmark 的安全基线检查 |
| 资源趋势周报 | 每周 | 过去一周资源趋势分析和预测 |

### 3.4 LLM 服务商支持（8 家）

| 服务商 | 标识 | API Key 环境变量 |
|--------|------|----------------|
| OpenRouter（推荐） | `openrouter` | `OPENROUTER_API_KEY` |
| 火山引擎（豆包） | `volcengine` | `VOLCENGINE_API_KEY` |
| 智谱 AI（GLM） | `zhipu` | `ZHIPU_API_KEY` |
| Kimi（月之暗面） | `moonshot` | `MOONSHOT_API_KEY` |
| MiniMax | `minimax` | `MINIMAX_API_KEY` |
| DeepSeek（直连） | `deepseek` | `DEEPSEEK_API_KEY` |
| OpenAI（直连） | `openai` | `OPENAI_API_KEY` |
| Ollama（本地） | `ollama` | 无需 Key |

模型 ID 格式：`provider:model_name`，例如 `openrouter:deepseek/deepseek-chat`

### 3.5 新增功能

#### 一键部署远程服务器

通过 `POST /api/servers/deploy` 端点，提供 SSH 密码即可自动完成远程服务器的注册、Agent 安装和连通性验证。前端提供完整的部署向导 UI，实时显示部署日志。

#### Smoke Test 集成验证

`scripts/smoke-test.sh` 脚本用于验证 ServerHub 关键端点的健康状态。支持指定地址测试，退出码 0 表示全部通过。可通过 `make smoke-test` 快捷运行。

#### RoboRev 自动评审

基于 Claude Code 的 commit 级自动代码评审系统。评审发现自动创建 Issue，触发 Claude Code 后台修复，生成 PR 后合并。支持 worktree 隔离运行，避免与用户工作冲突。配合 `gh-cleanup.sh` 每小时自动合并/关闭 roborev PR 和清理分支。

#### Agent Studio 增强

- Skills 详情面板：查看技能版本、安装状态、绑定关系
- SubAgents 编辑：在线编辑 SubAgent 配置（工具集、模型、提示词）

#### Agent Teams 安全加固

- 成员工具权限隔离：`user_role` 参数贯穿图构建，非 admin 用户只能使用 safe 级别工具
- Swarm handoff 循环检测：使用 `deque` 滑动窗口检测 2-agent 死循环
- 异步执行超时保护：`asyncio.wait_for` 实现 deadline 超时

### 3.6 Middleware 栈（12 个）

| 来源 | Middleware | 说明 |
|------|-----------|------|
| 框架自动 | TodoList | 任务列表管理 |
| 框架自动 | Filesystem | 文件操作工具注入 |
| 框架自动 | SubAgent | SubAgent 调度 |
| 框架自动 | Summarization | 长对话摘要 |
| 框架自动 | PatchToolCalls | 工具调用修复 |
| 框架自动 | AnthropicPromptCaching | Anthropic 模型缓存 |
| 框架自动 | HumanInTheLoop | 人工审批中断 |
| 框架自动 | Memory | data/agent-memory.md 记忆加载 |
| 手动注入 | ModelRetry | 模型调用失败重试（3次） |
| 手动注入 | ToolRetry | 工具调用失败重试（2次） |
| 手动注入 | ModelCallLimit | 调用次数限制（chat:50/patrol:100） |
| 手动注入 | ContextEditing | 上下文裁剪（60K token 上限） |

---

## 4. 部署环境

### 当前运行环境

- **主机名**: system-NF5468M6
- **系统**: Ubuntu 23.04 (Lunar Lobster)
- **CPU**: Intel Xeon Platinum 8380, 160 逻辑核心
- **内存**: 503 GB
- **GPU**: NVIDIA A800 80GB PCIe
- **服务端口**: 9900

### 数据文件

所有运行时生成的数据存储在 `data/` 目录（已加入 `.gitignore`）：

| 文件 | 说明 |
|------|------|
| `data/server-hub.db` | 应用主数据库 |
| `data/agent-checkpoints.db` | Agent 会话 checkpoint |
| `data/agent-store.db` | Agent 结构化存储 |
| `data/custom_prompt.txt` | 自定义系统提示词（存在时覆盖默认值） |
| `data/custom_subagents.json` | 自定义 SubAgent 配置 |
| `data/serverhub-secret.key` | 自动生成的 JWT 签名密钥（未设置环境变量时） |
| `data/bootstrap-admin-password.txt` | 自动生成的初始管理员密码（未设置环境变量时） |

### 相关文档

- [快速上手](getting-started.md) — 安装、配置、启动
- [架构设计](architecture.md) — 系统架构详解
- [开发规范](CONTRIBUTING.md) — 贡献代码规范
- [API 文档](api/) — 各模块 API 参考
- [Agent 文档](agents/) — AI 智能体详解

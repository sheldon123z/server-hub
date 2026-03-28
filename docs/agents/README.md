# AI 智能体子系统总览

ServerHub 的 AI 智能体子系统基于 **Deep Agents 框架**（deepagents + LangGraph）构建，提供对话式运维助手、定时巡检、告警规则引擎、故障诊断等能力。

关于新的 `run` 生命周期、Skill 安装体系和独立 Agent Studio 入口，见 [studio-runtime.md](./studio-runtime.md)。

---

## Deep Agents 框架简介

Deep Agents 是基于 LangGraph 的多智能体框架，通过 `create_deep_agent()` 工厂函数组装：

- **主 Agent**：负责与用户对话、调用工具、协调子智能体
- **SubAgent**：专业化子智能体，通过 `task()` 工具委派
- **Backend**：Shell + 文件系统执行环境（`SafeLocalShellBackend`）
- **Middleware 栈**：12 个中间件处理重试、限制、上下文压缩等横切关注点
- **记忆系统**：三层记忆架构（短期 / 长期 / 结构化）

---

## 架构图

```
用户请求（HTMX SSE）
       │
       ▼
  routes.py (FastAPI)
       │
       ▼
  build_agent()
  ┌─────────────────────────────────────────────────┐
  │              Deep Agent Graph                    │
  │                                                  │
  │  ┌──────────┐    ┌─────────────────────────────┐│
  │  │ Middleware│    │      Agent 节点             ││
  │  │  栈(12个) │───▶│  ChatModel (LLM)            ││
  │  │          │    │  + System Prompt             ││
  │  └──────────┘    └──────────┬──────────────────┘│
  │                             │                    │
  │              ┌──────────────┼──────────────────┐ │
  │              ▼              ▼                  ▼ │
  │         自定义工具     内置工具(9个)      task()  │
  │         (22个)        execute/read       委派     │
  │                       write/edit        SubAgent │
  │                       ls/glob/grep               │
  │                       write_todos/task           │
  └─────────────────────────────────────────────────┘
       │                                   │
       ▼                                   ▼
  SafeLocalShellBackend             SubAgent(4个)
  (Shell + 文件系统)                researcher
  /tmp/serverhub-sandbox/           log-analyzer
                                    security-auditor
                                    correlation-analyzer
```

### Middleware 栈（注入顺序）

| 顺序 | Middleware | 来源 | 作用 |
|------|-----------|------|------|
| 1 | TodoList | 框架自动 | 任务列表管理 |
| 2 | Filesystem | 框架自动 | 文件系统能力 |
| 3 | SubAgent | 框架自动 | 子智能体调度 |
| 4 | Summarization | 框架自动 | 历史消息压缩 |
| 5 | PatchToolCalls | 框架自动 | 工具调用修复 |
| 6 | ModelRetry | 手动注入 | 模型调用重试（3次，指数退避）|
| 7 | ToolRetry | 手动注入 | 工具调用重试（2次）|
| 8 | ModelCallLimit | 手动注入 | 调用次数限制（chat:50, patrol:100）|
| 9 | ContextEditing | 手动注入 | 超 60K token 清理旧工具输出 |
| 10 | AnthropicPromptCaching | 框架自动 | Anthropic 提示词缓存 |
| 11 | HumanInTheLoop | 框架自动 | 人工审批中断 |
| 12 | Memory | 框架自动 | data/agent-memory.md 长期记忆注入 |
| 13 | ModelFallback | 手动注入（可选）| 模型降级切换（chat 模式）|

---

## 核心组件清单

### 工具层（tools.py）

22 个 `@tool` 装饰的服务器管理工具，按风险分三级：

| 风险级别 | 工具数量 | 典型工具 |
|---------|---------|---------|
| safe（只读）| 15 | get_system_overview, list_docker_containers, check_compliance, analyze_resource_trend |
| moderate（可逆操作）| 6 | docker_container_action, service_control, update_user_quotas, create_cron_job |
| danger（高危）| 4 | kill_user_processes, auto_fix_compliance, execute_ops_script, delete_cron_job_tool |

详细说明见 [tools.md](./tools.md)。

### SubAgent 层（subagents.py）

4 个专业化子智能体，遵循 LangChain 官方 SubAgent 规范：

| 名称 | 专长 | 工具集 |
|------|------|-------|
| researcher | 联网搜索 | web_search, think |
| log-analyzer | 日志分析 | get_container_logs, get_service_logs |
| security-auditor | 安全审计 | get_system_overview |
| correlation-analyzer | 多源关联分析 | 6 个工具 |

详细说明见 [subagents.md](./subagents.md)。

### 巡检系统（patrol.py）

- 8 个内置巡检任务，最短 15 分钟一次
- 11 个巡检模板，支持参数化创建
- asyncio 调度循环，每 60s 检查一次到期任务
- 报告结构化解析，触发告警规则引擎

详细说明见 [patrol.md](./patrol.md)。

### 告警规则引擎（alert_engine.py）

- 7 条阈值告警规则（CPU / 内存 / GPU / 磁盘）
- 3 条基线偏离规则（μ±3σ，7 天滑动窗口）
- Cooldown 去重机制，防止告警风暴
- 触发后发送 Telegram 通知

详细说明见 [alerts.md](./alerts.md)。

### 故障诊断（diagnosis.py）

- 巡检 critical 状态自动触发（`asyncio.create_task`，不阻塞巡检流程）
- 独立 agent 执行：收集状态 → 日志分析（委派 log-analyzer）→ 根因分析 → 报告
- 结构化 JSON 报告存入 `fault_reports` 表
- 自动录入 `fault_cases` 案例库（含 FTS5 全文索引）

详细说明见 [diagnosis.md](./diagnosis.md)。

### 合规检查（tools.py + data/compliance_baselines.json）

- 15 条 CIS Benchmark 基线（SSH / 口令策略 / 权限 / 网络 / 内核 / 审计）
- `check_compliance` 工具执行检查，`auto_fix_compliance` 自动修复
- 配置文件驱动，无需改代码

详细说明见 [compliance.md](./compliance.md)。

### 安全层（safety.py）

- supervised 模式：危险工具触发 interrupt_on 审批
- autonomous 模式：巡检专用，全自动但有 Shell 黑名单底线防护
- TOOL_RISK_MAP：33 个工具的风险标签（前端展示用）

详细说明见 [safety.md](./safety.md)。

### 记忆系统（deep_agent.py）

- 短期：AsyncSqliteSaver checkpoint（per-conversation state 持久化）
- 长期：`data/agent-memory.md`（MemoryMiddleware 注入系统提示词，agent 通过 edit_file 更新）
- 结构化：AsyncSqliteStore（namespace + key-value → `data/agent-store.db`）

详细说明见 [memory.md](./memory.md)。

---

## 关键文件路径

| 文件 | 说明 |
|------|------|
| `modules/agents/deep_agent.py` | Agent 工厂，build_agent() 入口 |
| `modules/agents/tools.py` | 22 个自定义工具 |
| `modules/agents/subagents.py` | 4 个 SubAgent 定义 |
| `modules/agents/patrol.py` | 巡检任务 + 调度器 |
| `modules/agents/alert_engine.py` | 告警规则引擎 |
| `modules/agents/diagnosis.py` | 故障诊断工作流 |
| `modules/agents/safety.py` | 安全层配置 |
| `modules/agents/prompts.py` | 系统提示词 |
| `modules/agents/llm.py` | 8 家 LLM 服务商注册表 |
| `modules/agents/sandbox.py` | SafeLocalShellBackend |
| `modules/agents/routes.py` | SSE / 审批 / 巡检 / 管理 API |
| `data/compliance_baselines.json` | 15 条 CIS 合规基线定义 |
| `data/agent-memory.md` | AI 助手长期记忆文件 |
| `data/custom_prompt.txt` | 自定义系统提示词（可选）|
| `data/custom_subagents.json` | 自定义 SubAgent 配置（可选）|

# ServerHub 技术文档

> NF5468M6 服务器全功能 Web 管理系统 + AI 运维智能体

## 快速导航

| 文档 | 说明 |
|------|------|
| [系统概述](overview.md) | 项目定位、技术栈、功能全景 |
| [架构设计](architecture.md) | 三层架构、模块自发现、AI 智能体架构、数据流图 |
| [快速上手](getting-started.md) | 安装、配置、运行、首次使用 |
| [开发规范](CONTRIBUTING.md) | 编码风格、API 设计、提交规范、文档更新 |

## API 文档

完整的 REST API 参考，按模块分篇。

| 模块 | 前缀 | 端点数 | 说明 |
|------|------|--------|------|
| [API 总览](api/README.md) | — | 170+ | 认证方式、RBAC 权限模型、端点汇总 |
| [认证](api/auth.md) | `/api/auth` | 5 | 登录、登出、刷新令牌 |
| [仪表盘](api/dashboard.md) | `/api/dashboard` | 1 | 系统概览数据 |
| [系统监控](api/monitoring.md) | `/api/monitoring` | 11 | 实时指标、历史数据、GPU |
| [Docker 管理](api/docker.md) | `/api/docker` | 15 | 容器、镜像、Compose 堆栈 |
| [服务管理](api/services.md) | `/api/services` | 9 | Systemd 服务状态和控制 |
| [用户管理](api/users.md) | `/api/users` | 19 | Linux 用户资源、配额 |
| [定时任务](api/cron.md) | `/api/cron` | 10 | Crontab 查看和编辑 |
| [网络管理](api/network.md) | `/api/network` | 4 | 端口、连接、防火墙 |
| [代理管理](api/proxy.md) | `/api/proxy` | 16 | Clash 代理节点切换 |
| [日志查看](api/logs.md) | `/api/logs` | 4 | 日志文件搜索和实时流 |
| [通知管理](api/notifications.md) | `/api/notifications` | 16 | 多渠道通知（Telegram/站内/Webhook） |
| [告警管理](api/alerts.md) | `/api/alerts` | 10 | 告警规则引擎、评估器、状态机 |
| [RBAC 权限](api/rbac.md) | `/api/rbac` | 11 | 角色管理、权限矩阵、用户分配 |
| [文件管理](api/files.md) | `/api/files` | 10 | 文件浏览、读写、上传、搜索 |
| [审计日志](api/audit.md) | `/api/audit` | 1 | 操作审计记录查询 |
| [面板用户](api/panel-users.md) | `/api/panel-users` | 4 | Web 面板用户 CRUD |
| [系统设置](api/settings.md) | `/api/settings` | 1 | 非敏感配置查看 |
| [资产台账](api/assets.md) | `/api/assets` | 7 | 资产发现、拓扑图 |
| [服务器管理](api/servers.md) | `/api/servers` | 17 | 服务器注册、分组、心跳 |
| [运维剧本](api/playbooks.md) | `/api/playbooks` | 5 | 剧本 CRUD、执行、凭证 |
| [AI Agent](api/agents.md) | `/api/agents` | 59+WS | 对话、巡检、告警、诊断、案例库、Skill |

## AI 智能体专题

ServerHub 的核心特色 — 基于 Deep Agents 框架的 AI 运维智能体。

| 文档 | 说明 |
|------|------|
| [智能体总览](agents/README.md) | 架构、Middleware 栈、组件清单 |
| [Agent Studio 与 Skill Runtime](agents/studio-runtime.md) | run 生命周期、Skill 安装、Studio 入口 |
| [Agent 工具](agents/tools.md) | 49 个自定义工具 + 9 个内置工具 |
| [子智能体](agents/subagents.md) | 6 个 SubAgent 定义和使用 |
| [巡检系统](agents/patrol.md) | 8 个任务、11 个模板、调度机制 |
| [告警系统](agents/alerts.md) | 阈值规则 + 基线偏离检测 |
| [故障诊断](agents/diagnosis.md) | 自动诊断工作流 |
| [合规检查](agents/compliance.md) | 15 条 CIS 基线 + 自动修复 |
| [安全层](agents/safety.md) | 审批机制、黑名单、风险等级 |
| [记忆系统](agents/memory.md) | 三层记忆架构 |

## 基础设施

| 文档 | 说明 |
|------|------|
| [数据库 Schema](database.md) | 41 张表 + 1 FTS5 虚拟表、3 个数据库文件 |
| [前端架构](frontend.md) | React 18 + TypeScript + Tailwind CSS |

---

## 文档维护

当代码发生变更时，使用 `/update-docs` 技能自动更新对应文档。

详细的文档编写和更新规范见 [开发规范 - 文档更新](CONTRIBUTING.md#文档更新规范)。

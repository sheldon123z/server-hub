# Agent Studio 与 Skill Runtime

本文档描述 2026-03 这一轮重构后，ServerHub 智能体子系统的运行时、Skill 生命周期和前端 Agent Studio 入口。

## 目标

这一轮重构把原先“聊天页 + 分散配置项”的模式整理成三层能力：

- `conversation`：线程归档、标题、用户归属
- `run`：一次具体执行，负责流式事件、审批、取消、错误与完成状态
- `skill`：可安装、可启停、可推荐的提示层和组织层能力

前端新增独立的 Agent Studio，用于管理运行时、技能安装、子智能体、提示词和审批恢复。原 `AgentsPage` 保留为轻量聊天入口。

## 数据模型

数据库新增以下表：

- `agent_runs`
- `agent_run_events`
- `agent_skills`
- `agent_skill_versions`
- `agent_skill_installs`
- `agent_skill_bindings`

同时，`agent_approvals` 新增 `run_id` 字段，用于把审批和具体运行实例关联起来。

## Run 生命周期

核心服务位于：

- `modules/agents/run_service.py`
- `modules/agents/routes/chat.py`
- `modules/agents/routes/runs.py`
- `modules/agents/routes/approvals.py`

运行状态最少覆盖：

- `running`
- `waiting_approval`
- `cancel_requested`
- `completed`
- `error`

SSE 事件协议统一为：

- `run.started`
- `message.final`
- `tool.call`
- `tool.result`
- `todo.update`
- `approval.request`
- `run.error`
- `run.completed`

这些事件既用于前端实时渲染，也会持久化到 `agent_run_events`，从而支持会话恢复、运行回放和审批后续追踪。

## Skill 生命周期

核心服务位于：

- `modules/agents/skill_service.py`
- `modules/agents/routes/skills.py`

技能目录分为两类：

- 内置技能：`skills/`
- 运行时安装目录：`data/skills/installed/`

Skill 包格式：

- 必需：`skill.yaml`、`SKILL.md`
- 可选：`prompts/`、`templates/`、`scripts/`、`assets/`、`tests/`

当前已支持的安装与发现方式：

- 从本地 repo 路径安装
- 上传 zip / tar.gz / tgz 安装
- 配置扫描源并手动触发 discover

安全边界：

- 只有 admin 可以安装、启停、删除技能
- 上传包会校验路径穿越
- 技能推荐时仍会检查 `allowed_roles`

## 前端入口

主要页面和入口：

- `frontend/src/pages/agents/ChatPanel.tsx`
- `frontend/src/pages/agents/AgentStudioPage.tsx`
- `frontend/src/hooks/useSSEChat.ts`

其中：

- 聊天页负责消息流、审批卡片、技能推荐和取消运行
- Agent Studio 提供 `Overview / Skills / Install / SubAgents / Memory & Prompts / Runs & Approvals`

## API 摘要

运行时相关：

- `POST /api/agents/chat`
- `GET /api/agents/runs`
- `POST /api/agents/runs`
- `GET /api/agents/runs/{run_id}`
- `GET /api/agents/runs/{run_id}/events`
- `POST /api/agents/runs/{run_id}/cancel`
- `POST /api/agents/approvals/{approval_id}`

Skill 相关：

- `GET /api/agents/admin/skills`
- `GET /api/agents/admin/skill-sources`
- `PUT /api/agents/admin/skill-sources`
- `POST /api/agents/admin/skills/discover`
- `POST /api/agents/admin/skills/install-from-repo`
- `POST /api/agents/admin/skills/install-upload`
- `POST /api/agents/admin/skills/{skill_id}/enable`
- `POST /api/agents/admin/skills/{skill_id}/disable`
- `DELETE /api/agents/admin/skills/{skill_id}`
- `GET /api/agents/skills/{skill_id}`
- `GET /api/agents/skills/recommendations`

## 测试覆盖

本轮新增测试覆盖：

- run 创建、取消、事件持久化
- SSE 事件顺序与会话回放
- 审批恢复后的 run 状态更新
- skill 发现、repo 安装、上传安全校验、权限边界
- 前端 `useSSEChat` 流式处理
- 聊天页技能推荐选择
- Agent Studio 的概览和安装交互

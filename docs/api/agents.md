# AI Agent 模块 API

提供 Deep Agent 对话、审批流程、自动巡检、告警规则、故障报告、案例库、配置管理及 WebSocket 终端等完整接口。

**路由前缀**: `/api/agents`

**路由模块结构**（已拆分为子模块）:
```
modules/agents/routes/
├── __init__.py          # 统一注册所有子路由
├── chat.py              # 对话 SSE 流
├── conversations.py     # 对话历史
├── approvals.py         # 审批流程
├── patrols.py           # 巡检任务 + 模板
├── config.py            # Agent 设置 + 管理接口
├── alerts.py            # 告警规则
├── fault.py             # 故障报告 + 案例库 + 事件
├── async_tasks.py       # 异步任务管理
├── terminal.py          # WebSocket 终端
└── ui.py                # UI 组件交互回调
```

**相关文件**: `modules/agents/deep_agent.py`, `modules/agents/patrol.py`, `modules/agents/tools/`, `modules/agents/safety.py`, `modules/agents/llm.py`, `modules/agents/subagents/`, `modules/agents/lg_compat.py`

> 对话端点 (POST /chat, GET/DELETE /conversations) 需要 user 权限；其余端点需要 admin 权限。

---

## 目录

1. [对话（Chat）](#1-对话)
2. [审批（Approvals）](#2-审批)
3. [对话历史（Conversations）](#3-对话历史)
4. [巡检（Patrols）](#4-巡检)
5. [巡检模板（Templates）](#5-巡检模板)
6. [故障报告（Fault Reports）](#6-故障报告)
7. [告警规则（Alert Rules）](#7-告警规则)
8. [案例库（Fault Cases）](#8-案例库)
9. [事件记录（Events）](#9-事件记录)
10. [Agent 配置（Settings）](#10-agent-配置)
11. [管理接口（Admin）](#11-管理接口)
12. [异步任务（Async Tasks）](#12-异步任务)
13. [WebSocket 终端](#13-websocket-终端)
14. [UI 组件交互](#14-ui-组件交互)

---

## 1. 对话

### POST /api/agents/chat

向 AI Agent 发送消息，通过 **Server-Sent Events (SSE)** 流式返回响应。

**权限**: user（普通用户仅获得只读工具集）

**请求体**:

```json
{
  "message": "检查一下系统内存使用情况",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "safety_mode": "supervised"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | 是 | 用户消息内容 |
| conversation_id | string | 否 | 对话 ID（UUID），不传则自动生成新对话 |
| safety_mode | string | 否 | `supervised`（默认，危险操作需审批）/ `autonomous`（自主执行，不中断） |

**响应格式**: `text/event-stream`

SSE 事件类型说明：

| event 类型 | 说明 | data 格式 |
|-----------|------|-----------|
| `message` | Agent 文本回复 | `{"content": "...", "role": "assistant"}` |
| `tool_call` | Agent 调用工具 | `{"tool": "工具名", "input": {...}}` |
| `tool_result` | 工具执行结果 | `{"tool": "工具名", "content": "结果文本"}` |
| `todo_update` | Todo 任务列表更新 | `[{"text": "...", "status": "pending"}]` |
| `approval_request` | 危险操作请求审批（仅 supervised 模式） | 见下方审批事件格式 |
| `done` | 对话结束 | `{"conversation_id": "..."}` |
| `error` | 发生错误 | `{"error": "错误描述"}` |

**approval_request 事件 data 格式**:

```json
{
  "approval_id": "uuid",
  "conversation_id": "uuid",
  "actions": [
    {
      "name": "execute",
      "args": {"command": "rm -rf /tmp/test"}
    }
  ],
  "review_configs": [...]
}
```

**SSE 流示例**:

```
event: tool_call
data: {"tool": "get_system_overview", "input": {}}

event: tool_result
data: {"tool": "get_system_overview", "content": "CPU: 15%\nMemory: 45GB/503GB..."}

event: message
data: {"content": "当前系统内存使用约 45GB，占总量 503GB 的 8.9%，状态良好。", "role": "assistant"}

event: done
data: {"conversation_id": "550e8400-e29b-41d4-a716-446655440000"}
```

---

## 2. 审批

### GET /api/agents/approvals

获取所有待审批的操作列表（状态为 `pending` 的记录）。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "id": "uuid-approval-1",
    "conversation_id": "uuid-conv-1",
    "created_at": "2026-03-24T10:30:00",
    "tool_name": "execute",
    "tool_input": "{\"command\": \"systemctl restart nginx\"}",
    "risk_level": "danger",
    "description": "执行 execute",
    "status": "pending"
  }
]
```

---

### POST /api/agents/approvals/{approval_id}

批准或拒绝待审批操作，并将决定反馈给 Agent 继续执行。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| approval_id | 审批记录 UUID |

**请求体**:

```json
{
  "action": "approve",
  "reason": "确认可以重启 nginx"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| action | string | 是 | `approve`（批准）或 `reject`（拒绝） |
| reason | string | 否 | 操作原因说明 |

**成功响应** `200`:

```json
{
  "ok": true,
  "action": "approved",
  "result": "nginx 已成功重启，当前状态: active (running)"
}
```

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 404 | 审批记录不存在 |
| 400 | 该审批已处理过 |

---

## 3. 对话历史

### GET /api/agents/conversations

获取最近 50 条对话记录（未归档）。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "id": "uuid",
    "title": "检查一下系统内存使用情况...",
    "username": "admin",
    "safety_mode": "supervised",
    "created_at": "2026-03-24T10:30:00",
    "updated_at": "2026-03-24T10:32:00",
    "message_count": 4
  }
]
```

---

### GET /api/agents/conversations/{conversation_id}

获取指定对话的完整消息历史（从 LangGraph checkpoint 读取）。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| conversation_id | 对话 UUID |

**成功响应** `200`:

```json
{
  "conversation_id": "uuid",
  "messages": [
    {"role": "user", "content": "检查一下系统内存使用情况"},
    {"role": "tool_call", "tool": "get_system_overview", "args": {}},
    {"role": "tool_result", "content": "CPU: 15%\nMemory: 45GB/503GB..."},
    {"role": "assistant", "content": "当前系统内存使用约 45GB..."}
  ],
  "todos": [
    {"text": "检查内存使用", "status": "completed"}
  ]
}
```

---

### DELETE /api/agents/conversations/{conversation_id}

归档指定对话（软删除，设置 `is_archived=1`，不再在列表中显示）。

**权限**: admin

**成功响应** `200`:

```json
{
  "ok": true
}
```

---

## 4. 巡检

### GET /api/agents/patrols

获取所有巡检任务配置及最新执行状态。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "id": "system_health",
    "display_name": "系统健康巡检",
    "description": "检查 CPU、内存、磁盘、GPU 使用率",
    "interval_minutes": 60,
    "enabled": true,
    "last_run": "2026-03-24T10:00:00",
    "last_status": "ok",
    "last_report": "系统状态正常。CPU 15%，内存 8.9%...",
    "check_tools": "get_system_overview,get_disk_usage",
    "prompt": ""
  }
]
```

内置巡检任务 ID：`system_health`、`docker_health`、`service_health`、`disk_usage`、`security_check`、`network_check`。

---

### PUT /api/agents/patrols/{patrol_id}

更新巡检任务配置（启用/禁用、间隔、提示词、检查工具）。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| patrol_id | 巡检任务 ID |

**请求体**（所有字段可选）:

```json
{
  "enabled": true,
  "interval_minutes": 30,
  "prompt": "重点检查内存泄漏和僵尸进程",
  "check_tools": "get_system_overview,get_process_list"
}
```

**成功响应** `200`:

```json
{
  "ok": true
}
```

---

### POST /api/agents/patrols/{patrol_id}/run

立即触发指定巡检任务（异步执行，不等待结果）。

**权限**: admin

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "巡检 系统健康巡检 已触发"
}
```

---

### GET /api/agents/patrols/{patrol_id}/history

获取指定巡检任务的执行历史。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 20 | 返回最近 N 条记录 |

**成功响应** `200`:

```json
[
  {
    "timestamp": "2026-03-24T10:00:00",
    "status": "ok",
    "report": "系统状态正常。CPU 15%，内存 8.9%...",
    "duration": 12.5,
    "report_json": {
      "overall_status": "ok",
      "findings": [],
      "recommendations": []
    }
  }
]
```

---

### GET /api/agents/patrols/{patrol_id}/report/{history_id}

获取单次巡检的完整结构化报告。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| patrol_id | 巡检任务 ID |
| history_id | 历史记录 ID（数字） |

**成功响应** `200`:

```json
{
  "timestamp": "2026-03-24T10:00:00",
  "status": "ok",
  "report": "完整的巡检文本报告...",
  "duration": 12.5,
  "report_json": {
    "overall_status": "ok",
    "severity": "info",
    "findings": [],
    "recommendations": [],
    "metrics": {}
  }
}
```

---

## 5. 巡检模板

### GET /api/agents/templates

列出所有巡检模板（内置 + 自定义）。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| category | string | `""` | 按分类过滤，空则返回全部 |

**成功响应** `200`:

```json
[
  {
    "id": "memory_leak_check",
    "name": "内存泄漏检查",
    "category": "performance",
    "description": "检测可能存在内存泄漏的进程",
    "check_tools": "get_system_overview,get_process_list",
    "prompt_template": "请重点检查以下进程的内存占用趋势：{process_names}",
    "variables": [
      {"name": "process_names", "description": "要检查的进程名列表", "default": "python,java"}
    ],
    "is_builtin": true
  }
]
```

---

### POST /api/agents/templates

创建自定义巡检模板。

**权限**: admin

**请求体**:

```json
{
  "id": "my_custom_check",
  "name": "自定义检查",
  "category": "custom",
  "description": "我的自定义巡检",
  "check_tools": "get_system_overview",
  "prompt_template": "请检查 {target} 的状态",
  "variables": [
    {"name": "target", "description": "检查目标", "default": "nginx"}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 模板唯一 ID |
| name | string | 是 | 显示名称 |
| check_tools | string | 是 | 使用的工具列表（逗号分隔） |
| prompt_template | string | 是 | 提示词模板（支持 `{变量名}` 占位符） |
| category | string | 否 | 分类，默认 `general` |
| description | string | 否 | 描述说明 |
| variables | array | 否 | 变量定义列表 |

**成功响应** `200`:

```json
{
  "ok": true,
  "id": "my_custom_check"
}
```

**失败响应** `409`: 模板 ID 已存在。

---

### DELETE /api/agents/templates/{template_id}

删除自定义巡检模板（内置模板不可删除）。

**权限**: admin

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 403 | 内置模板不可删除 |
| 404 | 模板不存在 |

---

### POST /api/agents/patrols/from-template

从模板创建新的巡检任务（实例化模板变量）。

**权限**: admin

**请求体**:

```json
{
  "template_id": "memory_leak_check",
  "id": "my_memory_check",
  "display_name": "内存泄漏监控",
  "interval_minutes": 120,
  "variables": {
    "process_names": "python,uvicorn,ollama"
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| template_id | string | 是 | 模板 ID |
| id | string | 否 | 新巡检任务 ID，默认自动生成 |
| display_name | string | 否 | 显示名称，默认使用模板名 |
| interval_minutes | int | 否 | 执行间隔（分钟），默认 60 |
| variables | object | 否 | 模板变量替换值 |

**成功响应** `200`:

```json
{
  "ok": true,
  "id": "my_memory_check",
  "display_name": "内存泄漏监控"
}
```

---

## 6. 故障报告

### GET /api/agents/fault-reports

获取故障报告列表（由巡检 Agent 自动生成）。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 20 | 返回最近 N 条 |
| status | string | `""` | 按状态过滤：`open` / `resolved`，空则返回全部 |

**成功响应** `200`:

```json
[
  {
    "id": "uuid",
    "detected_at": "2026-03-24T09:00:00",
    "source": "docker_health",
    "severity": "warning",
    "root_cause": "docker-worker-1 容器在过去 2 小时内重启 5 次",
    "status": "open"
  }
]
```

---

### GET /api/agents/fault-reports/{report_id}

获取故障报告详情（含完整分析和建议）。

**权限**: admin

**成功响应** `200`:

```json
{
  "id": "uuid",
  "detected_at": "2026-03-24T09:00:00",
  "source": "docker_health",
  "severity": "warning",
  "root_cause": "docker-worker-1 容器在过去 2 小时内重启 5 次",
  "status": "open",
  "affected_components": ["docker-worker-1", "Dify AI 平台"],
  "symptoms": ["容器频繁重启", "Celery Worker 任务积压"],
  "evidence": ["重启日志: OOMKilled", "内存限制: 2GB"],
  "immediate_actions": ["检查容器内存配置", "查看应用日志"],
  "long_term_solutions": ["增加内存限制", "优化 Worker 内存使用"],
  "similar_cases": [1, 2]
}
```

---

### PUT /api/agents/fault-reports/{report_id}/resolve

标记故障报告为已解决。

**权限**: admin

**成功响应** `200`:

```json
{
  "ok": true
}
```

---

## 7. 告警规则

### GET /api/agents/alerts/rules

获取所有告警规则。

**权限**: admin

**成功响应** `200`:

```json
[
  {
    "id": "cpu_high",
    "name": "CPU 使用率过高",
    "metric": "cpu",
    "operator": ">",
    "warning_threshold": 80.0,
    "critical_threshold": 95.0,
    "cooldown_minutes": 30,
    "notify": true,
    "enabled": true
  }
]
```

---

### POST /api/agents/alerts/rules

创建自定义告警规则。

**权限**: admin

**请求体**:

```json
{
  "id": "disk_data3",
  "name": "Data3 磁盘使用率过高",
  "metric": "disk_data3",
  "operator": ">",
  "warning_threshold": 80.0,
  "critical_threshold": 95.0,
  "cooldown_minutes": 60,
  "notify": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| id | string | 是 | 规则唯一 ID |
| name | string | 是 | 显示名称 |
| metric | string | 是 | 监控指标名 |
| operator | string | 否 | 比较运算符（`>` / `<` / `>=` / `<=`），默认 `>` |
| warning_threshold | float | 否 | 警告阈值 |
| critical_threshold | float | 否 | 严重阈值 |
| cooldown_minutes | int | 否 | 告警冷却时间（分钟），默认 60 |
| notify | bool | 否 | 是否发送 Telegram 通知，默认 `true` |

**成功响应** `200`:

```json
{
  "ok": true,
  "id": "disk_data3"
}
```

---

### PUT /api/agents/alerts/rules/{rule_id}

更新告警规则（部分更新，仅更新提供的字段）。

**权限**: admin

**请求体**: 支持 `name`、`metric`、`operator`、`warning_threshold`、`critical_threshold`、`cooldown_minutes`、`notify`、`enabled` 任意组合。

**成功响应** `200`:

```json
{
  "ok": true
}
```

---

### DELETE /api/agents/alerts/rules/{rule_id}

删除告警规则。

**权限**: admin

**成功响应** `200`:

```json
{
  "ok": true
}
```

---

### GET /api/agents/alerts/history

获取告警触发历史记录。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 50 | 返回最近 N 条 |

**成功响应** `200`:

```json
[
  {
    "id": 1,
    "rule_id": "cpu_high",
    "rule_name": "CPU 使用率过高",
    "severity": "warning",
    "current_value": 85.2,
    "message": "CPU 使用率 85.2% 超过警告阈值 80%",
    "notified": true,
    "created_at": "2026-03-24T09:30:00"
  }
]
```

---

## 8. 案例库

### GET /api/agents/fault-cases

搜索或列出故障案例（支持全文搜索）。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| q | string | `""` | 搜索关键词（模糊匹配标题/症状/根因/标签） |
| category | string | `""` | 按分类过滤 |
| limit | int | 30 | 返回最多 N 条 |

**成功响应** `200`:

```json
[
  {
    "id": 1,
    "title": "Celery Worker OOMKilled 频繁重启",
    "category": "docker",
    "symptoms": "docker-worker-1 容器频繁重启，日志显示 OOMKilled",
    "root_cause": "容器内存限制过低（2GB），任务处理大型文件时超出限制",
    "solution": "将内存限制提升至 8GB，并添加内存使用监控",
    "tags": "docker,oom,celery,dify",
    "source": "manual",
    "created_at": "2026-03-10T10:00:00"
  }
]
```

---

### POST /api/agents/fault-cases

手动录入故障案例到案例库。

**权限**: admin

**请求体**:

```json
{
  "title": "Nginx 502 Bad Gateway",
  "category": "network",
  "symptoms": "访问站点返回 502，nginx 日志显示 upstream 连接超时",
  "root_cause": "后端应用崩溃，端口未监听",
  "solution": "重启后端应用服务，检查启动日志排查崩溃原因",
  "tags": "nginx,502,upstream"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 故障标题 |
| category | string | 否 | 分类 |
| symptoms | string | 否 | 故障现象描述 |
| root_cause | string | 否 | 根本原因 |
| solution | string | 否 | 解决方案 |
| tags | string | 否 | 标签（逗号分隔） |

**成功响应** `200`:

```json
{
  "ok": true,
  "id": 3
}
```

---

### DELETE /api/agents/fault-cases/{case_id}

删除故障案例。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| case_id | 案例 ID（整数） |

**成功响应** `200`:

```json
{
  "ok": true
}
```

---

## 9. 事件记录

### GET /api/agents/events

获取 Agent 工具调用事件记录（用于审计 Agent 行为）。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 50 | 返回最近 N 条 |

**成功响应** `200`:

```json
[
  {
    "timestamp": "2026-03-24T10:30:05",
    "event_type": "tool_call",
    "tool_name": "get_system_overview",
    "tool_input": "{}",
    "risk_level": "safe",
    "username": "admin",
    "details": null
  },
  {
    "timestamp": "2026-03-24T10:30:10",
    "event_type": "tool_call",
    "tool_name": "execute",
    "tool_input": "{\"command\": \"systemctl restart nginx\"}",
    "risk_level": "danger",
    "username": "admin",
    "details": null
  }
]
```

工具风险级别：`safe`（只读工具）/ `caution`（轻度操作）/ `danger`（危险操作，supervised 模式下触发审批）。

---

## 10. Agent 配置

### GET /api/agents/settings

获取 Agent 当前配置和各 LLM 服务商状态。

**权限**: admin

**成功响应** `200`:

```json
{
  "default_model": "openrouter:deepseek/deepseek-chat",
  "patrol_model": "openrouter:deepseek/deepseek-chat",
  "shell_timeout": 30,
  "shell_max_output": 10000,
  "providers": [
    {
      "id": "openrouter",
      "name": "OpenRouter",
      "configured": true,
      "models": [
        {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat"}
      ]
    },
    {
      "id": "anthropic",
      "name": "Anthropic",
      "configured": false,
      "models": []
    }
  ]
}
```

---

### PUT /api/agents/settings

更新 Agent 模型配置（持久化到 `.env` 文件，无需重启服务）。

**权限**: admin

**请求体**（字段可选）:

```json
{
  "default_model": "anthropic:claude-opus-4-6",
  "patrol_model": "openrouter:deepseek/deepseek-chat"
}
```

**成功响应** `200`:

```json
{
  "ok": true,
  "default_model": "anthropic:claude-opus-4-6",
  "patrol_model": "openrouter:deepseek/deepseek-chat"
}
```

---

### POST /api/agents/settings/refresh-models/{provider_id}

刷新指定服务商的可用模型列表（支持 `openrouter` 和 `ollama`）。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| provider_id | 服务商 ID（如 `openrouter`、`ollama`） |

**成功响应** `200`:

```json
{
  "ok": true,
  "count": 120,
  "models": [
    {"id": "deepseek/deepseek-chat", "name": "DeepSeek Chat"}
  ]
}
```

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 404 | 未知服务商 ID |
| 500 | 刷新失败（网络错误、服务不可达等） |

---

### PUT /api/agents/settings/api-key/{provider_id}

更新指定服务商的 API Key（写入环境变量和 `.env` 文件，立即生效）。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| provider_id | 服务商 ID |

**请求体**:

```json
{
  "api_key": "sk-xxxxxxxxxxxx"
}
```

**成功响应** `200`:

```json
{
  "ok": true,
  "provider": "openrouter",
  "env_var": "OPENROUTER_API_KEY"
}
```

---

## 11. 管理接口

### GET /api/agents/admin/prompt

获取当前系统提示词（自定义提示词或默认提示词）。

**权限**: admin

**成功响应** `200`:

```json
{
  "content": "你是一个 Linux 服务器运维助手...",
  "is_custom": false
}
```

`is_custom: true` 表示当前使用的是保存在 `data/custom_prompt.txt` 的自定义提示词。

---

### PUT /api/agents/admin/prompt

保存自定义系统提示词，或重置为默认提示词。

**权限**: admin

**请求体**:

```json
{
  "content": "你是一个专注于安全合规的 Linux 服务器运维助手...",
  "reset": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| content | string | 新的提示词内容（`reset: false` 时使用） |
| reset | bool | `true` 则删除自定义文件，恢复默认提示词 |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "提示词已保存"
}
```

---

### GET /api/agents/admin/subagents

获取所有 SubAgent 配置，以及可用工具列表和服务商信息。

**权限**: admin

**成功响应** `200`:

```json
{
  "subagents": [
    {
      "name": "researcher",
      "description": "联网搜索获取最新信息",
      "system_prompt": "你是一个专业的信息检索助手...",
      "tools": ["web_search", "think"],
      "model": null
    }
  ],
  "available_tools": ["web_search", "think", "get_container_logs", "get_service_logs", "get_system_overview"],
  "providers": [...]
}
```

---

### PUT /api/agents/admin/subagents

保存全部 SubAgent 配置，或重置为默认配置。

**权限**: admin

**请求体**:

```json
{
  "subagents": [
    {
      "name": "researcher",
      "description": "联网搜索",
      "system_prompt": "...",
      "tools": ["web_search", "think"],
      "model": "openrouter:deepseek/deepseek-chat"
    }
  ],
  "reset": false
}
```

| 字段 | 说明 |
|------|------|
| subagents | SubAgent 配置列表（完全替换） |
| reset | `true` 则删除自定义配置，恢复默认 SubAgent |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "已保存 1 个 SubAgent"
}
```

---

### GET /api/agents/admin/memory

获取 `data/agent-memory.md` 运行时长期记忆文件内容。

**权限**: admin

**成功响应** `200`:

```json
{
  "content": "# 服务器信息\n\n主机名: system-NF5468M6\n...",
  "path": "/home/zhengxiaodong/scripts/server-hub/data/agent-memory.md"
}
```

---

### PUT /api/agents/admin/memory

保存修改后的 `data/agent-memory.md` 长期记忆内容。

**权限**: admin

**请求体**:

```json
{
  "content": "# 服务器信息\n\n主机名: system-NF5468M6\n内存: 503GB\n..."
}
```

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "记忆已保存"
}
```

---

## 12. 异步任务

### GET /api/agents/async-tasks

获取后台异步任务列表（由异步 SubAgent 创建）。

**权限**: admin

**成功响应** `200`:

```json
[
  {
    "id": "uuid",
    "subagent": "researcher",
    "status": "running",
    "created_at": "2026-03-25T10:00:00",
    "query": "搜索 Docker OOM 解决方案"
  }
]
```

---

### GET /api/agents/async-tasks/{task_id}

获取异步任务详情（含结果）。

**权限**: admin

**成功响应** `200`:

```json
{
  "id": "uuid",
  "subagent": "researcher",
  "status": "completed",
  "result": "...",
  "created_at": "2026-03-25T10:00:00",
  "completed_at": "2026-03-25T10:01:30"
}
```

---

### DELETE /api/agents/async-tasks/{task_id}

取消正在运行的异步任务。

**权限**: admin

**成功响应** `200`:

```json
{
  "ok": true
}
```

---

## 13. WebSocket 终端

### WS /api/agents/ws/terminal

基于 PTY（伪终端）的全功能 WebSocket 终端，通过 `pty.fork()` 创建真实 shell 进程。

**协议**: WebSocket

**连接地址**: `ws://<host>/api/agents/ws/terminal`

**认证**: WebSocket 握手时从 Cookie 读取 `access_token`，验证 JWT 且要求 `role=admin`。认证失败分别返回关闭码 `4001`（未认证）或 `4003`（权限不足）。

**消息格式**:

- **客户端 → 服务端**: 发送字符串，直接写入终端（键盘输入）
- **服务端 → 客户端**: 发送字符串，终端输出内容（ANSI 转义序列）

**终端调整大小**（两种格式）:

```
\x1b[resize:80,24]
```

或 JSON 格式:

```json
{"type": "resize", "cols": 80, "rows": 24}
```

格式：`\x1b[resize:{cols},{rows}]`，`cols` 为列数，`rows` 为行数。

**空闲超时**: 服务端每 30 秒检测终端空闲状态。超时后自动发送黄色警告消息并关闭终端连接：

```
[ServerHub] 终端已空闲超时，自动关闭。
```

**断开连接**: 客户端关闭 WebSocket 连接后，服务端自动关闭 PTY 进程。

---

## 14. UI 组件交互

### POST /ui/action

处理前端 UI 组件（chart/table/form/card）的用户交互事件回调。当前为 MVP 实现，记录交互日志。后续可扩展为将交互注入 Agent 对话上下文。

**权限**: 任意已登录用户（user / admin）

**请求体**:

```json
{
  "component_id": "cpu-chart-1",
  "component_type": "chart",
  "action_id": "refresh-btn",
  "action_type": "refresh",
  "payload": {},
  "conversation_id": "",
  "run_id": ""
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| component_id | string | 是 | 组件唯一标识（1-128 字符，`[a-zA-Z0-9_-]+`） |
| component_type | string | 是 | 组件类型：`chart` / `table` / `form` / `card` |
| action_id | string | 是 | 操作标识（1-128 字符，`[a-zA-Z0-9_-]+`） |
| action_type | string | 是 | 操作类型：`submit` / `reset` / `agent` / `download` / `refresh` / `navigate` |
| payload | object | 否 | 附带数据（JSON 序列化后不超过 10KB） |
| conversation_id | string | 否 | 关联的对话 ID |
| run_id | string | 否 | 关联的运行 ID |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "已处理 refresh-btn 操作",
  "data": {
    "component_id": "cpu-chart-1",
    "action_id": "refresh-btn"
  }
}
```

**输入验证**（Pydantic）:

- `component_id` 和 `action_id` 必须匹配 `^[a-zA-Z0-9_-]+$`，长度 1-128
- `payload` 序列化后不得超过 10KB（10240 bytes），超出返回 `422`
- `component_type` 和 `action_type` 为枚举值，不在范围内返回 `422`

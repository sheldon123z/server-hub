# Pipeline 编排引擎设计规格

> 日期: 2026-04-06
> 状态: Approved
> 方案: YAML 定义 + LangGraph 执行（方案 C）

## 一、定位与边界

Pipeline 是可编排的多步骤工作流引擎，将"单次剧本执行"升级为"长程流水线"。支持条件分支、并行执行、人工审批、AI 决策。

### 与现有系统的关系

| 现有系统 | 关系 | 说明 |
|---------|------|------|
| Playbook | 被编排 | Pipeline 的一种 step 类型，复用剧本执行引擎 |
| Agent (Deep Agents) | 执行底座 | Pipeline 编译为 LangGraph StateGraph 运行 |
| Approval | 复用 | Pipeline 审批节点复用 LangGraph interrupt 机制 |
| Notification | 复用 | Pipeline 通知节点复用已有三渠道通知 |
| RBAC | 集成 | Pipeline 操作权限接入 RBAC 体系 |
| Cron 调度 | 扩展 | Pipeline 可由 Cron 定时触发 |
| Alert 告警 | 联动 | 告警规则可触发 Pipeline 自动执行 |

### 不做的事

- 不替代 Playbook（简单任务继续用剧本）
- 不替代 Agent 对话（交互式运维继续用聊天）

## 二、Pipeline 生命周期

```
创建 → 验证 → 发布 → 触发 → 执行 → 完成/失败
 ↑                          ↓
 └── 编辑/版本迭代 ←── 复盘分析
```

1. **创建** — YAML 编辑或模板向导生成，草稿状态
2. **验证** — 编译检查（语法、step 引用、参数完整性、循环检测）
3. **发布** — 标记 enabled，可被触发。每次修改自动递增版本号（v1, v2, v3...），历史版本可回溯
4. **触发** — 4 种触发源：手动 / Cron 定时 / 告警联动 / API 调用
5. **执行** — LangGraph 驱动，实时 SSE 推送进度，断点恢复
6. **复盘** — 执行历史、step 级耗时分析、失败归因、AI 自动总结

## 三、数据模型

### Pipeline 定义（YAML 格式）

```yaml
name: server-init
display_name: 服务器初始化流水线
description: 新机器上架全流程
version: 1
max_concurrent_runs: 1
timeout: 3600  # 整体超时（秒）

trigger:
  type: manual  # manual | cron | alert | api
  # cron: "0 2 * * *"
  # alert_rule_id: "rule-xxx"

params:
  - name: target_server
    type: string
    required: true
    description: 目标服务器 ID
  - name: deploy_services
    type: array
    default: ["nginx", "docker"]
  - name: ssh_credential
    type: secret
    description: SSH 凭据（Fernet 加密存储）

steps:
  - id: check-connectivity
    type: ssh
    name: 连通性检查
    host: "{{params.target_server}}"
    command: "echo ok"
    timeout: 30
    on_failure: abort

  - id: system-setup
    type: playbook
    name: 系统基础配置
    playbook_id: "system-init-template"
    params:
      server_id: "{{params.target_server}}"

  - id: install-services
    type: parallel
    name: 并行安装服务
    branches:
      - id: install-docker
        type: shell
        command: "curl -fsSL https://get.docker.com | sh"
      - id: install-nginx
        type: shell
        command: "apt-get install -y nginx"

  - id: ai-verify
    type: agent
    name: AI 健康验证
    prompt: "检查 {{params.target_server}} 的服务状态，确认所有组件正常运行"
    model: "fast"
    output_format: json  # 可选，要求 AI 返回结构化输出

  - id: decide-action
    type: condition
    name: 判断是否需要人工审批
    expression: "{{steps.ai-verify.output.confidence}} >= 0.9"
    on_true: notify-done
    on_false: admin-approve

  - id: admin-approve
    type: approval
    name: 管理员确认上线
    assignee: admin
    timeout: 3600
    on_timeout: abort  # abort | auto_approve

  - id: notify-done
    type: notify
    channel: telegram
    message: "服务器 {{params.target_server}} 初始化完成"
```

### 数据库表

#### pipelines — Pipeline 定义

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| name | TEXT UNIQUE | 唯一标识名 |
| display_name | TEXT | 中文显示名 |
| description | TEXT | 描述 |
| yaml_content | TEXT | 原始 YAML |
| steps_json | TEXT | 编译后的结构化 JSON（节点+边+坐标，为 V2 拖拽编辑器预留） |
| params_json | TEXT | 参数定义 JSON |
| trigger_json | TEXT | 触发配置 JSON |
| version | INTEGER | 版本号，每次修改自增 |
| max_concurrent_runs | INTEGER | 最大并发数，默认 1 |
| timeout | INTEGER | 整体超时（秒） |
| enabled | INTEGER | 是否启用 |
| created_by | TEXT | 创建人 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |

#### pipeline_runs — 执行实例

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| pipeline_id | TEXT FK | 关联 Pipeline |
| pipeline_version | INTEGER | 本次运行对应的 Pipeline 版本 |
| status | TEXT | pending / running / paused / completed / failed / cancelled |
| params_json | TEXT | 本次运行的参数值 |
| current_step_id | TEXT | 当前执行到的 step |
| steps_state_json | TEXT | 每个 step 的状态和输出 |
| trigger_type | TEXT | manual / cron / alert / api |
| started_at | TIMESTAMP | 开始时间 |
| completed_at | TIMESTAMP | 完成时间 |
| started_by | TEXT | 触发人 |
| error | TEXT | 错误信息 |
| langgraph_thread_id | TEXT | LangGraph checkpoint 关联 |
| summary | TEXT | AI 生成的执行摘要 |

#### pipeline_step_logs — Step 执行日志

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增 |
| run_id | TEXT FK | 关联 Run |
| step_id | TEXT | step 标识 |
| step_type | TEXT | step 类型 |
| status | TEXT | pending / running / completed / failed / skipped |
| started_at | TIMESTAMP | 开始时间 |
| completed_at | TIMESTAMP | 完成时间 |
| input_json | TEXT | 输入（模板解析后） |
| output_json | TEXT | 输出 |
| error | TEXT | 错误信息 |
| duration_ms | INTEGER | 耗时 |

索引：`(run_id, step_id)`, `(run_id, started_at)`, `(pipeline_id, status)`

## 四、执行引擎

### 编译流程

```
YAML 文本
  ↓ parse_pipeline_yaml() — 语法解析 + schema 校验
PipelineDefinition (Pydantic)
  ↓ validate_pipeline() — 循环检测 + step 引用检查 + 参数完整性
  ↓ compile_to_langgraph() — 动态构建图
LangGraph StateGraph
  ↓ 运行时
AsyncSqliteSaver checkpoint (断点恢复)
```

### Pipeline State

| 字段 | 说明 |
|------|------|
| run_id | 运行实例 ID |
| pipeline_id | Pipeline 定义 ID |
| params | 用户传入的参数 |
| step_outputs | `{step_id: output}` — 步骤间数据传递 |
| current_step | 当前执行的 step |
| status | 运行状态 |
| error | 错误信息 |

### Step → LangGraph 节点映射

| Step 类型 | 节点行为 | 复用的基础设施 |
|-----------|---------|--------------|
| shell | `SafeLocalShellBackend.execute()` | 沙箱 + 审计日志 |
| ssh | `tofu_connect()` + `conn.run()` | TOFU + 凭据系统 |
| playbook | `playbook_execute()` | 剧本执行引擎 |
| http | `httpx.AsyncClient` 请求 | — |
| agent | `create_deep_agent()` + `ainvoke()` | Deep Agents 框架 |
| approval | `interrupt_before` 节点 | LangGraph 原生中断 |
| condition | `conditional_edges` | LangGraph 原生条件路由 |
| parallel | `Send()` API + join 节点 | LangGraph 原生并行 |
| delay | `asyncio.sleep()` + checkpoint | — |
| notify | `send_notification()` | 三渠道通知系统 |

### 模板变量解析

- `{{params.target_server}}` → 运行参数
- `{{steps.diagnose.output}}` → 前序步骤输出
- `{{steps.diagnose.output.recommended_playbook}}` → JSON 深度取值
- `{{steps.diagnose.exit_code}}` → 退出码
- `{{run.id}}` / `{{run.started_at}}` → 运行元数据
- `{{trigger.alert_id}}` → 触发上下文

所有 step 的字符串字段在执行前经过模板解析。`type: secret` 参数日志中脱敏为 `***`。

## 五、触发系统

| 触发方式 | 机制 | 典型场景 |
|---------|------|---------|
| 手动 | 前端点击"运行"，填写参数 | 服务器初始化 |
| 定时 (Cron) | 复用已有 Cron 调度器，到期自动创建 run | 日常巡检 |
| 告警联动 | 告警规则触发时查找绑定的 Pipeline，注入告警上下文 | 故障自愈 |
| API 调用 | `POST /api/pipelines/{id}/run` + Bearer Token | CI/CD 集成 |

### 并发控制

每个 Pipeline 的 `max_concurrent_runs`（默认 1）控制同时运行数。超限时排队（FIFO）或拒绝（可配）。防止同一 Pipeline 重复触发。

## 六、错误处理与恢复

### 第一层 — Step 级 on_failure

| 策略 | 行为 |
|------|------|
| abort（默认） | 整条 Pipeline 标记失败，停止 |
| skip | 跳过此步，继续下一步 |
| retry | 指数退避重试（retry_count 默认 3，retry_delay 默认 5s） |
| notify_continue | 发通知但继续执行 |
| goto:{step_id} | 跳转到指定步骤（故障恢复路径） |

### 第二层 — Run 级恢复

Pipeline 运行失败后，管理员可从失败的 step 处重新执行。利用 LangGraph checkpoint 恢复到失败前的状态，无需从头运行。

### 第三层 — 全局超时

每个 Pipeline 可配置 `timeout`（整体超时，秒），防止无限挂起。超时后标记 failed，触发 on_failure 策略。

## 七、AI 深度融合

| 能力 | 触发点 | 说明 |
|------|-------|------|
| AI 诊断决策 | `type: agent` step | Pipeline 中嵌入 AI 节点做分析和推荐 |
| 智能路由 | condition 引用 agent 输出 | AI 输出 JSON，condition 据此路由 |
| 自然语言→YAML | 创建向导"AI 生成"按钮 | 用户描述需求，Agent 生成 Pipeline YAML |
| 执行摘要 | Pipeline 完成后自动触发 | AI 总结本次运行的关键发现和建议 |
| 失败分析 | Pipeline 失败后自动触发 | AI 分析失败原因，推荐修复方案 |
| Pipeline 审查 | 管理面板"AI 审查"按钮 | AI 审查 YAML，建议改进 |

Agent step 支持 `output_format: json`，要求 AI 返回结构化 JSON，后续 step 可通过 `{{steps.x.output.field}}` 引用具体字段。

## 八、安全模型

| 操作 | 权限要求 |
|------|---------|
| 查看 Pipeline / 运行历史 | `get_current_user` |
| 创建/编辑/删除 Pipeline | `require_role("admin")` |
| 手动触发运行 | `require_role("admin")` |
| 审批操作 | 审批节点指定的 assignee |
| Shell/SSH step | 走沙箱 + 命令黑名单 + 审计日志 |
| Agent step | 走 safety.py 安全层 |

Secret 参数通过 Fernet 凭据系统加密存储，执行时解密注入，日志中脱敏。

## 九、可观测性

### SSE 事件类型

| 事件 | 数据 |
|------|------|
| step_start | step_id, step_name, step_type |
| step_output | step_id, output_preview |
| step_complete | step_id, status, duration_ms |
| step_failed | step_id, error, on_failure_action |
| approval_required | step_id, assignee, timeout |
| pipeline_complete | run_id, status, total_duration |

### 统计仪表盘

- Pipeline 级：成功率、平均耗时、触发频率
- Step 级：最慢步骤、最常失败步骤
- 全链路审计追踪

## 十、API 端点

### Pipeline 定义管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/pipelines | 列表（?enabled=true 过滤） |
| POST | /api/pipelines | 创建（提交 YAML，后端编译验证） |
| GET | /api/pipelines/{id} | 详情（YAML + 编译后图结构） |
| PUT | /api/pipelines/{id} | 更新 YAML（自动递增版本） |
| DELETE | /api/pipelines/{id} | 删除 |
| POST | /api/pipelines/{id}/validate | 仅验证 YAML |
| GET | /api/pipelines/{id}/mermaid | Mermaid 流程图代码 |

### 执行管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/pipelines/{id}/run | 触发执行（body: params） |
| GET | /api/pipelines/runs | 运行列表（?status=running 过滤） |
| GET | /api/pipelines/runs/{run_id} | 运行详情（含每步状态） |
| POST | /api/pipelines/runs/{run_id}/cancel | 取消执行 |
| POST | /api/pipelines/runs/{run_id}/approve | 审批通过 |
| POST | /api/pipelines/runs/{run_id}/reject | 审批拒绝 |
| POST | /api/pipelines/runs/{run_id}/retry-from/{step_id} | 从失败步重试 |
| GET | /api/pipelines/runs/{run_id}/logs | Step 日志 |
| SSE | /api/pipelines/runs/{run_id}/stream | 实时进度推送 |

## 十一、前端

### 页面结构

三栏布局（与 Agent 页面风格一致）：

- **左栏** — Pipeline 列表 + 新建按钮
- **中栏** — 详情（3 个 Tab：编辑 / 预览 / 历史）
- **右栏** — 运行面板（实时进度 + 审批操作 + 历史运行）

### 编辑 Tab

- Monaco Editor（YAML mode）
- 实时校验（debounce 500ms 调用 /validate）
- AI 生成按钮（自然语言→YAML）
- 保存按钮（版本自增）

### 预览 Tab

- Mermaid 流程图（从 /mermaid 端点渲染）
- 参数定义表格
- "运行"按钮 → 参数填写 modal → 触发

### 历史 Tab

- 运行列表（状态/触发方式/耗时/操作人）
- 展开 → step 级日志 + 耗时可视化

### 运行面板（右栏）

- SSE 驱动的 step 进度条（每步一行）
- 审批节点：通过/拒绝按钮
- Agent 节点：AI 输出展示
- 失败节点：错误详情 + "从此步重试"按钮

### 创建向导

5 个模板 + AI 生成：
- 服务器初始化（连通→配置→安装→AI验证→审批→通知）
- 故障自愈（AI诊断→审批→修复→验证→通知）
- 日常巡检（并行检查→AI汇总→条件分支→通知）
- 安全扫描（合规→端口→SSH审计→AI报告→条件→审批）
- 空白 Pipeline
- AI 生成（自然语言描述→YAML）

### V2 拖拽编辑器预留

`steps_json` 存储结构化节点+边+坐标。V1 由 YAML 编译生成（坐标自动布局），V2 可从拖拽界面修改后反编译为 YAML。数据模型无需变更。

## 十二、模块结构

```
modules/pipelines/
├── __init__.py         — MODULE_INFO
├── models.py           — Pydantic 模型
├── compiler.py         — YAML → PipelineDefinition → LangGraph StateGraph
├── executor.py         — 运行管理（触发/取消/审批/重试）
├── steps/              — 10 种 step 执行器
│   ├── __init__.py     — StepExecutor 基类 + 注册表
│   ├── shell.py
│   ├── ssh.py
│   ├── playbook.py
│   ├── agent.py
│   ├── approval.py
│   ├── condition.py
│   ├── parallel.py
│   ├── notify.py
│   ├── http.py
│   └── delay.py
├── triggers.py         — 触发系统（Cron/Alert/API 集成）
├── templates.py        — 4+1 内置模板定义
├── routes.py           — API 端点
└── services.py         — 业务逻辑（CRUD + 统计 + 版本管理）
```

## 十三、内置模板

### 1. 服务器初始化

```yaml
steps:
  - {id: check, type: ssh, name: 连通性检查}
  - {id: setup, type: playbook, name: 系统配置}
  - {id: install, type: parallel, name: 并行安装服务}
  - {id: verify, type: agent, name: AI 健康验证}
  - {id: approve, type: approval, name: 管理员确认}
  - {id: notify, type: notify, name: 完成通知}
```

### 2. 故障自愈

```yaml
trigger: {type: alert}
steps:
  - {id: diagnose, type: agent, name: AI 诊断根因}
  - {id: approve, type: approval, name: 确认修复方案}
  - {id: fix, type: playbook, name: 执行修复}
  - {id: wait, type: delay, name: 等待恢复, seconds: 30}
  - {id: verify, type: agent, name: AI 验证恢复}
  - {id: check-ok, type: condition, name: 是否恢复}
  - {id: notify, type: notify, name: 结果通知}
```

### 3. 日常巡检

```yaml
trigger: {type: cron, cron: "0 8 * * *"}
steps:
  - id: checks
    type: parallel
    branches:
      - {id: resource, type: shell, name: 资源检查}
      - {id: security, type: playbook, name: 安全扫描}
      - {id: logs, type: agent, name: 日志分析}
  - {id: summarize, type: agent, name: AI 汇总报告}
  - {id: has-issue, type: condition, name: 是否有异常}
  - {id: notify, type: notify, name: 通知}
```

### 4. 安全扫描

```yaml
steps:
  - {id: compliance, type: playbook, name: 合规检查}
  - {id: ports, type: shell, name: 端口扫描}
  - {id: ssh-audit, type: ssh, name: SSH 审计}
  - {id: report, type: agent, name: AI 安全报告}
  - {id: severity, type: condition, name: 严重性判断}
  - {id: approve, type: approval, name: 高风险审批}
  - {id: fix, type: playbook, name: 自动修复}
  - {id: notify, type: notify, name: 通知}
```

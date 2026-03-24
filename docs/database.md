# 数据库 Schema

ServerHub 使用三个 SQLite 数据库文件，均在 `data/` 目录下（`.gitignore` 已排除）。

---

## 三个数据库文件

| 文件 | 说明 | 管理方式 |
|------|------|---------|
| `data/server-hub.db` | 主数据库（用户、监控、审计、agent 相关）| `database.py:init_tables()` 自动建表 |
| `data/agent-checkpoints.db` | LangGraph checkpoint（agent 会话状态持久化）| LangGraph AsyncSqliteSaver 管理 |
| `data/agent-store.db` | Agent 结构化长期存储（namespace+KV）| Deep Agents AsyncSqliteStore 管理 |

---

## 主数据库：server-hub.db

应用启动时由 `database.py:init_tables()` 自动创建所有表（`CREATE TABLE IF NOT EXISTS`）。

共 15 个表（含 1 个 FTS5 虚拟表）。

---

### panel_users — 面板用户

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| username | TEXT UNIQUE NOT NULL | 登录用户名 |
| hashed_password | TEXT NOT NULL | bcrypt 哈希密码 |
| display_name | TEXT DEFAULT '' | 显示名称 |
| role | TEXT NOT NULL DEFAULT 'user' | 角色：admin / user |
| disabled | INTEGER DEFAULT 0 | 是否禁用（0/1）|
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| last_login | TIMESTAMP | 最后登录时间 |

**用途**：JWT 认证系统的用户表，存储 Web 管理面板的账号信息。

---

### metrics — 监控指标

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| timestamp | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 采集时间 |
| metric_type | TEXT NOT NULL | 指标类型，如 `all`、`cpu`、`memory` |
| value_json | TEXT NOT NULL | JSON 格式的指标数据 |

**索引**：`idx_metrics_type_time`（metric_type, timestamp）

**用途**：
- 仪表盘历史图表（监控折线图）
- `analyze_resource_trend` 工具的数据源（查询 `metric_type='all'` 的历史记录）
- 基线偏离告警的基础数据（`check_baseline_deviation` 使用）

**数据结构示例**（`metric_type='all'` 的 `value_json`）：
```json
{
  "cpu": {"overall_percent": 12.3, "count": 160},
  "memory": {
    "ram": {"total": 540278079488, "used": 245760000000, "percent": 45.5},
    "swap": {"total": 8589934592, "used": 0, "percent": 0.0}
  },
  "gpu": {"available": true, "util": 87, "mem_used": 67584, "mem_total": 81920, "temp": 72},
  "disk": [{"mountpoint": "/", "device": "sdb2", "total": 3758096384, "used": 1435893760, "percent": 38.2}]
}
```

---

### audit_log — 操作审计日志

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| timestamp | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 操作时间 |
| username | TEXT | 操作用户名 |
| action | TEXT NOT NULL | 操作类型（如 `docker.restart`）|
| target | TEXT | 操作对象（如容器名）|
| details | TEXT | 详细信息（JSON 格式）|
| ip_address | TEXT | 客户端 IP |
| success | INTEGER DEFAULT 1 | 是否成功（0/1）|

**索引**：`idx_audit_time`（timestamp）

**用途**：所有 POST/PUT/DELETE `/api/*` 请求通过审计中间件自动记录。

---

### notifications — 通知记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| timestamp | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 发送时间 |
| channel | TEXT DEFAULT 'telegram' | 通知渠道 |
| message | TEXT NOT NULL | 消息内容 |
| success | INTEGER DEFAULT 1 | 是否发送成功 |
| error | TEXT | 失败原因 |

**用途**：记录所有 Telegram 通知的发送历史，便于追踪告警是否送达。

---

### agent_conversations — Agent 对话线程

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 对话 ID（UUID）|
| title | TEXT DEFAULT '新对话' | 对话标题 |
| username | TEXT NOT NULL | 创建者用户名 |
| safety_mode | TEXT DEFAULT 'supervised' | 安全模式：supervised / autonomous |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 最后更新时间 |
| message_count | INTEGER DEFAULT 0 | 消息数量 |
| is_archived | INTEGER DEFAULT 0 | 是否已归档 |

**索引**：`idx_conv_user`（username, updated_at）

**用途**：对话列表管理，前端侧边栏展示对话历史。

---

### agent_events — Agent 事件日志

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| conversation_id | TEXT | 关联的对话 ID |
| timestamp | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 事件时间 |
| event_type | TEXT NOT NULL | 事件类型（message/tool_call/tool_result 等）|
| tool_name | TEXT | 工具名称（tool_call 事件）|
| tool_input | TEXT | 工具输入参数（JSON）|
| tool_output | TEXT | 工具输出（截断存储）|
| risk_level | TEXT | 风险级别（safe/moderate/danger）|
| username | TEXT | 操作用户 |
| details | TEXT | 附加信息 |

**索引**：`idx_events_conv`（conversation_id, timestamp）

**用途**：追踪每次对话中的完整工具调用链，用于审计和调试。

---

### agent_approvals — Agent 待审批队列

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 审批请求 ID |
| conversation_id | TEXT NOT NULL | 关联的对话 ID |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| tool_name | TEXT NOT NULL | 需要审批的工具名 |
| tool_input | TEXT NOT NULL | 工具参数（JSON）|
| risk_level | TEXT NOT NULL | 风险级别 |
| description | TEXT | 审批描述 |
| status | TEXT DEFAULT 'pending' | 状态：pending / approved / rejected |
| resolved_at | TIMESTAMP | 审批时间 |
| resolved_by | TEXT | 审批用户名 |

**索引**：`idx_approvals_status`（status, created_at）

**用途**：supervised 模式下危险操作的审批队列，通过 SSE 实时推送到前端。

---

### agent_patrol_tasks — Agent 巡检任务

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 任务 ID（如 `memory_check`）|
| display_name | TEXT NOT NULL | 显示名称 |
| description | TEXT | 任务描述 |
| interval_minutes | INTEGER DEFAULT 60 | 执行间隔（分钟）|
| enabled | INTEGER DEFAULT 1 | 是否启用 |
| check_tools | TEXT NOT NULL | 建议使用的工具（逗号分隔）|
| prompt | TEXT NOT NULL | 巡检提示词 |
| last_run | TIMESTAMP | 最后执行时间 |
| last_status | TEXT | 最后执行状态（ok/warning/critical/error）|
| last_report | TEXT | 最后执行报告（截断到 5000 字符）|

**用途**：巡检调度器（`_patrol_loop`）每 60 秒查询此表，判断哪些任务需要执行。

---

### agent_patrol_history — Agent 巡检历史

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| task_id | TEXT NOT NULL | 关联的巡检任务 ID |
| timestamp | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 执行时间 |
| status | TEXT NOT NULL | 执行状态 |
| report | TEXT | 巡检报告文本（截断到 5000 字符）|
| report_json | TEXT | 结构化报告 JSON |
| alert_sent | INTEGER DEFAULT 0 | 是否发送了告警 |
| duration_seconds | REAL | 执行耗时（秒）|

**索引**：`idx_patrol_hist`（task_id, timestamp）

**用途**：前端巡检历史面板展示，`report_json` 字段用于告警规则引擎提取指标。

---

### alert_rules — 告警规则

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 规则 ID（如 `mem_high`）|
| name | TEXT NOT NULL | 规则名称 |
| metric | TEXT NOT NULL | 指标键名（如 `memory_percent`）|
| operator | TEXT NOT NULL DEFAULT '>' | 比较运算符 |
| warning_threshold | REAL | warning 阈值 |
| critical_threshold | REAL | critical 阈值 |
| cooldown_minutes | INTEGER DEFAULT 60 | 冷却时间（分钟）|
| notify | INTEGER DEFAULT 1 | 是否发送通知 |
| enabled | INTEGER DEFAULT 1 | 是否启用 |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| rule_type | TEXT DEFAULT 'threshold' | 规则类型：threshold / baseline（兼容旧版 ALTER 添加）|
| baseline_window_hours | INTEGER DEFAULT 168 | 基线窗口（小时，仅 baseline 类型）|
| stddev_multiplier | REAL DEFAULT 3.0 | 标准差倍数（仅 baseline 类型）|

**用途**：可配置的告警规则，通过 `evaluate_rules()` 评估。

---

### alert_history — 告警历史

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| rule_id | TEXT | 关联的规则 ID |
| severity | TEXT NOT NULL | 告警严重级别（warning/critical）|
| current_value | REAL | 触发时的指标值 |
| message | TEXT | 告警消息文本 |
| notified | INTEGER DEFAULT 0 | 是否已发送 Telegram 通知 |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 触发时间 |

**索引**：`idx_alert_hist_rule`（rule_id, created_at）

**用途**：Cooldown 去重机制依赖此表（查询冷却期内是否已有记录）。

---

### patrol_templates — 巡检模板

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 模板 ID（如 `tpl_memory`）|
| name | TEXT NOT NULL | 模板名称 |
| category | TEXT DEFAULT 'general' | 分类：performance/availability/security/general |
| description | TEXT | 模板描述 |
| check_tools | TEXT NOT NULL | 建议工具（逗号分隔）|
| prompt_template | TEXT NOT NULL | 提示词模板（含 `{variable}` 占位符）|
| variables | TEXT | 变量定义（JSON 数组）|
| report_schema | TEXT | 报告 Schema（预留字段）|
| is_builtin | INTEGER DEFAULT 0 | 是否内置模板 |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**variables 字段格式**：
```json
[
  {"name": "warning_threshold", "type": "number", "default": 85, "description": "告警阈值(%)"}
]
```

---

### fault_reports — 故障诊断报告

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 报告 ID（uuid4）|
| detected_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 检测时间 |
| source | TEXT | 来源（如 `patrol:memory_check`）|
| severity | TEXT | 严重级别 |
| affected_components | TEXT | 受影响组件（JSON 数组）|
| symptoms | TEXT | 症状列表（JSON 数组）|
| root_cause | TEXT | 根本原因分析 |
| evidence | TEXT | 证据列表（JSON 数组）|
| immediate_actions | TEXT | 紧急处置步骤（JSON 数组）|
| long_term_solutions | TEXT | 长期修复方案（JSON 数组）|
| similar_cases | TEXT | 相似案例（预留）|
| status | TEXT DEFAULT 'open' | 状态：open / resolved |
| resolved_at | TIMESTAMP | 解决时间 |

**索引**：`idx_fault_reports_status`（status, detected_at）

---

### fault_cases — 故障案例库

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| title | TEXT NOT NULL | 案例标题 |
| category | TEXT | 分类（memory/docker/service/network/security/gpu/general）|
| symptoms | TEXT | 症状描述 |
| root_cause | TEXT | 根本原因 |
| solution | TEXT | 解决方案 |
| tags | TEXT | 标签（逗号分隔）|
| source | TEXT DEFAULT 'manual' | 来源：manual（手动）/ auto（诊断自动录入）|
| source_id | TEXT | 来源 ID（自动录入时为 fault_report ID）|
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**注意**：`fault_cases_fts` 是此表的 FTS5 全文搜索虚拟表，在 `executescript` 之外单独创建。

---

### assets — 资产台账

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | 资产 ID |
| type | TEXT NOT NULL | 类型：service/container/compose/port/storage |
| name | TEXT NOT NULL | 资产名称 |
| status | TEXT DEFAULT 'unknown' | 状态 |
| properties | TEXT | 属性（JSON）|
| dependencies | TEXT | 依赖关系（JSON 数组）|
| is_manual | INTEGER DEFAULT 0 | 是否手动添加 |
| last_seen | TIMESTAMP | 最后发现时间 |
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 首次发现时间 |

**索引**：`idx_assets_type`（type）

---

### cron_job_log — 定时任务变更日志

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK AUTOINCREMENT | 自增主键 |
| cron_user | TEXT NOT NULL | 定时任务所属用户 |
| schedule | TEXT NOT NULL | cron 表达式 |
| command | TEXT NOT NULL | 执行命令 |
| comment | TEXT | 注释 |
| created_by | TEXT | 操作者（agent 或用户名）|
| created_at | TIMESTAMP DEFAULT CURRENT_TIMESTAMP | 操作时间 |
| action | TEXT NOT NULL | 操作类型（create/modify/delete/toggle）|

**索引**：`idx_cron_job_log_user`（cron_user）

---

## FTS5 虚拟表

### fault_cases_fts

FTS5（Full-Text Search 5）全文搜索虚拟表，基于 `fault_cases` 内容表。

```sql
CREATE VIRTUAL TABLE fault_cases_fts USING fts5(
    title, symptoms, root_cause, solution, tags,
    content=fault_cases,
    content_rowid=id
)
```

**用途**：`search_fault_cases` 工具优先使用 FTS5 搜索，支持 BM25 排序。FTS5 不可用时降级为 LIKE 查询。

**更新时机**：`save_fault_case` 工具和故障诊断自动录入时同步更新。

---

## 数据库初始化

### 兼容旧版本

`init_tables()` 使用 `ALTER TABLE ADD COLUMN` 为旧版数据库添加新列（新版若列已存在则忽略）：

```python
# alert_rules 表的基线检测相关列
for col, default in [
    ("rule_type", "'threshold'"),
    ("baseline_window_hours", "168"),
    ("stddev_multiplier", "3.0")
]:
    try:
        await db.execute(f"SELECT {col} FROM alert_rules LIMIT 0")
    except Exception:
        await db.execute(f"ALTER TABLE alert_rules ADD COLUMN {col} DEFAULT {default}")
```

### 连接配置

```python
await db.execute("PRAGMA journal_mode=WAL")   # WAL 模式，提高并发读写性能
await db.execute("PRAGMA foreign_keys=ON")    # 启用外键约束
```

**单例模式**：`get_db()` 返回全局单例连接，配合 `asyncio.Lock` 防止并发初始化。

# 变更日历 API

运维变更记录管理模块，提供变更事件 CRUD、冻结窗口管理和变更统计聚合。

**路由前缀**: `/api/changelog`
**模块路径**: `modules/changelog/`
**最低权限**: user（读取）/ admin（写入）

---

## 变更事件

### GET /api/changelog/events

- **说明**: 查询变更事件列表，支持多条件筛选和分页
- **权限**: user

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start | string | 否 | 起始时间，ISO 格式（如 `2025-01-01T00:00:00`）|
| end | string | 否 | 结束时间，ISO 格式 |
| event_type | string | 否 | 事件类型筛选（deploy / config / restart / maintenance / other）|
| operator | string | 否 | 操作人筛选 |
| limit | int | 否 | 每页条数，默认 200，范围 1-1000 |
| offset | int | 否 | 偏移量，默认 0 |

**响应示例**:

```json
{
  "items": [
    {
      "id": 1,
      "timestamp": "2025-04-05T10:30:00",
      "event_type": "deploy",
      "title": "Dify 平台升级到 v0.15",
      "description": "升级 Dify AI 平台至最新版本",
      "operator": "zhengxiaodong",
      "affected_services": "dify-api,dify-web,dify-worker",
      "risk_level": "medium",
      "duration_minutes": 15
    }
  ],
  "total": 1
}
```

---

### POST /api/changelog/events

- **说明**: 创建变更记录
- **权限**: admin

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| event_type | string | 否 | 事件类型（deploy / config / restart / maintenance / other），默认 other |
| title | string | 是 | 变更标题，最长 200 字符 |
| description | string | 否 | 详细描述 |
| affected_services | string | 否 | 受影响服务，逗号分隔 |
| risk_level | string | 否 | 风险等级（low / medium / high / critical），默认 low |
| duration_minutes | int | 否 | 预计持续分钟数，≥0 |

**响应示例**:

```json
{
  "ok": true,
  "event": {
    "id": 2,
    "timestamp": "2025-04-05T14:00:00",
    "event_type": "config",
    "title": "Nginx 配置更新",
    "description": "新增 academic 站点反向代理规则",
    "operator": "zhengxiaodong",
    "affected_services": "nginx",
    "risk_level": "low",
    "duration_minutes": 5
  }
}
```

**注意**: `operator` 字段自动从当前登录用户提取，无需手动传入。

---

### GET /api/changelog/events/{event_id}

- **说明**: 获取单条变更记录
- **权限**: user

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| event_id | int | 是 | 变更记录 ID（路径参数）|

**响应示例**:

```json
{
  "id": 1,
  "timestamp": "2025-04-05T10:30:00",
  "event_type": "deploy",
  "title": "Dify 平台升级到 v0.15",
  "description": "升级 Dify AI 平台至最新版本",
  "operator": "zhengxiaodong",
  "affected_services": "dify-api,dify-web,dify-worker",
  "risk_level": "medium",
  "duration_minutes": 15
}
```

**错误**: 404 — 变更记录不存在

---

### DELETE /api/changelog/events/{event_id}

- **说明**: 删除变更记录
- **权限**: admin

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| event_id | int | 是 | 变更记录 ID（路径参数）|

**响应示例**:

```json
{
  "ok": true
}
```

**错误**: 404 — 变更记录不存在

---

## 冻结窗口

### GET /api/changelog/freeze-windows

- **说明**: 查询冻结窗口列表
- **权限**: user

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| active_only | bool | 否 | 仅返回当前生效的冻结窗口，默认 false |

**响应示例**:

```json
{
  "items": [
    {
      "id": 1,
      "title": "期末考试冻结期",
      "start_time": "2025-06-20T00:00:00",
      "end_time": "2025-06-30T23:59:59",
      "reason": "考试期间禁止系统变更",
      "created_by": "zhengxiaodong",
      "created_at": "2025-06-15T10:00:00"
    }
  ],
  "total": 1
}
```

---

### POST /api/changelog/freeze-windows

- **说明**: 创建冻结窗口
- **权限**: admin

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| title | string | 是 | 窗口标题，最长 200 字符 |
| start_time | datetime | 是 | 开始时间（ISO 格式）|
| end_time | datetime | 是 | 结束时间（ISO 格式），必须晚于 start_time |
| reason | string | 否 | 冻结原因说明 |

**响应示例**:

```json
{
  "ok": true,
  "window": {
    "id": 2,
    "title": "国庆假期冻结",
    "start_time": "2025-10-01T00:00:00",
    "end_time": "2025-10-07T23:59:59",
    "reason": "假期无人值守，禁止变更",
    "created_by": "zhengxiaodong",
    "created_at": "2025-09-28T09:00:00"
  }
}
```

**错误**:
- 400 — 结束时间必须晚于开始时间

**注意**: `created_by` 字段自动从当前登录用户提取。

---

### GET /api/changelog/freeze-windows/active

- **说明**: 检查当前是否处于冻结窗口
- **权限**: user

无参数。

**响应示例**（冻结中）:

```json
{
  "frozen": true,
  "window": {
    "id": 1,
    "title": "期末考试冻结期",
    "start_time": "2025-06-20T00:00:00",
    "end_time": "2025-06-30T23:59:59",
    "reason": "考试期间禁止系统变更",
    "created_by": "zhengxiaodong",
    "created_at": "2025-06-15T10:00:00"
  }
}
```

**响应示例**（未冻结）:

```json
{
  "frozen": false,
  "window": null
}
```

---

### DELETE /api/changelog/freeze-windows/{window_id}

- **说明**: 删除冻结窗口
- **权限**: admin

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| window_id | int | 是 | 冻结窗口 ID（路径参数）|

**响应示例**:

```json
{
  "ok": true
}
```

**错误**: 404 — 冻结窗口不存在

---

## 统计

### GET /api/changelog/stats

- **说明**: 变更统计聚合 — 按天 / 按类型 / 按风险等级分组
- **权限**: user

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start | string | 否 | 起始时间，ISO 格式 |
| end | string | 否 | 结束时间，ISO 格式 |

**响应示例**:

```json
{
  "total": 42,
  "by_day": [
    {"date": "2025-04-01", "count": 5},
    {"date": "2025-04-02", "count": 3}
  ],
  "by_type": [
    {"event_type": "deploy", "count": 18},
    {"event_type": "config", "count": 12},
    {"event_type": "restart", "count": 7},
    {"event_type": "maintenance", "count": 3},
    {"event_type": "other", "count": 2}
  ],
  "by_risk": [
    {"risk_level": "low", "count": 25},
    {"risk_level": "medium", "count": 12},
    {"risk_level": "high", "count": 4},
    {"risk_level": "critical", "count": 1}
  ]
}
```

---

## 数据模型

### 枚举类型

| 枚举 | 值 | 说明 |
|------|---|------|
| EventType | deploy, config, restart, maintenance, other | 变更类型 |
| RiskLevel | low, medium, high, critical | 风险等级 |

### 数据库表

参见 [数据库文档 - changelog_events](../database.md) 和 [changelog_freeze_windows](../database.md)。

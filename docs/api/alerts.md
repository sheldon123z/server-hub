# 告警管理 API

基于指标快照的规则评估引擎，支持阈值告警和基线偏离检测，内置 7 条常用规则。

**路由前缀**: `/api/alerts`
**相关文件**: `modules/alerts/routes.py`, `modules/alerts/services.py`, `modules/alerts/evaluator.py`, `modules/alerts/seed.py`

---

## 告警状态机

每条规则对每个 `server_id` 维护独立状态：

```
OK → Pending（连续 N 次超阈值）→ Firing（发送通知）→ Resolved（恢复 OK）
```

| 状态 | 说明 |
|------|------|
| `ok` | 指标正常 |
| `pending` | 连续超阈值，尚未达到 firing 阈值 |
| `firing` | 告警触发，已发送通知 |
| `resolved` | 告警恢复，已发送恢复通知 |

---

## 内置告警规则

| 规则 ID | 名称 | 触发条件 |
|---------|------|---------|
| `builtin-swap-high` | Swap 使用率过高 | swap 使用率 > 50% |
| `builtin-disk-high` | 磁盘使用率过高 | 根分区使用率 > 85% |
| `builtin-disk-critical` | 磁盘使用率严重 | 根分区使用率 > 95% |
| `builtin-gpu-temp` | GPU 温度过高 | GPU 温度 > 85°C |
| `builtin-container-restart` | 容器频繁重启 | 重启次数 > 5 |
| `builtin-user-memory-quota` | 用户超配额 | 内存使用 > 配额 × 0.9 |
| `builtin-idle-user` | 空闲用户长期占用 | 空闲时间 > 6 小时 |

---

## 活跃告警

### GET /api/alerts/active

获取当前处于 `firing` 状态的告警列表。

**权限**: `user`（已登录）

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| server_id | string | null | 按服务器筛选 |
| limit | int | 100 | 最多返回条数（1~500） |

**响应**:
```json
{
  "alerts": [
    {
      "id": 42,
      "rule_id": "builtin-swap-high",
      "rule_name": "Swap 使用率过高",
      "server_id": "local",
      "severity": "warning",
      "status": "firing",
      "value": 68.5,
      "threshold": 50.0,
      "message": "Swap 使用率 68.5% 超过阈值 50%",
      "fired_at": "2026-04-05T10:30:00",
      "acknowledged": false,
      "acknowledged_by": null
    }
  ],
  "count": 1
}
```

---

### GET /api/alerts/history

分页查询告警历史（含已恢复的告警）。

**权限**: `user`

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| limit | int | 50 | 1~500 |
| offset | int | 0 | 分页偏移 |
| server_id | string | null | 按服务器筛选 |
| severity | string | null | `info`/`warning`/`critical` |
| status | string | null | `firing`/`resolved`/`acknowledged` |

**响应**:
```json
{
  "alerts": [...],
  "total": 128,
  "count": 50
}
```

---

### PUT /api/alerts/{alert_id}/acknowledge

确认告警（标记为"已知晓"，不影响告警状态）。

**权限**: `admin`

**响应**: `{"ok": true}`

**失败** `404`: 告警不存在或已不处于 firing 状态。

---

## 告警规则管理

### GET /api/alerts/rules

获取告警规则列表。

**权限**: `user`

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| enabled_only | bool | false | 仅返回启用的规则 |

**响应**:
```json
{
  "rules": [
    {
      "id": "builtin-swap-high",
      "name": "Swap 使用率过高",
      "description": "系统 Swap 使用率超过 50% 时触发告警",
      "enabled": true,
      "severity": "warning",
      "is_builtin": true,
      "metric_path": "memory.swap_percent",
      "condition": "gt",
      "threshold": 50.0,
      "consecutive_count": 3,
      "auto_action": null,
      "created_at": "2026-04-01T00:00:00"
    }
  ],
  "count": 7
}
```

---

### POST /api/alerts/rules

创建自定义告警规则。

**权限**: `admin`

**请求体**:
```json
{
  "name": "CPU 使用率过高",
  "description": "CPU 使用率持续超过 90%",
  "severity": "warning",
  "metric_path": "cpu.percent",
  "condition": "gt",
  "threshold": 90.0,
  "consecutive_count": 5,
  "auto_action": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 规则名称 |
| description | string | 否 | 规则说明 |
| severity | string | 是 | `info`/`warning`/`critical` |
| metric_path | string | 是 | 指标路径（如 `cpu.percent`） |
| condition | string | 是 | `gt`/`lt`/`gte`/`lte`/`eq` |
| threshold | float | 是 | 触发阈值 |
| consecutive_count | int | 否 | 连续超阈值次数（默认 3） |
| auto_action | string | 否 | 触发时自动执行的操作 |

---

### PUT /api/alerts/rules/{rule_id}

更新告警规则（所有字段均为可选）。

**权限**: `admin`

---

### DELETE /api/alerts/rules/{rule_id}

删除自定义规则。内置规则（ID 以 `builtin-` 开头）不允许删除，可禁用。

**权限**: `admin`

**禁止删除内置规则** `400`:
```json
{"detail": "内置规则不允许删除，可禁用"}
```

---

### PUT /api/alerts/rules/{rule_id}/toggle

启用/禁用告警规则。

**权限**: `admin`

**查询参数**: `enabled=true|false`

**响应**: 返回更新后的规则对象。

---

### POST /api/alerts/rules/{rule_id}/test

使用当前最新指标快照立即测试规则评估结果（调试用）。

**权限**: `admin`

**响应**:
```json
{
  "rule_id": "builtin-swap-high",
  "triggered": false,
  "current_value": 23.4,
  "threshold": 50.0,
  "message": "当前 Swap 23.4%，未超过阈值 50%"
}
```

---

## 评估器状态（调试）

### GET /api/alerts/states

返回评估器内存中所有规则的当前状态快照。

**权限**: `admin`

**响应**:
```json
{
  "states": {
    "builtin-swap-high:local": {
      "status": "ok",
      "consecutive_count": 0,
      "last_evaluated": "2026-04-05T10:45:00"
    }
  }
}
```

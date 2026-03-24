# 定时任务模块 API

提供 crontab 的查询、CRUD 管理、启用/禁用、历史查看和备份功能。

**路由前缀**: `/api/cron`
**相关文件**: `modules/cron/routes.py`, `modules/cron/services.py`

---

## 端点列表

### GET /api/cron/

获取当前用户（`zhengxiaodong`）的 crontab 任务列表。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
{
  "user": "zhengxiaodong",
  "jobs": [
    {
      "schedule": "0 8 * * *",
      "command": "bash ~/scripts/notification/send-telegram-report.sh --morning-report",
      "comment": "每日早报",
      "enabled": true
    },
    {
      "schedule": "#0 6 * * *",
      "command": "bash ~/scripts/monitoring/server-health-check.sh",
      "comment": "",
      "enabled": false
    }
  ]
}
```

`enabled: false` 表示该任务行以 `#` 注释形式存在（已禁用）。

---

### GET /api/cron/root

获取 root 用户的 crontab 任务列表。

**权限**: admin

**请求参数**: 无

**成功响应** `200`: 结构同上，`user` 字段为 `"root"`。

---

### POST /api/cron/validate

验证 cron 表达式，返回中文描述和未来 5 次执行时间。

**权限**: 任意已登录用户（user / admin）

**请求体**:

```json
{
  "expression": "0 8 * * *"
}
```

**成功响应** `200`:

```json
{
  "valid": true,
  "description": "每天 08:00 执行",
  "next_runs": [
    "2026-03-25 08:00:00",
    "2026-03-26 08:00:00",
    "2026-03-27 08:00:00",
    "2026-03-28 08:00:00",
    "2026-03-29 08:00:00"
  ]
}
```

**失败响应** `200`（合法格式，但表达式无效时也返回 200）：

```json
{
  "valid": false,
  "error": "非法的 cron 表达式"
}
```

---

### PUT /api/cron/schedule

修改指定 cron 任务的执行时间。操作完成后记录审计日志。

**权限**: admin

**请求体**:

```json
{
  "cron_user": "zhengxiaodong",
  "old_schedule": "0 8 * * *",
  "command": "bash ~/scripts/notification/send-telegram-report.sh --morning-report",
  "new_schedule": "30 7 * * *"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cron_user | string | 是 | 目标用户（仅字母数字下划线横杠） |
| old_schedule | string | 是 | 当前的 cron 表达式（用于定位任务） |
| command | string | 是 | 任务命令（用于定位任务） |
| new_schedule | string | 是 | 新的 cron 表达式 |

**成功响应** `200`:

```json
{
  "ok": true,
  "new_schedule": "30 7 * * *"
}
```

---

### POST /api/cron/jobs

创建新的 cron 任务。操作完成后记录审计日志。

**权限**: admin

**请求体**:

```json
{
  "cron_user": "zhengxiaodong",
  "schedule": "0 6 * * 1",
  "command": "bash ~/scripts/monitoring/server-health-check.sh",
  "comment": "每周一健康检查"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cron_user | string | 是 | 目标用户 |
| schedule | string | 是 | cron 表达式 |
| command | string | 是 | 执行命令（最小长度 1） |
| comment | string | 否 | 注释说明，默认空 |

**成功响应** `200`:

```json
{
  "ok": true,
  "schedule": "0 6 * * 1",
  "command": "bash ~/scripts/monitoring/server-health-check.sh"
}
```

---

### DELETE /api/cron/jobs

删除指定 cron 任务。操作完成后记录审计日志。

**权限**: admin

**请求体**:

```json
{
  "cron_user": "zhengxiaodong",
  "schedule": "0 6 * * 1",
  "command": "bash ~/scripts/monitoring/server-health-check.sh"
}
```

**成功响应** `200`:

```json
{
  "ok": true
}
```

---

### PUT /api/cron/jobs/toggle

启用或禁用 cron 任务（通过在行首添加/去除 `#` 实现）。操作完成后记录审计日志。

**权限**: admin

**请求体**:

```json
{
  "cron_user": "zhengxiaodong",
  "schedule": "0 8 * * *",
  "command": "bash ~/scripts/notification/send-telegram-report.sh --morning-report",
  "enabled": false
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cron_user | string | 是 | 目标用户 |
| schedule | string | 是 | cron 表达式 |
| command | string | 是 | 任务命令 |
| enabled | bool | 是 | `true` 启用 / `false` 禁用 |

**成功响应** `200`:

```json
{
  "ok": true,
  "enabled": false
}
```

---

### GET /api/cron/history

从 systemd journal 中获取 cron 任务的执行历史记录。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| pattern | string | `""` | 按命令关键词过滤（可选） |
| hours | int | 24 | 查询最近多少小时（范围 1-720） |

**成功响应** `200`:

```json
{
  "entries": [
    {
      "timestamp": "2026-03-24T08:00:01",
      "command": "bash ~/scripts/notification/send-telegram-report.sh --morning-report",
      "exit_code": 0,
      "output": "Report sent successfully"
    }
  ],
  "count": 1
}
```

---

### POST /api/cron/backup

备份指定用户的 crontab 到本地文件。操作完成后记录审计日志。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| cron_user | string | `"zhengxiaodong"` | 要备份的用户名 |

**成功响应** `200`:

```json
{
  "ok": true,
  "path": "/home/zhengxiaodong/logs/cron_backup_20260324_103000.txt"
}
```

---

### GET /api/cron/backups

列出可用的 crontab 备份文件。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| cron_user | string | `""` | 按用户名过滤，空则列出全部 |

**成功响应** `200`:

```json
{
  "backups": [
    "/home/zhengxiaodong/logs/cron_backup_20260324_103000.txt",
    "/home/zhengxiaodong/logs/cron_backup_20260323_080000.txt"
  ]
}
```

# 定时任务模块 API

提供 crontab 的查询、CRUD 管理、启用/禁用、表达式验证、执行历史查看和备份功能。

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
      "description": "每天 08:00",
      "command": "bash ~/scripts/notification/send-telegram-report.sh --morning-report",
      "comment": "每日早报",
      "raw_line": "0 8 * * * bash ~/scripts/notification/send-telegram-report.sh --morning-report",
      "enabled": true,
      "index": 0
    },
    {
      "schedule": "0 6 * * *",
      "description": "每天 06:00",
      "command": "bash ~/scripts/monitoring/server-health-check.sh",
      "comment": "",
      "raw_line": "#DISABLED# 0 6 * * * bash ~/scripts/monitoring/server-health-check.sh",
      "enabled": false,
      "index": 1
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| schedule | string | cron 表达式（5 字段） |
| description | string | 中文可读描述（由 `describe_schedule()` 生成） |
| command | string | 执行命令 |
| comment | string | cron 行上方的注释内容，无则为空字符串 |
| raw_line | string | crontab 中的原始行文本 |
| enabled | bool | `true` 启用 / `false` 已禁用（带 `#DISABLED# ` 前缀） |
| index | int | 任务在列表中的序号 |

**错误响应** `500`: 读取 crontab 失败。

---

### GET /api/cron/root

获取 root 用户的 crontab 任务列表。

**权限**: admin

**请求参数**: 无

**成功响应** `200`: 结构同上，`user` 字段为 `"root"`。

**错误响应** `500`: 读取 crontab 失败。

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

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| expression | string | 是 | 待验证的 cron 表达式 |

**成功响应** `200`（表达式有效）:

```json
{
  "valid": true,
  "description": "每天 08:00",
  "next_runs": [
    "2026-03-25 08:00",
    "2026-03-26 08:00",
    "2026-03-27 08:00",
    "2026-03-28 08:00",
    "2026-03-29 08:00"
  ],
  "error": null
}
```

**失败响应** `200`（表达式无效，仍返回 200）:

```json
{
  "valid": false,
  "description": "",
  "next_runs": [],
  "error": "cron 表达式必须包含 5 个字段"
}
```

> 注意：此端点始终返回 200，通过 `valid` 字段区分结果。`next_runs` 时间格式为 `%Y-%m-%d %H:%M`（无秒）。使用 `croniter` 库计算未来执行时间。

---

### PUT /api/cron/schedule

修改指定 cron 任务的执行时间。通过 `old_schedule` + `command` 定位任务行，替换为 `new_schedule`。操作完成后记录审计日志（`cron.modify`）。

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
| cron_user | string | 是 | 目标用户名 |
| old_schedule | string | 是 | 当前的 cron 表达式（用于定位任务） |
| command | string | 是 | 任务命令（用于定位任务） |
| new_schedule | string | 是 | 新的 cron 表达式（必须 5 个字段） |

**成功响应** `200`:

```json
{
  "ok": true,
  "new_schedule": "30 7 * * *"
}
```

**错误响应**:
- `400`: 新表达式不是 5 个字段，或未找到匹配的任务
- `500`: 读写 crontab 失败

---

### POST /api/cron/jobs

创建新的 cron 任务。会先验证表达式合法性并检查重复。操作完成后记录审计日志（`cron.create`）。

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
| cron_user | string | 是 | 目标用户（仅字母、数字、下划线、横杠） |
| schedule | string | 是 | cron 表达式（必须通过 `croniter` 验证） |
| command | string | 是 | 执行命令（最小长度 1） |
| comment | string | 否 | 注释说明，写入 cron 行上方，默认空 |

**成功响应** `200`:

```json
{
  "ok": true,
  "schedule": "0 6 * * 1",
  "command": "bash ~/scripts/monitoring/server-health-check.sh"
}
```

**错误响应**:
- `400`: 无效的 cron 表达式、已存在相同任务
- `500`: 读写 crontab 失败

---

### DELETE /api/cron/jobs

删除指定 cron 任务。通过 `schedule` + `command` 精确匹配任务行（同时匹配启用和 `#DISABLED#` 禁用状态的行）。如果匹配行的上一行是注释，注释行也会一并删除。操作完成后记录审计日志（`cron.delete`）。

**权限**: admin

**请求体**:

```json
{
  "cron_user": "zhengxiaodong",
  "schedule": "0 6 * * 1",
  "command": "bash ~/scripts/monitoring/server-health-check.sh"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cron_user | string | 是 | 目标用户（仅字母、数字、下划线、横杠） |
| schedule | string | 是 | cron 表达式 |
| command | string | 是 | 任务命令 |

**成功响应** `200`:

```json
{
  "ok": true
}
```

**错误响应**:
- `400`: 未找到匹配的任务
- `500`: 读写 crontab 失败

---

### PUT /api/cron/jobs/toggle

启用或禁用 cron 任务。禁用时在行首添加 `#DISABLED# ` 前缀，启用时移除该前缀。操作完成后记录审计日志（`cron.enable` 或 `cron.disable`）。

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
| cron_user | string | 是 | 目标用户（仅字母、数字、下划线、横杠） |
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

**错误响应**:
- `400`: 未找到匹配的任务
- `500`: 读写 crontab 失败

---

### GET /api/cron/history

从 systemd journal（`journalctl -u cron`）中获取 cron 任务的执行历史记录。最多返回 100 条。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| pattern | string | `""` | 按命令关键词过滤（传给 `journalctl --grep`），可选 |
| hours | int | `24` | 查询最近多少小时（范围 1-720） |

**成功响应** `200`:

```json
{
  "entries": [
    {
      "timestamp": "2026-03-24T08:00:01+0800",
      "user": "zhengxiaodong",
      "command": "bash ~/scripts/notification/send-telegram-report.sh --morning-report"
    }
  ],
  "count": 1
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| timestamp | string | ISO 格式时间戳（来自 `journalctl -o short-iso`） |
| user | string | 执行该 cron 任务的系统用户 |
| command | string | 执行的命令 |

**错误响应**:
- `400`: `hours` 不在 1-720 范围内
- `500`: 读取 journal 失败

---

### POST /api/cron/backup

备份指定用户的 crontab 到本地文件。备份存储在 `data/cron_backups/` 目录，文件名格式 `{用户名}_{YYYYMMDD_HHMMSS}.txt`。操作完成后记录审计日志（`cron.backup`）。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| cron_user | string | `"zhengxiaodong"` | 要备份的用户名 |

**成功响应** `200`:

```json
{
  "ok": true,
  "path": "/home/zhengxiaodong/scripts/server-hub/data/cron_backups/zhengxiaodong_20260324_103000.txt"
}
```

**错误响应** `500`: 读取 crontab 或写入备份文件失败。

---

### GET /api/cron/backups

列出可用的 crontab 备份文件。按修改时间倒序排列，最多返回 20 条。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| cron_user | string | `""` | 按用户名过滤（匹配文件名前缀），空则列出全部 |

**成功响应** `200`:

```json
{
  "backups": [
    {
      "filename": "zhengxiaodong_20260324_103000.txt",
      "cron_user": "zhengxiaodong",
      "size": 1024,
      "created_at": "2026-03-24 10:30:00"
    },
    {
      "filename": "root_20260323_080000.txt",
      "cron_user": "root",
      "size": 512,
      "created_at": "2026-03-23 08:00:00"
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| filename | string | 备份文件名 |
| cron_user | string | 对应的系统用户 |
| size | int | 文件大小（字节） |
| created_at | string | 备份时间（`%Y-%m-%d %H:%M:%S` 格式） |

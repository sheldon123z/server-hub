# 日志查看模块 API

提供日志文件列表、内容读取、搜索和实时流式推送接口。

**路由前缀**: `/api/logs`
**相关文件**: `modules/logs/routes.py`, `modules/logs/services.py`

> 所有端点均需要 admin 权限。日志路径受白名单保护，仅允许访问配置的 `log_dirs` 目录下的文件，防止路径遍历攻击。

---

## 端点列表

### GET /api/logs/files

列出所有可访问的日志文件（在配置的 `log_dirs` 目录下递归搜索）。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
{
  "files": [
    {
      "path": "/var/log/nginx/access.log",
      "size": 10485760,
      "modified": "2026-03-24T09:30:00"
    },
    {
      "path": "/home/zhengxiaodong/logs/monitor.log",
      "size": 524288,
      "modified": "2026-03-24T08:00:01"
    }
  ],
  "count": 2
}
```

---

### GET /api/logs/tail

读取指定日志文件的最后 N 行内容。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 必填 | 默认值 | 范围 | 说明 |
|------|------|------|--------|------|------|
| path | string | 是 | - | - | 日志文件绝对路径 |
| lines | int | 否 | 200 | 1 ~ 10000 | 返回行数 |

**成功响应** `200`:

```json
{
  "path": "/var/log/nginx/access.log",
  "lines": 200,
  "content": "192.168.1.1 - - [24/Mar/2026:10:00:00 +0800] \"GET /api/dashboard/overview HTTP/1.1\" 200 1234\n..."
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 403 | 路径不在允许的目录白名单内 |
| 404 | 日志文件不存在 |
| 500 | 读取失败 |

---

### GET /api/logs/search

在指定日志文件中搜索匹配指定模式的行。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| path | string | 是 | - | 日志文件绝对路径 |
| q | string | 是 | - | 搜索关键词（1~500 字符） |
| max | int | 否 | 100 | 最多返回结果数（1~5000） |

**成功响应** `200`:

```json
{
  "path": "/var/log/nginx/access.log",
  "pattern": "500",
  "results": [
    {
      "line_number": 1042,
      "content": "192.168.1.5 - - [24/Mar/2026:09:15:22 +0800] \"POST /api/agents/chat HTTP/1.1\" 500 89"
    }
  ],
  "count": 1
}
```

---

### GET /api/logs/stream

通过 Server-Sent Events (SSE) 实时推送日志文件新增内容（类似 `tail -f`）。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| path | string | 是 | 日志文件绝对路径 |

**响应格式**: `text/event-stream`

每当日志文件有新内容写入时，推送以下格式的 SSE 事件：

```
event: log
data: 192.168.1.1 - - [24/Mar/2026:10:05:00 +0800] "GET /api/monitoring/realtime HTTP/1.1" 200 856

event: log
data: 192.168.1.1 - - [24/Mar/2026:10:05:05 +0800] "GET /api/monitoring/realtime HTTP/1.1" 200 856
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 403 | 路径不在白名单内 |
| 404 | 文件不存在 |

> 注意：连接建立后持续推送，客户端断开连接时服务端自动停止。

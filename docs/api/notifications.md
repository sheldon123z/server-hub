# 通知管理模块 API

提供 Telegram 通知的发送、测试和历史查看接口。

**路由前缀**: `/api/notifications`
**相关文件**: `modules/notifications/routes.py`, `modules/notifications/services.py`

> 所有端点均需要 admin 权限。Telegram 配置读取自 `~/.telegram_config`（BOT_TOKEN 和 CHAT_ID）。

---

## 端点列表

### POST /api/notifications/send

发送自定义 Telegram 通知消息。

**权限**: admin

**请求体**:

```json
{
  "message": "服务器维护通知：今晚 22:00 - 24:00 将进行系统更新，期间服务可能中断。"
}
```

| 字段 | 类型 | 必填 | 限制 | 说明 |
|------|------|------|------|------|
| message | string | 是 | 1 ~ 4096 字符 | 消息内容 |

**成功响应** `200`:

```json
{
  "success": true,
  "message_id": 12345,
  "timestamp": "2026-03-24T10:30:00"
}
```

**失败响应** `502`:

```json
{
  "detail": "Telegram send failed: Bad Request: message text is empty"
}
```

---

### POST /api/notifications/test

发送测试消息（固定内容 `"ServerHub 测试通知"`），验证 Telegram 集成是否正常。

**权限**: admin

**请求体**: 无

**成功响应** `200`:

```json
{
  "success": true,
  "message_id": 12346,
  "timestamp": "2026-03-24T10:30:05"
}
```

---

### GET /api/notifications/history

获取通知发送历史记录（从数据库 `notification_history` 表查询）。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| limit | int | 50 | 1 ~ 500 | 返回最近 N 条记录 |

**成功响应** `200`:

```json
{
  "notifications": [
    {
      "id": 1,
      "timestamp": "2026-03-24T10:30:00",
      "message": "服务器维护通知...",
      "success": true,
      "message_id": 12345
    },
    {
      "id": 2,
      "timestamp": "2026-03-24T08:00:01",
      "message": "【每日早报】...",
      "success": true,
      "message_id": 12340
    }
  ],
  "count": 2
}
```

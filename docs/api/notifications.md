# 通知管理 API

统一多渠道通知系统，支持 Telegram Bot、站内通知和 Webhook 三种渠道，并行分发。

**路由前缀**: `/api/notifications`
**相关文件**: `modules/notifications/routes.py`, `modules/notifications/services.py`, `modules/notifications/channels.py`, `modules/notifications/dispatcher.py`

---

## 架构概览

```
send_notification("消息")
     │
     ├── TelegramBotChannel  → httpx POST telegram API
     ├── InAppChannel        → 写入 inapp_notifications 表 + WebSocket 推送
     └── WebhookChannel      → httpx POST 自定义 URL
```

所有启用的渠道并行投递，互不影响。每次投递结果记录到 `notifications` 历史表。

---

## 站内通知（当前用户）

站内通知与登录用户绑定，前端 TopBar 铃铛图标显示未读数。

### GET /api/notifications

获取当前用户的站内通知列表（分页）。

**权限**: 已登录（任意角色）

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| unread_only | bool | false | 仅返回未读 |
| limit | int | 50 | 1~200 |
| offset | int | 0 | 分页偏移 |

**响应**:
```json
{
  "items": [
    {
      "id": 42,
      "title": "告警通知",
      "message": "Swap 使用率 68.5% 超过阈值",
      "level": "warning",
      "read": false,
      "created_at": "2026-04-05T10:30:00"
    }
  ],
  "total": 5,
  "unread": 3
}
```

---

### GET /api/notifications/unread-count

获取未读通知数（TopBar badge 专用，轻量接口）。

**权限**: 已登录

**响应**: `{"count": 3}`

---

### PUT /api/notifications/read-all

将当前用户所有通知标记为已读。

**权限**: 已登录

**响应**: `{"ok": true, "updated": 3}`

---

### PUT /api/notifications/{notification_id}/read

标记单条通知为已读。

**权限**: 已登录

**响应**: `{"ok": true}`

---

## 渠道类型

### GET /api/notifications/channel-types

获取系统支持的所有渠道类型及其配置 schema。

**权限**: `admin`

**响应**:
```json
{
  "telegram": {
    "display_name": "Telegram Bot",
    "config_schema": {
      "bot_token": {"type": "string", "label": "Bot Token"},
      "chat_id": {"type": "string", "label": "Chat ID"}
    }
  },
  "inapp": {
    "display_name": "站内通知",
    "config_schema": {}
  },
  "webhook": {
    "display_name": "Webhook",
    "config_schema": {
      "url": {"type": "string", "label": "Webhook URL"},
      "secret": {"type": "string", "label": "签名密钥（可选）"}
    }
  }
}
```

---

## 渠道管理

### GET /api/notifications/channels

列出所有已配置的通知渠道。

**权限**: `admin`

**响应**:
```json
{
  "channels": [
    {
      "id": "telegram-main",
      "channel_type": "telegram",
      "display_name": "实验室 Telegram",
      "enabled": true,
      "priority": 1,
      "created_at": "2026-04-01T00:00:00"
    }
  ]
}
```

---

### POST /api/notifications/channels

创建通知渠道。

**权限**: `admin`

**请求体**:
```json
{
  "channel_type": "telegram",
  "display_name": "实验室 Telegram",
  "config": {
    "bot_token": "1234567890:ABCdef...",
    "chat_id": "-100123456789"
  },
  "enabled": true
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| channel_type | string | 是 | `telegram`/`inapp`/`webhook` |
| display_name | string | 是 | 渠道显示名 |
| config | object | 否 | 渠道特定配置 |
| enabled | bool | 否 | 默认 true |

**成功响应** `201`: 返回创建的渠道对象。

> **Telegram 渠道**：如果 `config.bot_token` 缺省，自动读取 `~/.telegram_config` 中的 `BOT_TOKEN` 和 `CHAT_ID`。

---

### PUT /api/notifications/channels/{channel_id}

更新渠道配置（字段可选，仅更新提供的字段）。

**权限**: `admin`

**请求体** (均可选):
```json
{
  "display_name": "新名称",
  "config": {"chat_id": "-100987654321"},
  "enabled": false,
  "priority": 2
}
```

---

### DELETE /api/notifications/channels/{channel_id}

删除通知渠道。

**权限**: `admin`

**响应**: `{"ok": true}`

---

### POST /api/notifications/channels/{channel_id}/test

向指定渠道发送测试消息，验证连通性。

**权限**: `admin`

**响应**:
```json
{
  "success": true,
  "channel_id": "telegram-main",
  "message": "测试消息发送成功"
}
```

---

## 消息发送

### POST /api/notifications/send

向所有启用的渠道广播消息。

**权限**: `admin`

**请求体**:
```json
{
  "message": "服务器维护通知：今晚 22:00 - 24:00 进行系统更新，期间服务可能中断。"
}
```

| 字段 | 类型 | 必填 | 限制 | 说明 |
|------|------|------|------|------|
| message | string | 是 | 1~4096 字符 | 消息内容 |

**响应**:
```json
{
  "results": [
    {"channel_id": "telegram-main", "success": true},
    {"channel_id": "inapp", "success": true}
  ],
  "summary": "2/2 个渠道发送成功",
  "all_success": true
}
```

---

### POST /api/notifications/test

向所有启用渠道发送测试通知（消息固定为"ServerHub 测试通知"）。

**权限**: `admin`

**响应**: 同 `/send`。

---

## 发送历史

### GET /api/notifications/history

查询通知发送历史记录。

**权限**: `admin`

**查询参数**:

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| limit | int | 50 | 1~500 |
| channel_id | string | null | 按渠道筛选 |

**响应**:
```json
{
  "notifications": [
    {
      "id": 100,
      "channel_id": "telegram-main",
      "message": "告警：Swap 使用率 68.5%",
      "success": true,
      "created_at": "2026-04-05T10:30:00"
    }
  ],
  "count": 1
}
```

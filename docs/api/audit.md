# 审计日志模块 API

提供分页查询操作审计日志的接口。

**路由前缀**: `/api/audit`
**相关文件**: `modules/audit/routes.py`, `modules/audit/middleware.py`

> 所有 `POST / PUT / DELETE /api/*` 请求均由审计中间件自动写入 `audit_log` 表，包含操作用户、操作类型、目标、IP 地址和成功/失败状态。客户端 IP 通过 `utils.get_client_ip()` 提取，兼容 nginx 反代（优先级: `X-Forwarded-For` 首 IP > `X-Real-IP` > `request.client.host`）。

---

## 端点列表

### GET /api/audit/

分页查询审计日志，支持按用户名和操作类型筛选。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| page | int | 1 | ≥ 1 | 页码 |
| limit | int | 50 | 1 ~ 200 | 每页条数 |
| username | string | 无 | - | 按操作用户名筛选（精确匹配，可选） |
| action | string | 无 | - | 按操作类型筛选（精确匹配，可选） |

**成功响应** `200`:

```json
{
  "total": 1024,
  "page": 1,
  "limit": 50,
  "items": [
    {
      "timestamp": "2026-03-24T10:30:00",
      "username": "admin",
      "action": "docker.container.restart",
      "target": "docker-nginx-1",
      "details": "Container restarted successfully",
      "ip": "192.168.1.100",
      "success": true
    },
    {
      "timestamp": "2026-03-24T10:25:00",
      "username": "admin",
      "action": "service.restart",
      "target": "nginx",
      "details": "",
      "ip": "192.168.1.100",
      "success": true
    }
  ]
}
```

**常见 action 值**:

| action | 触发来源 |
|--------|---------|
| `docker.container.start` | 启动容器 |
| `docker.container.stop` | 停止容器 |
| `docker.container.restart` | 重启容器 |
| `docker.image.remove` | 删除镜像 |
| `docker.stack.up` / `down` / `restart` / `pull` | Compose 堆栈操作 |
| `service.start` / `stop` / `restart` | systemd 服务操作 |
| `cron.create` / `modify` / `delete` | cron 任务变更 |
| `cron.enable` / `cron.disable` | cron 任务启用/禁用 |
| `cron.backup` | crontab 备份 |

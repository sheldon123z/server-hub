# ServerHub API 文档总览

## 认证方式

ServerHub 使用 **JWT Cookie 认证**。登录成功后，服务端通过 `Set-Cookie` 将两个 HttpOnly Cookie 写入客户端：

| Cookie | 说明 | 有效期 |
|--------|------|--------|
| `access_token` | 访问令牌（JWT），随每次请求自动携带 | 24 小时 |
| `refresh_token` | 刷新令牌，用于无感续期 | 30 天 |

所有受保护的 API 端点均从请求的 Cookie 中读取 `access_token` 并验证。前端无需手动处理 Authorization 头，浏览器自动携带 Cookie。

**刷新流程**：`access_token` 过期后，调用 `POST /api/auth/refresh`，服务端验证 `refresh_token` 后重新签发 `access_token`。

## 权限模型

系统采用两级 RBAC：

| 角色 | 权限范围 |
|------|---------|
| `admin` | 完全控制：读取 + 写入 + 危险操作（重启服务、终止进程、删除资源等） |
| `user` | 只读监控：查看系统状态、指标、日志，不可执行写操作 |

依赖注入方式：
- `get_current_user` — 验证已登录（任意角色均可）
- `require_role("admin")` — 验证 admin 角色

## 通用响应格式

### 成功响应

数据直接作为 JSON 返回，无固定外层包装。部分操作类端点返回：

```json
{
  "ok": true,
  "message": "操作描述"
}
```

集合型端点通常返回：

```json
{
  "items": [...],
  "total": 100,
  "count": 50
}
```

### 错误响应

所有错误均返回标准 FastAPI HTTPException 格式：

```json
{
  "detail": "错误描述信息"
}
```

常见 HTTP 状态码：

| 状态码 | 含义 |
|--------|------|
| 400 | 请求参数有误 |
| 401 | 未登录或令牌失效 |
| 403 | 权限不足（需要 admin） |
| 404 | 资源不存在 |
| 409 | 资源冲突（重复创建） |
| 500 | 服务器内部错误 |
| 502 | 上游服务不可用（如 Telegram API） |

## 审计日志

所有 `POST / PUT / DELETE /api/*` 请求由审计中间件自动记录到 `audit_log` 表，包含操作用户、操作类型、目标、IP 地址和结果。

## API 端点汇总

| 模块 | 路由前缀 | 端点数 | 最低权限 |
|------|---------|--------|---------|
| [认证](auth.md) | `/api/auth` | 5 | 无（登录）/ user（其余） |
| [仪表盘](dashboard.md) | `/api/dashboard` | 1 | user |
| [系统监控](monitoring.md) | `/api/monitoring` | 3 | user |
| [Docker 管理](docker.md) | `/api/docker` | 9 | user（读）/ admin（写） |
| [服务管理](services.md) | `/api/services` | 4 | user（读）/ admin（写） |
| [用户管理](users.md) | `/api/users` | 6 | user（读）/ admin（写） |
| [定时任务](cron.md) | `/api/cron` | 11 | user（读）/ admin（写） |
| [网络管理](network.md) | `/api/network` | 4 | admin |
| [代理管理](proxy.md) | `/api/proxy` | 7 | admin |
| [日志查看](logs.md) | `/api/logs` | 4 | admin |
| [通知管理](notifications.md) | `/api/notifications` | 3 | admin |
| [审计日志](audit.md) | `/api/audit` | 1 | admin |
| [面板用户](panel-users.md) | `/api/panel-users` | 4 | admin |
| [系统设置](settings.md) | `/api/settings` | 1 | admin |
| [资产台账](assets.md) | `/api/assets` | 7 | admin |
| [AI Agent](agents.md) | `/api/agents` | 35（含 1 WS） | admin |

**合计**: 16 个模块，约 80 个端点（含 1 个 WebSocket）。

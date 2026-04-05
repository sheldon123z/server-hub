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

系统采用细粒度 RBAC（详见 [RBAC 权限管理](rbac.md)），同时向后兼容旧版两级角色。

### 内置角色

| 角色 | 权限范围 |
|------|---------|
| `super-admin` | 拥有所有权限（`*:*:*`） |
| `operator` | 可执行操作但不可管理用户和 RBAC |
| `viewer` | 只读权限 |
| `agent-user` | 仅可使用 Agent 对话功能 |

### 向后兼容

旧版 `admin`/`user` 角色在启动时自动迁移：`admin` → `super-admin`，`user` → `viewer`。

### 依赖注入方式

- `get_current_user` — 验证已登录（任意角色均可）
- `require_role("admin")` — 向后兼容，等价于 `require_permission("*", "*")`
- `require_permission("servers", "write")` — 细粒度资源权限守卫（推荐）

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
| [Docker 管理](docker.md) | `/api/docker` | 15 | user（读）/ admin（写） |
| [服务管理](services.md) | `/api/services` | 9 | user（读）/ admin（写） |
| [用户管理](users.md) | `/api/users` | 14 | user（读）/ admin（写） |
| [定时任务](cron.md) | `/api/cron` | 10 | user（读）/ admin（写） |
| [网络管理](network.md) | `/api/network` | 4 | admin |
| [代理管理](proxy.md) | `/api/proxy` | 7 | admin |
| [日志查看](logs.md) | `/api/logs` | 4 | admin |
| [通知管理](notifications.md) | `/api/notifications` | 16 | user（站内）/ admin（管理） |
| [告警管理](alerts.md) | `/api/alerts` | 10 | user（读）/ admin（写） |
| [RBAC 权限](rbac.md) | `/api/rbac` | 11 | rbac:admin / user（自查） |
| [文件管理](files.md) | `/api/files` | 10 | files:read / files:write |
| [审计日志](audit.md) | `/api/audit` | 1 | admin |
| [面板用户](panel-users.md) | `/api/panel-users` | 4 | admin |
| [系统设置](settings.md) | `/api/settings` | 1 | admin |
| [资产台账](assets.md) | `/api/assets` | 7 | admin |
| [AI Agent](agents.md) | `/api/agents` | 35（含 1 WS） | admin |

**合计**: 19 个模块，约 170 个端点（含 1 个 WebSocket）。

### GET /api/sidebar
- **说明**: 返回按用户角色过滤的侧边栏菜单项（React 前端使用）
- **权限**: `user`（自动按角色过滤 admin-only 模块）
- **响应**: `[{name, display_name, icon, category, required_role, order}]`

---

## 各模块端点明细

### Docker 管理 `/api/docker`（15 个端点）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/containers` | 列出所有容器 | user |
| GET | `/containers/{name}/logs` | 获取容器日志 | user |
| GET | `/containers/{name}/stats` | 获取容器资源统计 | user |
| GET | `/containers/{name}/inspect` | 获取容器 inspect 详情 | admin |
| POST | `/containers/{name}/{action}` | 容器操作（start/stop/restart） | admin |
| POST | `/containers/{name}/exec` | 在容器内执行命令 | admin |
| GET | `/containers/{name}/env` | 获取容器环境变量（脱敏） | admin |
| GET | `/images` | 列出本地镜像 | user |
| DELETE | `/images/{image_id}` | 删除镜像 | admin |
| POST | `/images/pull` | 拉取镜像 | admin |
| GET | `/stacks` | 列出 Compose 堆栈 | user |
| POST | `/stacks/{name}/{action}` | 堆栈操作（up/down/restart/pull） | admin |
| GET | `/networks` | 列出 Docker 网络 | user |
| GET | `/volumes` | 列出 Docker 卷 | user |
| POST | `/prune/{resource_type}` | 清理未使用资源 | admin |

### 服务管理 `/api/services`（9 个端点）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/` | 列出所有受管 systemd 服务 | user |
| GET | `/{name}/status` | 获取服务详细状态 | user |
| POST | `/{name}/{action}` | 服务操作（start/stop/restart） | admin |
| POST | `/{name}/enable` | 启用服务自启动 | admin |
| POST | `/{name}/disable` | 禁用服务自启动 | admin |
| POST | `/{name}/reload` | 重新加载服务配置 | admin |
| GET | `/{name}/resources` | 获取服务资源使用情况 | user |
| GET | `/{name}/dependencies` | 获取服务依赖关系 | user |
| GET | `/{name}/journal` | 获取服务 journal 日志 | user |

### 用户管理 `/api/users`（14 个端点）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/` | 获取所有用户资源使用统计 | user |
| GET | `/all` | 获取所有 Linux 用户详细信息 | admin |
| GET | `/sessions` | 获取当前活跃登录会话 | user |
| GET | `/{username}/history` | 获取用户登录历史 | admin |
| POST | `/create` | 创建 Linux 用户 | admin |
| DELETE | `/{username}` | 删除 Linux 用户 | admin |
| PUT | `/{username}` | 修改用户属性（组/Shell） | admin |
| POST | `/{username}/password` | 设置用户密码 | admin |
| POST | `/{username}/kill` | 终止用户所有进程 | admin |
| POST | `/{username}/kill/{pid}` | 终止用户单个进程 | admin |
| GET | `/quotas` | 获取所有配额配置 | user |
| PUT | `/quotas` | 全量替换配额配置 | admin |
| POST | `/quotas` | 添加单条配额 | admin |
| DELETE | `/quotas/{key}` | 删除指定配额 | admin |

### 定时任务 `/api/cron`（10 个端点）

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | `/` | 列出用户 crontab | user |
| GET | `/root` | 列出 root crontab | admin |
| POST | `/validate` | 验证 cron 表达式 | user |
| PUT | `/schedule` | 修改任务执行时间 | admin |
| POST | `/jobs` | 创建新任务 | admin |
| DELETE | `/jobs` | 删除任务 | admin |
| PUT | `/jobs/toggle` | 启用/禁用任务 | admin |
| GET | `/history` | 获取 cron 执行历史 | admin |
| POST | `/backup` | 备份 crontab | admin |
| GET | `/backups` | 列出可用备份 | admin |

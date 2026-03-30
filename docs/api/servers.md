# 服务器管理模块 API

提供多服务器注册、分组管理、连通性测试、Token 轮换等接口。基于 Hub-Agent 架构，中心 Hub 通过此模块管理远程服务器。

**路由前缀**: `/api/servers`
**相关文件**: `modules/servers/routes.py`, `modules/servers/services.py`, `modules/servers/schemas.py`, `modules/servers/agent_client.py`
**权限**: 所有端点需要 `admin` 角色

---

## 端点列表

### POST /api/servers/deploy

一键部署远程服务器：注册 → SSH 安装 Agent → 验证连通。

**权限**: admin

**请求体** (`ServerDeployRequest`):

```json
{
  "name": "gpu-server-01",
  "ip_address": "192.168.1.100",
  "ssh_user": "root",
  "ssh_port": 22,
  "ssh_password": "your-ssh-password",
  "agent_port": 9901,
  "hostname": "",
  "tags": ["gpu", "training"]
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| name | string | 是 | - | 服务器名称（1-64 字符）|
| ip_address | string | 是 | - | 主机 IP 地址 |
| ssh_password | string | 是 | - | SSH 登录密码 |
| ssh_user | string | 否 | `root` | SSH 登录用户 |
| ssh_port | int | 否 | `22` | SSH 端口 |
| agent_port | int | 否 | `9901` | Agent 监听端口 |
| hostname | string | 否 | name | 主机名（为空时回退到 name）|
| tags | string/list | 否 | `[]` | 标签（逗号分隔字符串或数组）|

**部署流程**:

1. 在本地数据库注册服务器，生成 Agent Token
2. 通过 `SERVERHUB_HUB_URL` 环境变量（或 Request Host 头）检测 Hub 地址
3. SSH 连接远程服务器，自动安装 serverhub-agent 并配置 Token
4. 等待 3 秒后测试连通性（三层健康检查）

**成功响应** `200`:

```json
{
  "ok": true,
  "id": "server-uuid",
  "deploy_ok": true,
  "deploy_log": "部署日志（Token 已脱敏）",
  "connectivity": {
    "ping_ok": true,
    "ping_ms": 2,
    "ssh_ok": true,
    "agent_ok": true,
    "agent_version": "0.1.0"
  }
}
```

**错误响应**:
- `409`: 服务器名称已存在
- `400`: 参数错误

> **安全提示**: 部署日志中的 Agent Token 会被自动脱敏。SSH 密码仅用于部署过程，不存储在数据库中。

---

### GET /api/servers/overview

获取服务器舰队概览统计（在线/离线数量、分组统计等）。

**权限**: admin

**成功响应** `200`:

```json
{
  "total": 5,
  "online": 3,
  "offline": 1,
  "unknown": 1,
  "groups": [...]
}
```

---

### GET /api/servers/

列出所有已注册的服务器。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| status | string | null | 按状态过滤：online / offline / unknown |

**成功响应** `200`: 服务器列表数组。

---

### GET /api/servers/{server_id}

获取单个服务器详情。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| server_id | 服务器 ID |

**成功响应** `200`: 服务器详情对象。

**错误响应** `404`: 服务器不存在。

---

### POST /api/servers/

注册新服务器，返回一次性可见的 agent token。

**权限**: admin

**请求体** (`ServerCreateRequest`):

```json
{
  "name": "gpu-server-01",
  "ip_address": "192.168.1.100",
  "agent_port": 9901,
  "hostname": "gpu-node-01",
  "ssh_user": "root",
  "ssh_port": 22,
  "tags": ["gpu", "training"]
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| name | string | 是 | - | 服务器名称（1-64 字符，UNIQUE）|
| ip_address | string | 是 | - | 主机 IP 地址 |
| agent_port | int | 否 | `9901` | Agent 监听端口 |
| hostname | string | 否 | name | 主机名 |
| ssh_user | string | 否 | null | SSH 用户 |
| ssh_port | int | 否 | `22` | SSH 端口 |
| ssh_key_credential | string | 否 | null | SSH 密钥凭据引用 |
| tags | string/list | 否 | `[]` | 标签 |

**成功响应** `200`:

```json
{
  "ok": true,
  "id": "server-uuid",
  "agent_token": "一次性可见的明文 token"
}
```

**错误响应**:
- `409`: 服务器名称已存在
- `400`: 参数错误

> **安全提示**: `agent_token` 仅在创建时返回一次，之后只能通过轮换获取新 token。Token 使用 Fernet 加密存储在数据库中。

---

### PUT /api/servers/{server_id}

更新服务器信息。

**权限**: admin

**请求体**: 可更新字段（`exclude_unset=True`，仅发送需要更新的字段）。

```json
{
  "name": "new-name",
  "host": "192.168.1.200",
  "port": 9901,
  "description": "更新描述"
}
```

**成功响应** `200`: `{"ok": true}`

**错误响应** `404`: 服务器不存在。

---

### DELETE /api/servers/{server_id}

删除服务器。

**权限**: admin

**成功响应** `200`: `{"ok": true}`

**错误响应** `400`: 删除失败（如本地服务器不可删除）。

---

### POST /api/servers/{server_id}/test

测试服务器连通性（三层健康检查：存活 -> 鉴权 -> 业务）。

**权限**: admin

**成功响应** `200`:

```json
{
  "ok": true,
  "reachable": true,
  "authenticated": true,
  "latency_ms": 45
}
```

**错误响应** `404`: 服务器不存在。

---

### POST /api/servers/{server_id}/rotate-token

轮换服务器 agent token。旧 token 立即失效，返回新的一次性可见 token。

**权限**: admin

**成功响应** `200`:

```json
{
  "ok": true,
  "token": "新的一次性可见明文 token"
}
```

**错误响应** `404`: 服务器不存在。

---

## 服务器分组

### GET /api/servers/groups

列出所有服务器分组。

**权限**: admin

**成功响应** `200`: 分组列表数组。

---

### POST /api/servers/groups

创建服务器分组。

**权限**: admin

**请求体**:

```json
{
  "name": "GPU 集群",
  "description": "用于训练的 GPU 服务器组"
}
```

**成功响应** `200`: `{"ok": true, "id": "group-uuid"}`

**错误响应** `409`: 分组名已存在。

---

### DELETE /api/servers/groups/{group_id}

删除服务器分组。

**权限**: admin

**成功响应** `200`: `{"ok": true}`

**错误响应** `404`: 分组不存在。

---

### GET /api/servers/groups/{group_id}/members

列出分组内所有服务器。

**权限**: admin

**成功响应** `200`: 分组内服务器列表。

**错误响应** `404`: 分组不存在。

---

### POST /api/servers/groups/{group_id}/members

将服务器添加到分组。

**权限**: admin

**请求体**:

```json
{
  "server_id": "server-uuid"
}
```

**成功响应** `200`: `{"ok": true}`

**错误响应** `404`: 分组或服务器不存在。

---

### DELETE /api/servers/groups/{group_id}/members/{server_id}

从分组中移除服务器。

**权限**: admin

**成功响应** `200`: `{"ok": true}`

**错误响应** `404`: 分组或服务器不存在。

# RBAC 权限管理 API

细粒度角色权限控制（Role-Based Access Control），支持自定义角色和资源级权限分配。

**路由前缀**: `/api/rbac`
**相关文件**: `modules/rbac/routes.py`, `modules/rbac/services.py`, `modules/rbac/seed.py`

> 所有端点均需要 `rbac:admin` 权限（内置角色 `super-admin` 持有此权限）。  
> 普通用户可调用 `GET /api/rbac/users/me/permissions` 查询自身权限。

---

## 权限模型

### 内置角色

| 角色 ID | 显示名 | 说明 |
|---------|--------|------|
| `super-admin` | 超级管理员 | 拥有所有权限，不可删除 |
| `operator` | 运维人员 | 可执行操作但不可管理用户和 RBAC |
| `viewer` | 观察者 | 只读权限 |
| `agent-user` | Agent 用户 | 仅可使用 Agent 对话功能 |

### 权限格式

每条权限由三个字段组成：

```json
{
  "resource": "servers",
  "action": "write",
  "scope": "*"
}
```

| 字段 | 可选值 | 说明 |
|------|--------|------|
| `resource` | `*`, `servers`, `docker`, `services`, `users`, `cron`, `files`, `agents`, `rbac`, `alerts`, `notifications` | 资源类型，`*` 表示所有资源 |
| `action` | `*`, `read`, `write`, `admin` | 操作类型，`*` 表示所有操作 |
| `scope` | `*` | 当前版本统一为 `*`（全范围） |

向后兼容：旧版 `require_role("admin")` 映射为 `has_permission("*", "*")`，`require_role("user")` 映射为 `has_permission("*", "read")`。

---

## 角色管理

### GET /api/rbac/roles

获取所有角色（含权限列表）。

**权限**: `rbac:admin`

**响应**:
```json
[
  {
    "id": "super-admin",
    "name": "super-admin",
    "display_name": "超级管理员",
    "description": "拥有所有权限",
    "is_builtin": true,
    "permissions": [
      {"resource": "*", "action": "*", "scope": "*"}
    ]
  }
]
```

---

### POST /api/rbac/roles

创建自定义角色。

**权限**: `rbac:admin`

**请求体**:
```json
{
  "name": "dev-ops",
  "display_name": "DevOps 工程师",
  "description": "部署和监控权限",
  "permissions": [
    {"resource": "servers", "action": "write", "scope": "*"},
    {"resource": "docker", "action": "write", "scope": "*"},
    {"resource": "agents", "action": "read", "scope": "*"}
  ]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| name | string | 是 | 唯一标识符（kebab-case） |
| display_name | string | 是 | 显示名 |
| description | string | 否 | 角色说明 |
| permissions | array | 否 | 权限列表 |

**成功响应** `200`:
```json
{"ok": true, "role": {...}}
```

**冲突响应** `409`:
```json
{"detail": "角色名 dev-ops 已存在"}
```

---

### PUT /api/rbac/roles/{role_id}

更新角色信息。内置角色不允许修改权限。

**权限**: `rbac:admin`

**请求体** (所有字段可选):
```json
{
  "display_name": "DevOps 工程师（更新）",
  "description": "新说明",
  "permissions": [...]
}
```

---

### DELETE /api/rbac/roles/{role_id}

删除自定义角色。内置角色不可删除。

**权限**: `rbac:admin`

**成功响应**: `{"ok": true}`

**禁止响应** `403`:
```json
{"detail": "内置角色不允许删除"}
```

---

## 角色权限

### GET /api/rbac/roles/{role_id}/permissions

获取角色的权限列表。

**权限**: `rbac:admin`

**响应**:
```json
{
  "role_id": "operator",
  "permissions": [
    {"resource": "servers", "action": "write", "scope": "*"},
    {"resource": "docker", "action": "write", "scope": "*"}
  ]
}
```

---

### PUT /api/rbac/roles/{role_id}/permissions

替换角色的全部权限（内置角色不可修改）。

**权限**: `rbac:admin`

**请求体**:
```json
{
  "permissions": [
    {"resource": "agents", "action": "read", "scope": "*"}
  ]
}
```

---

## 用户角色分配

### GET /api/rbac/users/{user_id}/roles

获取用户持有的角色 ID 列表。

**权限**: `rbac:admin`

**响应**:
```json
{
  "user_id": "alice",
  "roles": ["operator", "dev-ops"]
}
```

---

### PUT /api/rbac/users/{user_id}/roles

为用户分配角色（幂等，重复分配不报错）。

**权限**: `rbac:admin`

**请求体**:
```json
{"role_id": "operator"}
```

**响应**:
```json
{"ok": true, "user_id": "alice", "roles": ["operator"]}
```

---

### DELETE /api/rbac/users/{user_id}/roles/{role_id}

移除用户的指定角色。

**权限**: `rbac:admin`

**响应**: `{"ok": true}`

---

## 当前用户权限查询

### GET /api/rbac/users/me/permissions

获取当前登录用户的所有有效权限。无需 `rbac:admin`，任意已登录用户均可访问。

**权限**: 已登录（任意角色）

**响应**:
```json
{
  "user_id": "alice",
  "permissions": [
    {"resource": "servers", "action": "write", "scope": "*"},
    {"resource": "docker", "action": "read", "scope": "*"}
  ]
}
```

---

## 依赖注入使用方式

在路由中使用细粒度权限守卫：

```python
from auth.dependencies import require_permission

# 需要 servers:read 权限
@router.get("/servers")
async def list_servers(user=Depends(require_permission("servers", "read"))):
    ...

# 需要 servers:write 权限
@router.post("/servers")
async def create_server(user=Depends(require_permission("servers", "write"))):
    ...
```

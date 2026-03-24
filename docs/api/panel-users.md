# 面板用户管理模块 API

提供 ServerHub 面板登录用户的增删改查接口。

> 注意：本模块管理的是**面板登录账号**，而非服务器 Linux 用户。Linux 用户管理请参见 [用户管理 API](users.md)。

**路由前缀**: `/api/panel-users`
**相关文件**: `modules/panel_users/routes.py`, `auth/user_store.py`

> 所有端点均需要 admin 权限。

---

## 端点列表

### GET /api/panel-users/

列出所有面板用户。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
{
  "users": [
    {
      "id": 1,
      "username": "admin",
      "display_name": "管理员",
      "role": "admin",
      "disabled": false,
      "created_at": "2026-01-01T00:00:00"
    },
    {
      "id": 2,
      "username": "viewer",
      "display_name": "只读用户",
      "role": "user",
      "disabled": false,
      "created_at": "2026-02-01T00:00:00"
    }
  ],
  "count": 2
}
```

---

### POST /api/panel-users/

创建新的面板用户。

**权限**: admin

**请求体**:

```json
{
  "username": "newuser",
  "password": "securepassword",
  "display_name": "新用户",
  "role": "user"
}
```

| 字段 | 类型 | 必填 | 限制 | 说明 |
|------|------|------|------|------|
| username | string | 是 | 2 ~ 32 字符 | 登录用户名 |
| password | string | 是 | 6 ~ 128 字符 | 初始密码 |
| display_name | string | 否 | 最长 64 字符 | 显示名称，默认空 |
| role | string | 否 | `admin` / `user` | 角色，默认 `user` |

**成功响应** `200`:

```json
{
  "id": 3,
  "username": "newuser",
  "display_name": "新用户",
  "role": "user",
  "disabled": false,
  "created_at": "2026-03-24T10:30:00"
}
```

**失败响应** `409`:

```json
{
  "detail": "用户名已存在"
}
```

---

### PUT /api/panel-users/{user_id}

更新面板用户的属性（显示名、角色、禁用状态、密码），仅更新提供的字段。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| user_id | 用户 ID（数字） |

**请求体**（所有字段可选，至少提供一个）:

```json
{
  "display_name": "更新后的显示名",
  "role": "admin",
  "disabled": false,
  "password": "newpassword"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| display_name | string | 新的显示名称（最长 64 字符） |
| role | string | 新角色：`admin` 或 `user` |
| disabled | bool | 是否禁用账号 |
| password | string | 新密码（6 ~ 128 字符） |

**成功响应** `200`: 返回更新后的完整用户对象（格式同创建响应）。

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 未提供任何字段 |
| 404 | 用户不存在 |

---

### DELETE /api/panel-users/{user_id}

删除面板用户。不能删除自己的账号。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| user_id | 用户 ID（数字） |

**成功响应** `200`:

```json
{
  "success": true,
  "deleted_user_id": "3"
}
```

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 试图删除自己的账号 |
| 404 | 用户不存在 |

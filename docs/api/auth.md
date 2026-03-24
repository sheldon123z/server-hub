# 认证模块 API

管理用户登录、登出、令牌刷新和密码修改。

**路由前缀**: `/api/auth`
**相关文件**: `auth/routes.py`, `auth/jwt_handler.py`, `auth/user_store.py`, `auth/models.py`

---

## 端点列表

### POST /api/auth/login

用户登录，成功后写入 `access_token` 和 `refresh_token` HttpOnly Cookie。

**权限**: 无需认证

**请求体**:

```json
{
  "username": "admin",
  "password": "yourpassword"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 面板用户名 |
| password | string | 是 | 密码 |

**成功响应** `200`:

```json
{
  "ok": true,
  "user": {
    "username": "admin",
    "display_name": "管理员",
    "role": "admin"
  }
}
```

同时设置以下 Cookie（HttpOnly, SameSite=Lax）：
- `access_token`：有效期 24 小时
- `refresh_token`：有效期 30 天

**失败响应** `401`:

```json
{
  "detail": "用户名或密码错误"
}
```

---

### POST /api/auth/refresh

使用 `refresh_token` Cookie 刷新 `access_token`，无感续期。

**权限**: 无需认证（依赖 Cookie 中的 refresh_token）

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true
}
```

同时重新设置 `access_token` Cookie（有效期重置为 24 小时）。

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 401 | 无刷新令牌 / 令牌无效 / 用户已禁用 |

---

### GET /api/auth/me

获取当前登录用户信息。

**权限**: 任意已登录用户（user / admin）

**请求体**: 无

**成功响应** `200`:

```json
{
  "username": "admin",
  "display_name": "管理员",
  "role": "admin"
}
```

---

### POST /api/auth/change-password

修改当前用户密码。

**权限**: 任意已登录用户（user / admin）

**请求体**:

```json
{
  "old_password": "oldpass",
  "new_password": "newpass"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| old_password | string | 是 | 原密码 |
| new_password | string | 是 | 新密码 |

**成功响应** `200`:

```json
{
  "ok": true
}
```

**失败响应** `400`:

```json
{
  "detail": "原密码错误"
}
```

---

### POST /api/auth/logout

登出，清除 Cookie。

**权限**: 无需认证（清除 Cookie 即可）

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true
}
```

此端点删除 `access_token` 和 `refresh_token` Cookie。

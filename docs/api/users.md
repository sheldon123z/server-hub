# 用户管理模块 API

提供 Linux 系统用户的资源统计、进程管理和配额配置接口。

> 注意：本模块管理的是**服务器 Linux 用户**，而非面板登录用户。面板用户管理请参见 [面板用户 API](panel-users.md)。

**路由前缀**: `/api/users`
**相关文件**: `modules/users/routes.py`, `modules/users/services.py`, `scripts/config/user-quotas.conf`

---

## 端点列表

### GET /api/users/

获取所有 Linux 用户的实时资源使用统计（CPU、内存、进程数等）。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "username": "zhengxiaodong",
    "uid": 1000,
    "processes": 45,
    "memory_mb": 2048.5,
    "memory_percent": 0.4,
    "cpu_percent": 2.1
  },
  {
    "username": "wangtao",
    "uid": 1001,
    "processes": 12,
    "memory_mb": 8192.0,
    "memory_percent": 1.6,
    "cpu_percent": 15.3
  }
]
```

---

### POST /api/users/{username}/kill

终止指定 Linux 用户的所有进程（等同于 `pkill -u {username}`）。操作会记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| username | Linux 用户名 |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "已终止用户 wangtao 的所有进程"
}
```

**失败响应** `400`:

```json
{
  "detail": "用户不存在或无进程可终止"
}
```

---

### GET /api/users/quotas

获取所有用户/用户组的资源配额配置（从 `config/user-quotas.conf` 读取）。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "key": "wangtao",
    "mem_gb": 80,
    "proc_limit": 600,
    "comment": "学生用户"
  },
  {
    "key": "@students",
    "mem_gb": 80,
    "proc_limit": 600,
    "comment": "students 组默认配额"
  },
  {
    "key": "default",
    "mem_gb": 16,
    "proc_limit": 200,
    "comment": "默认配额"
  }
]
```

配额匹配优先级：用户名精确匹配 > `@组名` 匹配 > `default`。

---

### PUT /api/users/quotas

全量替换所有配额配置（覆盖整个配额文件）。

**权限**: admin

**请求体**:

```json
[
  {
    "key": "wangtao",
    "mem_gb": 80,
    "proc_limit": 600,
    "comment": "学生用户"
  },
  {
    "key": "default",
    "mem_gb": 16,
    "proc_limit": 200,
    "comment": ""
  }
]
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| key | string | 是 | 用户名、`@组名` 或 `default` |
| mem_gb | int | 是 | 内存限制（GB） |
| proc_limit | int | 是 | 进程数上限 |
| comment | string | 否 | 备注说明 |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "配额已更新"
}
```

---

### POST /api/users/quotas

添加单条配额记录。

**权限**: admin

**请求体**:

```json
{
  "key": "newstudent",
  "mem_gb": 40,
  "proc_limit": 300,
  "comment": "新学生"
}
```

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "已添加配额 newstudent"
}
```

**失败响应** `409`:

```json
{
  "detail": "配额 newstudent 已存在"
}
```

---

### DELETE /api/users/quotas/{key}

删除指定 key 的配额记录。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| key | 配额 key（用户名、`@组名` 或 `default`） |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "已删除配额 newstudent"
}
```

**失败响应** `404`:

```json
{
  "detail": "配额 newstudent 不存在"
}
```

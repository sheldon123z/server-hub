# 用户管理模块 API

提供 Linux 系统用户的资源统计、用户生命周期管理、进程管理、登录审计和配额配置接口。

> 注意：本模块管理的是**服务器 Linux 用户**，而非面板登录用户。面板用户管理请参见 [面板用户 API](panel-users.md)。

**路由前缀**: `/api/users`
**相关文件**: `modules/users/routes.py`, `modules/users/services.py`, `scripts/config/user-quotas.conf`

---

## 端点总览

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET | /api/users/ | 用户资源使用统计 | user / admin |
| GET | /api/users/all | 全用户列表（含管理员） | admin |
| GET | /api/users/sessions | 活跃登录会话 | user / admin |
| GET | /api/users/{username}/history | 用户登录历史 | admin |
| POST | /api/users/create | 创建 Linux 用户 | admin |
| DELETE | /api/users/{username} | 删除 Linux 用户 | admin |
| PUT | /api/users/{username} | 修改用户属性 | admin |
| POST | /api/users/{username}/password | 设置用户密码 | admin |
| POST | /api/users/{username}/kill | 终止用户所有进程 | admin |
| POST | /api/users/{username}/kill/{pid} | 终止用户单个进程 | admin |
| GET | /api/users/quotas | 获取配额列表 | user / admin |
| PUT | /api/users/quotas | 全量替换配额 | admin |
| POST | /api/users/quotas | 添加单条配额 | admin |
| DELETE | /api/users/quotas/{key} | 删除配额 | admin |

---

## 资源监控

### GET /api/users/

获取所有非管理员 Linux 用户（UID >= 1000）的实时资源使用统计，包括内存、进程数、GPU 显存和 Top 进程。结果按内存使用量降序排列。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "name": "wangtao",
    "uid": 1001,
    "groups": "students docker",
    "mem_gb": 8.2,
    "proc_count": 12,
    "gpu_mem_mb": 4096,
    "top_procs": [
      { "pid": 12345, "mem_mb": 2048.5, "name": "python" },
      { "pid": 12346, "mem_mb": 1024.0, "name": "java" },
      { "pid": 12347, "mem_mb": 512.3, "name": "node" }
    ]
  }
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 用户名 |
| uid | int | 用户 UID |
| groups | string | 空格分隔的所属组 |
| mem_gb | float | 内存使用量（GB） |
| proc_count | int | 进程总数 |
| gpu_mem_mb | int | GPU 显存使用量（MB），无 GPU 进程则为 0 |
| top_procs | array | 内存占用最多的前 3 个进程 |

---

## 用户列表与详情

### GET /api/users/all

获取所有 Linux 用户（UID >= 1000）的详细信息，包含管理员用户。返回用户的 home 目录、shell、所属组、最后登录时间等。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
{
  "users": [
    {
      "name": "zhengxiaodong",
      "uid": 1000,
      "home": "/home/zhengxiaodong",
      "shell": "/bin/bash",
      "groups": "zhengxiaodong sudo docker",
      "last_login": "Tue Mar 24 09:30:00 2026",
      "is_admin": true
    },
    {
      "name": "wangtao",
      "uid": 1001,
      "home": "/home/wangtao",
      "shell": "/bin/bash",
      "groups": "wangtao students",
      "last_login": "从未登录",
      "is_admin": false
    }
  ]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 用户名 |
| uid | int | 用户 UID |
| home | string | home 目录路径 |
| shell | string | 登录 shell |
| groups | string | 空格分隔的所属组 |
| last_login | string | 最后登录时间，未登录过显示"从未登录" |
| is_admin | bool | 是否为管理员 |

---

## 登录审计

### GET /api/users/sessions

获取当前所有活跃登录会话（基于 `who` 命令）。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
{
  "sessions": [
    {
      "username": "zhengxiaodong",
      "tty": "pts/0",
      "login_time": "2026-03-24 09:30",
      "source": "192.168.1.100"
    }
  ],
  "count": 1
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| username | string | 登录用户名 |
| tty | string | 终端 |
| login_time | string | 登录时间 |
| source | string | 来源 IP 或终端，本地登录可能为空 |

---

### GET /api/users/{username}/history

获取指定用户的登录历史记录（基于 `last` 命令）。

**权限**: admin

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| username | string | Linux 用户名 |

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| count | int | 20 | 最大返回条数（上限 100） |

**成功响应** `200`:

```json
{
  "entries": [
    {
      "username": "wangtao",
      "tty": "pts/1",
      "source": "192.168.1.50",
      "raw": "wangtao  pts/1  192.168.1.50  Tue Mar 24 08:00:00 2026 - Tue Mar 24 12:00:00 2026 (04:00)"
    }
  ],
  "count": 1
}
```

**失败响应** `400`:

```json
{
  "detail": "无效的用户名: ..."
}
```

---

## 用户增删改

### POST /api/users/create

创建新的 Linux 用户。可选设置附加组、shell 和初始密码。操作记录审计日志。

**权限**: admin

**请求体**:

```json
{
  "username": "newstudent",
  "groups": "students,docker",
  "shell": "/bin/bash",
  "password": "initial123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| username | string | 是 | 用户名（2-32 字符，仅允许字母、数字、`_`、`-`） |
| groups | string | 否 | 逗号分隔的附加组，默认为空 |
| shell | string | 否 | 登录 shell，默认 `/bin/bash`。允许值：`/bin/bash`、`/bin/sh`、`/bin/zsh`、`/usr/bin/zsh`、`/usr/sbin/nologin`、`/bin/false` |
| password | string | 否 | 初始密码，不提供则用户无密码 |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "用户 newstudent 已创建"
}
```

**部分成功响应** `200`（用户已创建但密码设置失败）:

```json
{
  "ok": true,
  "warning": "用户已创建，但设置密码失败: ..."
}
```

**失败响应** `400`:

```json
{
  "detail": "用户 newstudent 已存在"
}
```

---

### DELETE /api/users/{username}

删除 Linux 用户。可选同时删除 home 目录。不允许删除管理员用户。操作记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| username | string | 要删除的用户名 |

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| remove_home | bool | false | 是否同时删除 home 目录 |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "用户 wangtao 已删除"
}
```

**失败响应** `400`:

```json
{
  "detail": "不能删除管理员用户"
}
```

---

### PUT /api/users/{username}

修改用户属性（所属组、登录 shell）。不允许修改管理员用户。操作记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| username | string | 要修改的用户名 |

**请求体**:

```json
{
  "groups": "students,docker",
  "shell": "/bin/zsh"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| groups | string | 否 | 逗号分隔的附加组，`null` 表示不修改 |
| shell | string | 否 | 登录 shell，`null` 表示不修改。允许值同创建接口 |

> 至少需要提供 `groups` 或 `shell` 中的一个，否则返回错误。

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "用户 wangtao 已修改"
}
```

**失败响应** `400`:

```json
{
  "detail": "未指定要修改的属性"
}
```

---

### POST /api/users/{username}/password

设置指定用户的密码（通过 `chpasswd` 命令）。不允许修改管理员密码。操作记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| username | string | 用户名 |

**请求体**:

```json
{
  "password": "newpassword123"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| password | string | 是 | 新密码（6-128 字符） |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "用户 wangtao 的密码已更新"
}
```

**失败响应** `400`:

```json
{
  "detail": "不能修改管理员密码"
}
```

---

## 进程管理

### POST /api/users/{username}/kill

终止指定 Linux 用户的所有进程（先 `pkill -u`，再 `pkill -9 -u` 强制清理）。不允许终止管理员进程。操作记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| username | string | Linux 用户名 |

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
  "detail": "不能终止管理员进程"
}
```

---

### POST /api/users/{username}/kill/{pid}

终止指定用户的单个进程。会校验进程是否属于该用户，不允许终止管理员进程。操作记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 类型 | 说明 |
|------|------|------|
| username | string | 进程所属用户名 |
| pid | int | 进程 ID |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "已终止进程 12345"
}
```

**失败响应** `400`:

```json
{
  "detail": "进程 12345 不属于用户 wangtao"
}
```

---

## 配额管理

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

添加单条配额记录。如果 key 已存在则返回 409 冲突。

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

| 参数 | 类型 | 说明 |
|------|------|------|
| key | string | 配额 key（用户名、`@组名` 或 `default`） |

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

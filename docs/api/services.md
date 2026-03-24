# 服务管理模块 API

提供 systemd 服务的状态查询、生命周期控制、自启动管理、资源监控、依赖分析和日志获取接口。

**路由前缀**: `/api/services`
**相关文件**: `modules/services/routes.py`, `modules/services/services.py`

---

## 端点列表

### GET /api/services/

列出所有受管 systemd 服务的状态（服务列表由配置文件 `managed_services` 字段定义）。并行查询每个服务的 `is-active` 和 `is-enabled` 状态。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "name": "nginx",
    "active": true,
    "enabled": true,
    "status_text": "active"
  },
  {
    "name": "docker",
    "active": true,
    "enabled": true,
    "status_text": "active"
  }
]
```

**错误响应** `500`: 查询失败。

---

### GET /api/services/{name}/status

获取指定 systemd 服务的详细状态信息（等同于 `systemctl status {name}` 的输出）。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称（如 `nginx`、`docker`，必须在受管列表中） |

**成功响应** `200`:

```json
{
  "name": "nginx",
  "status": "● nginx.service - A high performance web server\n   Loaded: loaded (/lib/systemd/system/nginx.service)\n   Active: active (running) since..."
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 服务不在受管列表中 |
| 500 | 获取状态失败 |

---

### POST /api/services/{name}/{action}

对 systemd 服务执行生命周期操作。通过 `sudo systemctl` 执行，超时时间 30 秒。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 可选值 | 说明 |
|------|--------|------|
| name | - | 服务名称（必须在受管列表中） |
| action | `start` / `stop` / `restart` | 要执行的操作 |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "action": "restart",
  "service": "nginx",
  "output": ""
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 服务不在受管列表或操作不支持 |
| 500 | 操作执行失败（如服务启动失败） |

---

### POST /api/services/{name}/enable

启用服务的开机自启动。通过 `sudo systemctl enable` 执行。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称（必须在受管列表中） |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "service": "nginx",
  "output": "Created symlink /etc/systemd/system/multi-user.target.wants/nginx.service..."
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 服务不在受管列表或执行失败 |

---

### POST /api/services/{name}/disable

禁用服务的开机自启动。通过 `sudo systemctl disable` 执行。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称（必须在受管列表中） |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "service": "nginx",
  "output": "Removed /etc/systemd/system/multi-user.target.wants/nginx.service."
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 服务不在受管列表或执行失败 |

---

### POST /api/services/{name}/reload

重新加载服务配置（不重启服务进程）。通过 `sudo systemctl reload` 执行。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称（必须在受管列表中） |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "service": "nginx",
  "output": ""
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 服务不在受管列表、不支持 reload 或执行失败 |

---

### GET /api/services/{name}/resources

获取服务的资源使用情况（内存、CPU 时间、进程数等）。通过 `systemctl show` 查询 `MemoryCurrent`、`CPUUsageNSec`、`MainPID`、`Tasks` 属性。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称（必须在受管列表中） |

**成功响应** `200`:

```json
{
  "MemoryCurrent": "52428800",
  "MemoryMB": 50.0,
  "CPUUsageNSec": "1500000000",
  "CPUSeconds": 1.5,
  "MainPID": "12345",
  "Tasks": "3"
}
```

> `MemoryMB` 和 `CPUSeconds` 为自动转换后的可读字段。若 cgroup 未启用相关统计，原始值可能为 `[not set]`，此时不会生成可读字段。

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 服务不在受管列表或查询失败 |

---

### GET /api/services/{name}/dependencies

获取服务的 systemd 依赖关系树。通过 `systemctl list-dependencies` 查询。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称（必须在受管列表中） |

**成功响应** `200`:

```json
{
  "service": "nginx",
  "dependencies": [
    "system.slice",
    "sysinit.target",
    "network-online.target",
    "nss-lookup.target"
  ],
  "raw": "● nginx.service\n├─system.slice\n├─sysinit.target\n│ ├─..."
}
```

> `dependencies` 为解析后的依赖服务名称列表（不含自身）。`raw` 为原始树形输出。

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 服务不在受管列表或查询失败 |

---

### GET /api/services/{name}/journal

获取服务的 systemd journal 日志。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称（必须在受管列表中） |

**查询参数**:

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| lines | int | 100 | 1 ~ 5000 | 返回最后 N 行日志 |

**成功响应** `200`:

```json
{
  "name": "nginx",
  "journal": "Mar 24 10:00:00 system-NF5468M6 nginx[12345]: 2026/03/24 10:00:00 [notice] nginx started\n..."
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 服务不在受管列表中 |
| 500 | 获取日志失败 |

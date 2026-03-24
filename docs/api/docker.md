# Docker 管理模块 API

提供 Docker 容器、镜像、Compose 堆栈、网络、卷的查询与管理接口。

**路由前缀**: `/api/docker`
**相关文件**: `modules/docker/routes.py`, `modules/docker/services.py`

---

## 端点列表

### GET /api/docker/containers

列出所有 Docker 容器（默认包含已停止的容器）。

**权限**: 任意已登录用户（user / admin）

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| all | bool | true | 是否包含已停止的容器 |

**成功响应** `200`:

```json
[
  {
    "name": "docker-nginx-1",
    "id": "abc123def456",
    "image": "nginx:latest",
    "status": "Up 3 days",
    "state": "running",
    "ports": "80/tcp -> 0.0.0.0:8080",
    "created": "2026-03-01T10:00:00"
  }
]
```

**错误响应** `500`: Docker daemon 不可用。

---

### GET /api/docker/containers/{name}/logs

获取指定容器的日志（带时间戳）。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 容器名称 |

**查询参数**:

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|--------|------|------|
| tail | int | 100 | 1 ~ 5000 | 返回最后 N 行 |

**成功响应** `200`:

```json
{
  "name": "docker-nginx-1",
  "logs": "2026-03-24 10:00:00 [notice] nginx started\n..."
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 容器名称非法 |
| 500 | 获取日志失败 |

---

### GET /api/docker/containers/{name}/stats

获取容器实时资源使用统计（CPU、内存、网络 I/O、磁盘 I/O）。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 容器名称 |

**成功响应** `200`:

```json
{
  "name": "docker-nginx-1",
  "cpu_percent": "0.50%",
  "memory_usage": "50MiB / 8GiB",
  "memory_percent": "0.61%",
  "net_io": "1.2MB / 987KB",
  "block_io": "10MB / 5MB",
  "pids": "3"
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 容器名称非法 |
| 500 | 获取统计失败 |

---

### GET /api/docker/containers/{name}/inspect

获取容器完整 inspect 信息（包含挂载、环境变量、网络等详细配置）。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 容器名称 |

**成功响应** `200`: 返回 `docker inspect` 原始 JSON 对象。

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 容器名称非法 |
| 500 | 查询失败 |

---

### POST /api/docker/containers/{name}/{action}

对容器执行生命周期操作。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 可选值 | 说明 |
|------|--------|------|
| name | - | 容器名称 |
| action | `start` / `stop` / `restart` | 要执行的操作 |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "action": "restart",
  "container": "docker-nginx-1",
  "output": "docker-nginx-1"
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 不支持的操作或容器名称非法 |
| 500 | 操作执行失败 |

---

### GET /api/docker/containers/{name}/env

获取容器的环境变量列表。敏感值（包含 KEY、SECRET、TOKEN、PASSWORD、PASS 的变量）自动脱敏为 `***`。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 容器名称 |

**成功响应** `200`:

```json
{
  "envs": [
    "PATH=/usr/local/bin:/usr/bin",
    "NGINX_VERSION=1.25.0",
    "API_KEY=***",
    "DB_PASSWORD=***"
  ]
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 容器名称非法或容器不存在 |

---

### POST /api/docker/containers/{name}/exec

在运行中的容器内执行命令。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 容器名称 |

**请求体** (`application/json`):

| 字段 | 类型 | 必填 | 限制 | 说明 |
|------|------|------|------|------|
| command | string | 是 | 1 ~ 500 字符 | 要执行的 shell 命令 |

**请求示例**:

```json
{
  "command": "ls -la /var/log"
}
```

**成功响应** `200`:

```json
{
  "ok": true,
  "output": "total 12\ndrwxr-xr-x 2 root root 4096 ...\n..."
}
```

> 输出超过 10240 字节时会自动截断。

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 容器名称非法、容器未运行或命令执行失败 |

---

### GET /api/docker/images

列出本地所有 Docker 镜像。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "ID": "sha256:abc123",
    "Repository": "nginx",
    "Tag": "latest",
    "Size": "187MB",
    "CreatedAt": "2026-02-01 00:00:00 +0800 CST"
  }
]
```

---

### DELETE /api/docker/images/{image_id}

删除指定 Docker 镜像。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| image_id | 镜像 ID 或 `repository:tag`（支持路径中包含冒号和斜杠） |

**成功响应** `200`:

```json
{
  "ok": true,
  "image_id": "sha256:abc123",
  "output": "Deleted: sha256:abc123"
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 镜像 ID 非法或镜像被容器使用 |
| 500 | 删除失败 |

---

### POST /api/docker/images/pull

拉取 Docker 镜像。操作完成后记录审计日志。超时时间 300 秒。

**权限**: admin

**请求体** (`application/json`):

| 字段 | 类型 | 必填 | 限制 | 说明 |
|------|------|------|------|------|
| image | string | 是 | 1 ~ 200 字符 | 镜像名称，如 `nginx:latest` |

**请求示例**:

```json
{
  "image": "nginx:latest"
}
```

**成功响应** `200`:

```json
{
  "ok": true,
  "output": "latest: Pulling from library/nginx\nDigest: sha256:...\nStatus: Downloaded newer image for nginx:latest"
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 镜像名称非法或拉取失败 |

---

### GET /api/docker/networks

列出所有 Docker 网络。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
{
  "networks": [
    {
      "name": "bridge",
      "id": "abc123def456",
      "driver": "bridge",
      "scope": "local"
    },
    {
      "name": "host",
      "id": "def456abc789",
      "driver": "host",
      "scope": "local"
    }
  ]
}
```

> `id` 字段为截断后的短 ID（12 字符）。

**错误响应** `500`: Docker daemon 不可用。

---

### GET /api/docker/volumes

列出所有 Docker 卷。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
{
  "volumes": [
    {
      "name": "postgres_data",
      "driver": "local",
      "mountpoint": "/var/lib/docker/volumes/postgres_data/_data"
    }
  ]
}
```

**错误响应** `500`: Docker daemon 不可用。

---

### GET /api/docker/stacks

列出所有 Docker Compose 堆栈（根据配置中的 `compose_stacks` 列表）。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "name": "dify",
    "display_name": "Dify AI 平台",
    "path": "/home/zhengxiaodong/projects/dify/docker",
    "containers": 8,
    "running": 7,
    "error": null
  }
]
```

---

### POST /api/docker/stacks/{name}/{action}

管理 Compose 堆栈。操作完成后记录审计日志。超时时间 120 秒。

**权限**: admin

**路径参数**:

| 参数 | 可选值 | 说明 |
|------|--------|------|
| name | - | 堆栈名称（对应配置中的 key） |
| action | `up` / `down` / `restart` / `pull` | 操作类型 |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "action": "restart",
  "stack": "dify",
  "output": "Container docker-nginx-1 Restarted\nContainer docker-api-1 Restarted\n..."
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 不支持的操作或堆栈不存在 |
| 500 | 操作执行失败 |

---

### POST /api/docker/prune/{resource_type}

清理未使用的 Docker 资源。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 可选值 | 说明 |
|------|--------|------|
| resource_type | `container` / `image` / `volume` / `network` / `all` | 要清理的资源类型 |

- `all` 等同于 `docker system prune -f`
- 其他值等同于 `docker {type} prune -f`

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "output": "Deleted Containers:\nabc123def456\n\nTotal reclaimed space: 1.2GB"
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 不支持的资源类型 |
| 500 | 清理执行失败 |

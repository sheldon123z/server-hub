# Docker 管理模块 API

提供 Docker 容器、镜像和 Compose 堆栈的查询与管理接口。

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
    "id": "abc123def456",
    "name": "docker-nginx-1",
    "image": "nginx:latest",
    "status": "running",
    "state": "running",
    "ports": "80/tcp -> 0.0.0.0:8080",
    "created": "2026-03-01T10:00:00"
  }
]
```

**错误响应** `500`: Docker daemon 不可用。

---

### GET /api/docker/containers/{name}/logs

获取指定容器的日志。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 容器名称或 ID |

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
| 400 | 容器不存在 |
| 500 | 获取日志失败 |

---

### GET /api/docker/containers/{name}/stats

获取容器实时资源使用统计（CPU、内存、网络 I/O）。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 容器名称或 ID |

**成功响应** `200`:

```json
{
  "name": "docker-nginx-1",
  "cpu_percent": 0.5,
  "memory_usage": 52428800,
  "memory_limit": 8589934592,
  "memory_percent": 0.61,
  "net_io_rx": 1234567,
  "net_io_tx": 987654
}
```

---

### GET /api/docker/containers/{name}/inspect

获取容器完整 inspect 信息（包含挂载、环境变量、网络等详细配置）。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 容器名称或 ID |

**成功响应** `200`: 返回 `docker inspect` 原始 JSON 对象。

---

### POST /api/docker/containers/{name}/{action}

对容器执行生命周期操作。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 可选值 | 说明 |
|------|--------|------|
| name | - | 容器名称或 ID |
| action | `start` / `stop` / `restart` | 要执行的操作 |

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "action": "restart",
  "container": "docker-nginx-1",
  "output": "Container restarted successfully"
}
```

**错误响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 不支持的操作或容器不存在 |
| 500 | 操作执行失败 |

---

### GET /api/docker/images

列出本地所有 Docker 镜像。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "id": "sha256:abc123",
    "repository": "nginx",
    "tag": "latest",
    "size": 187645952,
    "created": "2026-02-01T00:00:00"
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
| image_id | 镜像 ID 或 `repository:tag`（支持路径中包含冒号） |

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
| 400 | 镜像被容器使用，无法删除 |
| 500 | 删除失败 |

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
    "compose_file": "/home/zhengxiaodong/projects/dify/docker/docker-compose.yaml",
    "status": "running",
    "services": 8
  }
]
```

---

### POST /api/docker/stacks/{name}/{action}

管理 Compose 堆栈。操作完成后记录审计日志。

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

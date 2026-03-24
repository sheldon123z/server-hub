# 资产台账模块 API

提供服务器资产（容器、服务、端口、进程等）的自动发现、查询、手动录入和拓扑图生成接口。

**路由前缀**: `/api/assets`
**相关文件**: `modules/assets/routes.py`, `modules/assets/services.py`

> 所有端点均需要 admin 权限。

---

## 资产类型

| type 值 | 说明 |
|---------|------|
| `container` | Docker 容器 |
| `service` | systemd 服务 |
| `port` | 监听端口 |
| `process` | 系统进程 |
| `custom` | 手动添加的自定义资产 |

---

## 端点列表

### GET /api/assets/

获取资产列表，可按类型过滤。

**权限**: admin

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| type | string | `""` | 按资产类型过滤，空则返回全部 |

**成功响应** `200`:

```json
[
  {
    "id": "container:docker-nginx-1",
    "type": "container",
    "name": "docker-nginx-1",
    "status": "running",
    "properties": {
      "image": "nginx:latest",
      "ports": "8080->80/tcp"
    },
    "dependencies": ["service:docker"],
    "is_manual": false,
    "discovered_at": "2026-03-24T10:00:00"
  }
]
```

---

### POST /api/assets/discover

触发全量资产自动发现（扫描 Docker 容器、systemd 服务、监听端口、关键进程）。

**权限**: admin

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "stats": {
    "container": 12,
    "service": 15,
    "port": 32,
    "process": 8
  },
  "total": 67
}
```

---

### GET /api/assets/topology

生成资产拓扑图（Mermaid 格式），展示资产间的依赖关系。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
{
  "mermaid": "graph TD\n  service_docker[\"Docker\"]\n  container_nginx[\"docker-nginx-1\"]\n  service_docker --> container_nginx\n  ..."
}
```

返回的 `mermaid` 字段为 Mermaid 图表语法字符串，可直接渲染为可视化拓扑图。

---

### GET /api/assets/summary

获取按资产类型分组的统计概览。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
{
  "container": {
    "total": 12,
    "healthy": 10
  },
  "service": {
    "total": 15,
    "healthy": 14
  },
  "port": {
    "total": 32,
    "healthy": 32
  }
}
```

`healthy` 统计 `status` 为 `running`、`ok` 或 `listening` 的资产数量。

---

### PUT /api/assets/{asset_id}

更新资产的状态、属性或依赖关系。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| asset_id | 资产 ID（格式如 `container:docker-nginx-1`，支持路径中含冒号） |

**请求体**（所有字段可选，至少提供一个）:

```json
{
  "status": "stopped",
  "properties": {
    "image": "nginx:1.25",
    "ports": "8080->80/tcp"
  },
  "dependencies": ["service:docker", "container:docker-db-1"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 新的状态值 |
| properties | object | 属性键值对（完全替换） |
| dependencies | array | 依赖的资产 ID 列表（完全替换） |

**成功响应** `200`:

```json
{
  "ok": true
}
```

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 未提供任何可更新字段 |
| 404 | 资产不存在 |

---

### POST /api/assets/manual

手动添加自定义资产（用于记录无法自动发现的组件）。

**权限**: admin

**请求体**:

```json
{
  "type": "custom",
  "name": "MySQL 主库",
  "id": "custom:mysql-primary",
  "status": "running",
  "properties": {
    "host": "localhost",
    "port": 3306
  },
  "dependencies": ["service:mysql"]
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| type | string | 是 | 资产类型 |
| name | string | 是 | 资产显示名称 |
| id | string | 否 | 自定义 ID，默认为 `{type}:{name}` |
| status | string | 否 | 初始状态，默认 `unknown` |
| properties | object | 否 | 附加属性 |
| dependencies | array | 否 | 依赖的资产 ID 列表 |

**成功响应** `200`:

```json
{
  "ok": true,
  "id": "custom:mysql-primary"
}
```

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 400 | 缺少 `type` 或 `name` 字段 |
| 409 | 资产 ID 已存在 |

---

### DELETE /api/assets/{asset_id}

删除资产（仅允许删除手动添加的资产，自动发现的资产无法手动删除）。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| asset_id | 资产 ID |

**成功响应** `200`:

```json
{
  "ok": true
}
```

**失败响应**:

| 状态码 | 原因 |
|--------|------|
| 403 | 自动发现的资产不允许手动删除（下次发现后会自动恢复） |
| 404 | 资产不存在 |

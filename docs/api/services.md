# 服务管理模块 API

提供 systemd 服务的状态查询、控制和日志获取接口。

**路由前缀**: `/api/services`
**相关文件**: `modules/services/routes.py`, `modules/services/services.py`

---

## 端点列表

### GET /api/services/

列出所有受管 systemd 服务的状态（服务列表由配置文件 `managed_services` 字段定义）。

**权限**: 任意已登录用户（user / admin）

**请求参数**: 无

**成功响应** `200`:

```json
[
  {
    "name": "nginx",
    "active_state": "active",
    "sub_state": "running",
    "load_state": "loaded",
    "description": "A high performance web server and a reverse proxy server"
  },
  {
    "name": "docker",
    "active_state": "active",
    "sub_state": "running",
    "load_state": "loaded",
    "description": "Docker Application Container Engine"
  }
]
```

---

### GET /api/services/{name}/status

获取指定 systemd 服务的详细状态信息（等同于 `systemctl status {name}` 的输出）。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称（如 `nginx`、`docker`） |

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

对 systemd 服务执行生命周期操作。操作完成后记录审计日志。

**权限**: admin

**路径参数**:

| 参数 | 可选值 | 说明 |
|------|--------|------|
| name | - | 服务名称 |
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

### GET /api/services/{name}/journal

获取服务的 systemd journal 日志。

**权限**: 任意已登录用户（user / admin）

**路径参数**:

| 参数 | 说明 |
|------|------|
| name | 服务名称 |

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

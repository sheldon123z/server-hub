# 代理管理模块 API

提供 Clash 代理的状态查询、节点切换、配置管理和订阅更新接口。

**路由前缀**: `/api/proxy`
**相关文件**: `modules/proxy/routes.py`, `modules/proxy/services.py`

> 所有端点均需要 admin 权限。本模块通过 Clash RESTful API（默认 `127.0.0.1:9090`）与 Clash 进程通信。

---

## 端点列表

### GET /api/proxy/status

获取 Clash 代理服务的当前状态和配置摘要。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
{
  "running": true,
  "version": "1.18.0",
  "mode": "rule",
  "mixed_port": 7890,
  "allow_lan": false,
  "log_level": "info",
  "ipv6": false
}
```

---

### GET /api/proxy/groups

获取所有代理组及其当前选中节点和可用节点列表。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
{
  "groups": [
    {
      "name": "PROXY",
      "type": "Selector",
      "now": "HK-01",
      "all": ["HK-01", "HK-02", "JP-01", "US-01", "DIRECT"]
    },
    {
      "name": "Auto",
      "type": "URLTest",
      "now": "HK-01",
      "all": ["HK-01", "HK-02", "JP-01"]
    }
  ]
}
```

---

### POST /api/proxy/switch-node

切换指定代理组的当前节点。

**权限**: admin

**请求体**:

```json
{
  "group": "PROXY",
  "node": "JP-01"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| group | string | 是 | 代理组名称 |
| node | string | 是 | 目标节点名称 |

**成功响应** `200`:

```json
{
  "ok": true,
  "msg": "已切换到 JP-01"
}
```

**失败响应** `500`:

```json
{
  "ok": false,
  "msg": "切换失败"
}
```

---

### POST /api/proxy/switch-config

切换 Clash 配置文件（从预定义的配置列表中选择）。

**权限**: admin

**请求体**:

```json
{
  "config": "config_work.yaml"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| config | string | 是 | 配置文件名（相对于 Clash 配置目录） |

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "已切换到 config_work.yaml"
}
```

**失败响应** `500`:

```json
{
  "ok": false,
  "message": "配置文件不存在或格式错误"
}
```

---

### POST /api/proxy/update-subscription

更新 Clash 订阅并重载配置。

**权限**: admin

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "订阅已更新，新节点数: 120"
}
```

**失败响应** `500`:

```json
{
  "ok": false,
  "message": "订阅更新失败: connection timeout"
}
```

---

### POST /api/proxy/restart

重启 Clash 服务（通过 `systemctl restart clash`）。

**权限**: admin

**请求体**: 无

**成功响应** `200`:

```json
{
  "ok": true,
  "message": "Clash 已重启"
}
```

---

### GET /api/proxy/test-delays/{group}

测试指定代理组中所有节点的延迟。

**权限**: admin

**路径参数**:

| 参数 | 说明 |
|------|------|
| group | 代理组名称 |

**成功响应** `200`:

```json
{
  "HK-01": 45,
  "HK-02": 62,
  "JP-01": 120,
  "US-01": 280,
  "DIRECT": 5
}
```

值为毫秒数，`-1` 表示超时或不可达。

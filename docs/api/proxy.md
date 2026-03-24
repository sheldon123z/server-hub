# 代理管理模块 API

提供面向代理实例的统一运维接口，支持 `systemd` 托管的通用代理服务，并为 Clash / Mihomo 类实例提供节点组、订阅和测速等扩展能力。

**路由前缀**: `/api/proxy`
**相关文件**: `modules/proxy/routes.py`, `modules/proxy/services.py`, `data/proxy_instances.json`

> 所有端点均需要 admin 权限。代理实例由 `data/proxy_instances.json` 定义；当前默认保留旧版 Clash 单实例接口作为兼容层。

---

## 实例注册表

代理实例通过 `data/proxy_instances.json` 声明，典型字段包括:

```json
{
  "default_instance_id": "clash-main",
  "instances": [
    {
      "id": "clash-main",
      "name": "Clash 主实例",
      "type": "clash",
      "plugin": "clash",
      "service_name": "clash",
      "listen_ports": [{"label": "Mixed Port", "port": 7890}],
      "admin_api": {"base_url": "http://127.0.0.1:9090", "secret": "xxx"},
      "config_profiles": [{"key": "fastfly", "name": "FastFly"}],
      "commands": {
        "switch_config": {"argv": ["sudo", "...", "{config_arg}"]},
        "update_subscription": {"argv": ["sudo", "...", "update"]}
      },
      "capabilities": {
        "systemd_actions": ["start", "stop", "restart"],
        "node_switch": true,
        "delay_test": true
      }
    }
  ]
}
```

---

## 新版实例化接口

### GET /api/proxy/instances

列出所有代理实例及摘要状态。

**成功响应** `200`:

```json
{
  "default_instance_id": "clash-main",
  "instances": [
    {
      "id": "clash-main",
      "name": "Clash 主实例",
      "type": "clash",
      "plugin": "clash",
      "service_name": "clash",
      "running": true,
      "enabled": true,
      "current_config": "fastfly",
      "current_config_name": "FastFly",
      "supported_actions": ["start", "stop", "restart", "switch_config", "update_subscription"]
    }
  ]
}
```

### GET /api/proxy/instances/{id}

获取单个代理实例的完整状态。

**成功响应** `200`:

```json
{
  "id": "clash-main",
  "name": "Clash 主实例",
  "type": "clash",
  "plugin": "clash",
  "service_name": "clash",
  "running": true,
  "enabled": true,
  "status_text": "active",
  "pid": 1234,
  "listen_ports": [
    {"label": "Mixed Port", "port": 7890, "description": "HTTP / SOCKS5"}
  ],
  "current_config": "fastfly",
  "current_config_name": "FastFly",
  "config_profiles": [
    {"key": "original", "name": "原机场"},
    {"key": "fastfly", "name": "FastFly", "preferred_after_update": true}
  ],
  "preferred_update_config_key": "fastfly",
  "supported_actions": ["start", "stop", "restart", "switch_config", "update_subscription"],
  "capabilities": {
    "config_switch": true,
    "subscription_update": true,
    "node_switch": true,
    "delay_test": true
  },
  "available_extensions": ["clash"],
  "version": "1.18.0",
  "premium": false
}
```

### POST /api/proxy/instances/{id}/actions/{action}

执行实例级动作。

当前支持的 `action`:
- `start`
- `stop`
- `restart`
- `reload`
- `update_subscription`

**成功响应** `200`:

```json
{
  "ok": true,
  "msg": "Clash 主实例已重启",
  "output": ""
}
```

**不支持动作** `400`:

```json
{
  "ok": false,
  "unsupported": true,
  "msg": "当前实例不支持操作: 更新订阅"
}
```

### POST /api/proxy/instances/{id}/switch-config

切换实例的预定义配置。

**请求体**:

```json
{
  "config": "fastfly"
}
```

**成功响应** `200`:

```json
{
  "ok": true,
  "msg": "已切换到 FastFly",
  "output": "..."
}
```

### POST /api/proxy/instances/{id}/config-profiles

新增一个基于订阅链接的机场配置，并立即拉取订阅内容生成 Clash 配置文件。

**请求体**:

```json
{
  "name": "Kycloud 备用",
  "url": "https://subscribe.example.com/sub/auto?...",
  "switch_after_add": false
}
```

### POST /api/proxy/instances/{id}/config-profiles/{profile_key}/update-subscription

更新指定配置项的订阅内容。该端点会直接从配置项记录的订阅链接重新下载并覆盖对应配置文件。

---

## Clash / Mihomo 扩展接口

以下端点仅适用于 `plugin=clash` 的实例。

### GET /api/proxy/instances/{id}/extensions/clash/groups

获取代理组及当前节点。

### POST /api/proxy/instances/{id}/extensions/clash/switch-node

切换指定代理组节点。

**请求体**:

```json
{
  "group": "PROXY",
  "node": "JP-01"
}
```

### GET /api/proxy/instances/{id}/extensions/clash/test-delays/{group}

测试指定代理组的延迟。

---

## 兼容旧版 Clash API

以下端点仍然保留，全部指向 `default_instance_id` 对应的实例，便于旧页面或旧脚本继续工作:

- `GET /api/proxy/status`
- `GET /api/proxy/groups`
- `POST /api/proxy/switch-node`
- `POST /api/proxy/switch-config`
- `POST /api/proxy/update-subscription`
- `POST /api/proxy/restart`
- `GET /api/proxy/test-delays/{group}`

如果默认实例不是 Clash / Mihomo，相关旧接口可能返回空结果或不支持错误。

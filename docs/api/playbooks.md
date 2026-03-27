# 运维剧本 API

前缀: `/api/playbooks`，所有端点需 admin 角色。

---

## 剧本管理

### GET `/` — 列出剧本

查询参数: `category` (可选，筛选类别)

响应: Playbook 数组

### GET `/{id}` — 获取剧本详情

响应: Playbook 对象

### POST `/` — 创建剧本

请求体:
```json
{
  "id": "check_nginx",
  "name": "检查 Nginx 配置",
  "description": "...",
  "category": "system",
  "system_prompt": "你是 Nginx 运维专家...\n## 步骤\n1. ...",
  "parameters": "[{\"name\":\"config_path\",\"type\":\"string\",\"default\":\"/etc/nginx/nginx.conf\"}]",
  "tools_required": "ssh_execute_command,think",
  "validation_rules": "{\"timeout_seconds\":120}",
  "trigger_config": "{\"type\":\"manual\"}",
  "tags": "nginx,config"
}
```

响应: `{"ok": true, "id": "check_nginx"}`

### PUT `/{id}` — 更新剧本

请求体: 仅包含需更新的字段

### DELETE `/{id}` — 删除剧本

内置剧本 (`is_builtin=1`) 不可删除。

---

## 执行

### POST `/{id}/run-async` — 后台异步执行

请求体:
```json
{
  "parameters": {
    "switch_ip": "192.168.1.1",
    "username": "admin",
    "password": "secret123"
  }
}
```

响应: `{"ok": true, "message": "剧本 '交换机 VLAN 信息采集' 已在后台启动执行"}`

### GET `/{id}/executions` — 执行历史

查询参数: `limit` (默认 20)

### GET `/executions/{exec_id}` — 执行详情

包含完整 `report` 字段。

### POST `/executions/{exec_id}/cancel` — 取消执行

---

## 凭据管理

### GET `/credentials` — 列出凭据

返回凭据元数据（名称、类型），**不包含密文值**。

### POST `/credentials` — 存储凭据

请求体:
```json
{
  "name": "switch_default_password",
  "value": "actual_password_here",
  "description": "交换机默认密码",
  "credential_type": "ssh_password"
}
```

值通过 Fernet 对称加密存储。

### DELETE `/credentials/{name}` — 删除凭据

---

## 参数类型

| 类型 | 说明 | 前端渲染 |
|------|------|---------|
| `string` | 文本 | 文本输入框 |
| `string[]` | 文本数组 | 多行输入 / 标签 |
| `number` | 数值 | 数字输入框 |
| `boolean` | 布尔 | 开关 |
| `secret` | 加密凭据 | 密码框 + 凭据选择器 |

`secret` 类型参数可通过 `credential_ref` 引用已存储的凭据，运行时自动解密注入。

---

## Agent 工具集成

Agent 可在对话中通过以下工具管理剧本:

| 工具 | 风险等级 | 说明 |
|------|---------|------|
| `ssh_execute_command` | DANGER | SSH 连接远程设备执行命令 |
| `playbook_create` | MODERATE | 从对话创建新剧本 |
| `playbook_execute` | MODERATE | 执行已保存的剧本 |
| `playbook_list` | SAFE | 列出可用剧本 |
| `playbook_search` | SAFE | 按关键词搜索剧本 |

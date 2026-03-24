# 系统设置模块 API

提供非敏感系统配置项的查询接口。

**路由前缀**: `/api/settings`
**相关文件**: `modules/settings/routes.py`, `config.py`

---

## 端点列表

### GET /api/settings/

获取当前系统配置（仅返回非敏感配置项，不包含密钥、密码等敏感信息）。

**权限**: admin

**请求参数**: 无

**成功响应** `200`:

```json
{
  "metrics_interval": 300,
  "retention_days": 30,
  "managed_services": [
    "nginx",
    "docker",
    "clash",
    "ollama",
    "jupyterlab",
    "mysql",
    "fail2ban"
  ],
  "compose_stacks": [
    {
      "name": "dify",
      "compose_file": "/home/zhengxiaodong/projects/dify/docker/docker-compose.yaml"
    },
    {
      "name": "lobe",
      "compose_file": "/mnt/sda/container_mount/lobe-chat-db/docker-compose.yml"
    }
  ],
  "log_dirs": [
    "/var/log",
    "/home/zhengxiaodong/logs"
  ],
  "admin_linux_users": [
    "zhengxiaodong",
    "root"
  ]
}
```

| 字段 | 说明 |
|------|------|
| metrics_interval | 指标采集间隔（秒） |
| retention_days | 历史指标保留天数 |
| managed_services | 受管 systemd 服务列表 |
| compose_stacks | 受管 Compose 堆栈列表 |
| log_dirs | 日志查看白名单目录 |
| admin_linux_users | 管理员 Linux 用户（监控时跳过） |

> 通过环境变量 `SERVERHUB_*` 或 `.env` 文件修改配置，重启服务后生效。

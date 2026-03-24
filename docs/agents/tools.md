# Agent 工具详细说明

所有工具定义在 `modules/agents/tools.py`，通过 `get_server_tools()` 注册到主 Agent。
工具使用 LangChain `@tool` 装饰器，框架通过 Filesystem / TodoList middleware 额外注入 9 个内置工具。

---

## 自定义工具（22 个）

### safe — 只读查询（15 个）

这些工具不修改系统状态，可在 supervised 和 autonomous 模式下自由调用。

#### get_system_overview

获取系统状态概览：CPU 使用率、内存、Swap、磁盘、GPU、负载、运行时间。

| 属性 | 值 |
|------|---|
| 参数 | 无 |
| 返回 | Markdown 格式的多行字符串 |
| 数据来源 | `modules/dashboard/collectors.py:get_system_info()` |

返回示例：
```
## 系统状态
- CPU: 12.3% (160核)
- 内存: 45.6% (229.4/503.0 GB)
- Swap: 0.0% (0.0/8.0 GB)
- 系统盘: 38.2% (1.3/3.5 GB)
- 负载: [45.2, 43.1, 40.6]
- GPU: 87% 利用率, 65536/81920MiB 显存, 72°C
- 运行时间: 45 days, 3:12:05
```

---

#### get_disk_info

获取所有磁盘挂载点的使用情况（系统盘 `/` 以外的挂载点）。

| 属性 | 值 |
|------|---|
| 参数 | 无 |
| 返回 | Markdown 表格，含挂载点、设备、使用率、容量 |
| 数据来源 | `modules/dashboard/collectors.py:get_extra_disks()` |

---

#### get_user_resources

获取所有非管理员用户的资源使用情况。

| 属性 | 值 |
|------|---|
| 参数 | 无 |
| 返回 | Markdown 表格：用户名 / 内存(GB) / 进程数 / GPU显存(MiB) |
| 数据来源 | `modules/users/services.py:get_user_stats()` |

---

#### get_user_quotas

获取所有用户资源配额配置（读取 `config/user-quotas.conf`）。

| 属性 | 值 |
|------|---|
| 参数 | 无 |
| 返回 | Markdown 表格：标识 / 内存上限(GB) / 进程上限 / 备注 |

---

#### list_docker_containers

列出所有 Docker 容器及其运行状态。

| 属性 | 值 |
|------|---|
| 参数 | 无 |
| 返回 | Markdown 表格：容器名 / 状态 / 镜像 |
| 说明 | 包含全部容器（含已停止），等价于 `docker ps -a` |

---

#### get_container_logs

获取指定 Docker 容器的最近日志。

| 属性 | 值 |
|------|---|
| 参数 | `name: str`（容器名）、`tail: int`（行数，默认 50，上限 200）|
| 返回 | Markdown 代码块，最多截取 3000 字符 |

---

#### list_systemd_services

列出所有管理的 systemd 服务及其状态。

| 属性 | 值 |
|------|---|
| 参数 | 无 |
| 返回 | Markdown 表格：服务名 / 运行状态 / 是否自启 |
| 说明 | 仅显示 `settings.managed_services` 白名单中的服务 |

---

#### get_service_logs

获取指定 systemd 服务的 journald 日志。

| 属性 | 值 |
|------|---|
| 参数 | `name: str`（服务名）、`lines: int`（行数，默认 50，上限 200）|
| 返回 | Markdown 代码块，最多截取 3000 字符 |
| 说明 | 服务名必须在 `settings.managed_services` 白名单中 |

---

#### analyze_resource_trend

分析系统资源的历史趋势，查询监控数据库中的指标历史。

| 属性 | 值 |
|------|---|
| 参数 | `metric: str`（all/cpu/memory/gpu/disk，默认 all）、`hours: int`（时间范围小时数，默认 168）|
| 返回 | 统计报告：均值、峰值、P95、最低值、趋势方向、7 天预测 |

支持指标：

| 指标键 | 含义 |
|-------|------|
| cpu | CPU 使用率(%) |
| memory | 内存使用率(%) |
| swap | Swap 使用率(%) |
| disk | 系统盘使用率(%) |
| gpu_util | GPU 利用率(%) |
| gpu_mem | GPU 显存使用率(%) |
| gpu_temp | GPU 温度(°C) |

---

#### check_compliance

执行 CIS Benchmark 安全合规基线检查。

| 属性 | 值 |
|------|---|
| 参数 | `category: str`（分类过滤，留空检查全部）|
| 返回 | 合规率 + Markdown 表格（检查项 / 结果 / 严重级别 / 详情）|
| 数据来源 | `data/compliance_baselines.json`（15 条基线）|

---

#### search_fault_cases

从历史故障案例库中检索匹配的问题和解决方案。

| 属性 | 值 |
|------|---|
| 参数 | `query: str`（搜索关键词）|
| 返回 | 最多 5 条匹配案例（标题 / 症状 / 根因 / 解决方案 / 标签）|
| 搜索机制 | 优先使用 FTS5 全文搜索，降级为 LIKE 查询 |

---

#### save_fault_case

将故障案例保存到案例库，并更新 FTS5 全文索引。

| 属性 | 值 |
|------|---|
| 参数 | `title, category, symptoms, root_cause, solution, tags` |
| 返回 | 保存成功的案例 ID |
| 分类枚举 | memory / docker / service / network / security / gpu |

---

#### get_asset_inventory

查询服务器资产清单（服务、容器、端口、存储等）。

| 属性 | 值 |
|------|---|
| 参数 | `asset_type: str`（service/container/compose/port/storage，留空返回全部）|
| 返回 | 按类型分组的资产列表 |

---

#### get_asset_topology

获取资产依赖关系拓扑图（文本形式）。

| 属性 | 值 |
|------|---|
| 参数 | 无 |
| 返回 | 资产依赖关系的 Markdown 描述 |

---

#### send_notification

发送 Telegram 通知消息。

| 属性 | 值 |
|------|---|
| 参数 | `message: str`（消息内容）|
| 返回 | 成功/失败信息 |
| 风险级别 | safe（TOOL_RISK_MAP 中标记，因为只是通知，不影响系统）|

---

### moderate — 可逆操作（6 个）

这些工具会修改系统状态，但操作可撤销。supervised 模式下部分需要审批。

#### docker_container_action

对单个 Docker 容器执行操作。

| 属性 | 值 |
|------|---|
| 参数 | `name: str`（容器名）、`action: str`（start / stop / restart）|
| 返回 | 执行结果描述 |
| 审批触发 | supervised 模式下触发 interrupt_on 审批 |

---

#### docker_compose_action

对 Docker Compose 堆栈执行操作。

| 属性 | 值 |
|------|---|
| 参数 | `stack_name: str`（dify / lobe / grid-autopilot）、`action: str`（up / down / restart / pull）|
| 返回 | 执行结果描述 |
| 审批触发 | supervised 模式下触发 interrupt_on 审批 |

---

#### service_control

管理 systemd 服务（只允许白名单内的服务）。

| 属性 | 值 |
|------|---|
| 参数 | `name: str`（服务名）、`action: str`（start / stop / restart）|
| 返回 | 执行结果描述 |
| 审批触发 | supervised 模式下触发 interrupt_on 审批 |

---

#### update_user_quotas

修改用户资源配额（写入 `config/user-quotas.conf`）。

| 属性 | 值 |
|------|---|
| 参数 | `key: str`（用户名或 @组名）、`mem_gb: int`、`proc_limit: int`、`comment: str`（可选）|
| 返回 | 更新确认信息 |

---

#### create_cron_job

创建 cron 定时任务。

| 属性 | 值 |
|------|---|
| 参数 | 具体字段见 cron 模块文档 |
| 审批触发 | supervised 模式下触发审批（approved_decisions: approve/reject）|

---

#### modify_cron_schedule / toggle_cron_job_tool

修改 cron 任务调度周期 / 启用或禁用 cron 任务。

| 属性 | 值 |
|------|---|
| 风险级别 | moderate |

---

### danger — 高风险操作（4 个）

这些工具操作不可逆或风险极高。supervised 模式下始终触发审批，autonomous 模式下仍受 Shell 黑名单约束。

#### kill_user_processes

终止指定用户的所有进程。

| 属性 | 值 |
|------|---|
| 参数 | `username: str`（要终止进程的用户名）|
| 返回 | 执行结果描述 |
| 限制 | 不能终止管理员用户（zhengxiaodong, root）|
| 审批触发 | supervised 模式下始终触发审批 |

---

#### auto_fix_compliance

自动修复指定的不合规项，执行 `fix_cmd` 并验证修复结果。

| 属性 | 值 |
|------|---|
| 参数 | `item_id: str`（合规基线项 ID）|
| 返回 | 修复前 / 后对比 + 修复状态 |
| 限制 | 仅对 `auto_fixable: true` 的基线项有效 |
| 审批触发 | supervised 模式下始终触发审批 |

---

#### execute_ops_script

执行注册的运维管理脚本（通过 `scripts_bridge` 白名单机制）。

| 属性 | 值 |
|------|---|
| 参数 | `script_key: str`（如 dify_manage, health_check）、`args: list[str]`（可选）|
| 返回 | 脚本 stdout + 退出码，最多截取 3000 字符 |
| 限制 | 只能执行 `SCRIPT_REGISTRY` 白名单中的脚本 |
| 审批触发 | supervised 模式下始终触发审批 |

---

#### delete_cron_job_tool

删除 cron 定时任务（不可恢复）。

| 属性 | 值 |
|------|---|
| 参数 | 任务标识 |
| 审批触发 | supervised 模式下始终触发审批 |

---

## 框架内置工具（9 个）

这些工具由 Deep Agents 框架通过 `Filesystem` 和 `TodoList` middleware 自动注入，无需在 `tools.py` 中定义。

| 工具名 | 风险级别 | 说明 |
|--------|---------|------|
| `execute` | danger | Shell 命令执行（由 SafeLocalShellBackend 处理）|
| `read_file` | safe | 读取文件内容 |
| `write_file` | moderate | 写入文件（系统路径需审批）|
| `edit_file` | moderate | 编辑文件（系统路径需审批）|
| `ls` | safe | 列出目录内容 |
| `glob` | safe | 文件名模式匹配 |
| `grep` | safe | 在文件中搜索内容 |
| `write_todos` | safe | 更新任务列表 |
| `task` | safe | 委派任务给子智能体 |

`execute` 工具在 supervised 模式下会对匹配 `rm|sudo|kill|shutdown|reboot|mkfs|dd|chmod|chown|systemctl.*(stop|disable)|iptables` 的命令触发审批。

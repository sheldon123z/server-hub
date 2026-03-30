# Agent 工具详细说明

工具按功能领域拆分为 14 个子模块，存放在 `modules/agents/tools/` 目录下：

```
modules/agents/tools/
├── __init__.py          # 导出入口：get_server_tools(user_role)
├── system.py            # 系统监控（3 个工具）
├── docker.py            # Docker 管理（7 个工具）
├── services.py          # Systemd 服务（5 个工具）
├── users.py             # 用户管理（10 个工具）
├── cron.py              # 定时任务（6 个工具）
├── assets.py            # 资产与故障案例（4 个工具）
├── knowledge.py         # RAG 知识库（2 个工具）
├── security.py          # 安全合规（2 个工具）
├── notifications.py     # 通知推送（1 个工具）
├── scripts.py           # 运维脚本桥接（1 个工具）
├── playbook.py          # 运维剧本 + SSH（5 个工具）
├── servers.py           # 服务器舰队管理（2 个工具）
└── page_context_tool.py # 页面上下文数据查询（1 个工具）
```

通过 `get_server_tools(user_role)` 注册到主 Agent：
- **admin**: 返回全部 49 个自定义工具
- **user**: 仅返回 SAFE 级别的只读工具

工具使用 LangChain `@tool` 装饰器，分布在 14 个子模块中。框架通过 Filesystem / TodoList middleware 额外注入 9 个内置工具。

---

## 自定义工具（49 个）

### safe — 只读查询（21 个 + 4 个新增）

这些工具不修改系统状态，可在 supervised 和 autonomous 模式下自由调用。

---

#### get_system_overview

- **风险等级**: safe
- **说明**: 获取系统状态概览：CPU 使用率、内存、Swap、磁盘、GPU、负载、运行时间。
- **参数**: 无
- **返回**: Markdown 格式的多行字符串
- **数据来源**: `modules/dashboard/collectors.py:get_system_info()`
- **使用场景**: 快速了解服务器当前整体状态，巡检时首先调用

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

- **风险等级**: safe
- **说明**: 获取所有磁盘挂载点的使用情况（系统盘 `/` 以外的挂载点）。
- **参数**: 无
- **返回**: Markdown 表格，含挂载点、设备、使用率、容量
- **数据来源**: `modules/dashboard/collectors.py:get_extra_disks()`
- **使用场景**: 检查存储空间是否充足，排查磁盘满的问题

---

#### get_user_resources

- **风险等级**: safe
- **说明**: 获取所有非管理员用户的资源使用情况。
- **参数**: 无
- **返回**: Markdown 表格：用户名 / 内存(GB) / 进程数 / GPU显存(MiB)
- **数据来源**: `modules/users/services.py:get_user_stats()`
- **使用场景**: 监控学生用户资源占用，发现超配额用户

---

#### get_user_quotas

- **风险等级**: safe
- **说明**: 获取所有用户资源配额配置（读取 `config/user-quotas.conf`）。
- **参数**: 无
- **返回**: Markdown 表格：标识 / 内存上限(GB) / 进程上限 / 备注
- **使用场景**: 查看当前配额设置，与实际用量对比

---

#### list_docker_containers

- **风险等级**: safe
- **说明**: 列出所有 Docker 容器及其运行状态。
- **参数**: 无
- **返回**: Markdown 表格：容器名 / 状态 / 镜像
- **说明**: 包含全部容器（含已停止），等价于 `docker ps -a`
- **使用场景**: 检查容器健康状态，发现异常停止或频繁重启的容器

---

#### get_container_logs

- **风险等级**: safe
- **说明**: 获取指定 Docker 容器的最近日志。
- **参数**: `name: str`（容器名）、`tail: int`（行数，默认 50，上限 200）
- **返回**: Markdown 代码块，最多截取 3000 字符
- **使用场景**: 排查容器崩溃、错误日志分析

---

#### list_systemd_services

- **风险等级**: safe
- **说明**: 列出所有管理的 systemd 服务及其状态。
- **参数**: 无
- **返回**: Markdown 表格：服务名 / 运行状态 / 是否自启
- **说明**: 仅显示 `settings.managed_services` 白名单中的服务
- **使用场景**: 检查关键服务运行状态

---

#### get_service_logs

- **风险等级**: safe
- **说明**: 获取指定 systemd 服务的 journald 日志。
- **参数**: `name: str`（服务名）、`lines: int`（行数，默认 50，上限 200）
- **返回**: Markdown 代码块，最多截取 3000 字符
- **说明**: 服务名必须在 `settings.managed_services` 白名单中
- **使用场景**: 排查服务启动失败、异常退出

---

#### analyze_resource_trend

- **风险等级**: safe
- **说明**: 分析系统资源的历史趋势，查询监控数据库中的指标历史，计算统计量和趋势预测。
- **参数**: `metric: str`（all/cpu/memory/gpu/disk，默认 all）、`hours: int`（时间范围小时数，默认 168）
- **返回**: 统计报告：均值、峰值、P95、最低值、趋势方向、7 天预测
- **使用场景**: 容量规划、资源瓶颈预判、趋势报告

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

- **风险等级**: safe
- **说明**: 执行 CIS Benchmark 安全合规基线检查。
- **参数**: `category: str`（分类过滤，留空检查全部）
- **返回**: 合规率 + Markdown 表格（检查项 / 结果 / 严重级别 / 详情）
- **数据来源**: `data/compliance_baselines.json`
- **使用场景**: 安全巡检、合规审计

---

#### search_fault_cases

- **风险等级**: safe
- **说明**: 从历史故障案例库中检索匹配的问题和解决方案。
- **参数**: `query: str`（搜索关键词）
- **返回**: 最多 5 条匹配案例（标题 / 症状 / 根因 / 解决方案 / 标签）
- **搜索机制**: 优先使用 FTS5 全文搜索，降级为 LIKE 查询
- **使用场景**: 遇到问题时先查案例库，避免重复排查

---

#### save_fault_case

- **风险等级**: safe
- **说明**: 将故障案例保存到案例库，并更新 FTS5 全文索引。
- **参数**: `title: str`, `category: str`, `symptoms: str`, `root_cause: str`, `solution: str`, `tags: str`（可选，逗号分隔）
- **返回**: 保存成功的案例 ID
- **分类枚举**: memory / docker / service / network / security / gpu
- **使用场景**: 故障解决后沉淀经验，供后续检索

---

#### get_asset_inventory

- **风险等级**: safe
- **说明**: 查询服务器资产清单（服务、容器、端口、存储等）。
- **参数**: `asset_type: str`（service/container/compose/port/storage，留空返回全部）
- **返回**: 按类型分组的资产列表
- **使用场景**: 资产盘点、了解服务器上运行了哪些服务

---

#### get_asset_topology

- **风险等级**: safe
- **说明**: 生成服务器资产拓扑关系图（Mermaid 格式）并分析潜在风险（单点故障、冗余不足等）。
- **参数**: 无
- **返回**: Mermaid 图 + 风险分析文本
- **使用场景**: 了解服务间依赖关系，发现单点故障风险

---

#### send_notification

- **风险等级**: safe
- **说明**: 发送 Telegram 通知消息。
- **参数**: `message: str`（消息内容）
- **返回**: 成功/失败信息
- **使用场景**: 告警通知、巡检结果推送

---

#### get_service_dependencies_tool

- **风险等级**: safe
- **说明**: 获取 systemd 服务的依赖关系树。
- **参数**: `name: str`（服务名称）
- **返回**: 依赖项列表（最多 30 项）
- **使用场景**: 了解服务依赖链，排查服务启动顺序问题，评估停止某服务的影响范围

---

#### list_docker_networks

- **风险等级**: safe
- **说明**: 列出 Docker 网络，包含名称、驱动和范围。
- **参数**: 无
- **返回**: Docker 网络列表（名称 / 驱动 / 范围）
- **使用场景**: 排查容器网络连通性问题，了解网络拓扑

---

#### get_user_login_history_tool

- **风险等级**: safe
- **说明**: 查询 Linux 用户登录历史。可以查看谁在什么时候从哪个 IP 登录了服务器。
- **参数**: `username: str`（留空查所有用户）、`count: int`（最多返回条数，默认 10，上限 50）
- **返回**: 登录记录列表
- **使用场景**: 安全审计、追踪异常登录、确认用户活跃度

---

#### get_active_sessions_tool

- **风险等级**: safe
- **说明**: 获取当前服务器上的活跃登录会话。
- **参数**: 无
- **返回**: 活跃会话列表（用户名 / TTY / 登录时间 / 来源 IP）
- **使用场景**: 查看谁在线、排查挂机用户、安全审计

---

#### list_cron_jobs

- **风险等级**: safe
- **说明**: 列出指定用户的 cron 定时任务，包含执行时间、命令、启用状态。
- **参数**: `cron_user: str`（Linux 用户名，默认 "zhengxiaodong"，使用 "root" 查看 root 的任务）
- **返回**: 定时任务列表（启用状态 / 调度表达式 / 描述 / 命令 / 备注）
- **使用场景**: 检查定时任务配置，排查任务未执行问题

---

#### validate_cron_expr

- **风险等级**: safe
- **说明**: 验证 cron 表达式是否合法，返回中文描述和未来 5 次执行时间。
- **参数**: `expression: str`（5 字段的 cron 表达式，如 "0 8 * * *"）
- **返回**: 表达式描述 + 未来 5 次执行时间
- **使用场景**: 创建或修改定时任务前验证表达式正确性

---

#### server_list

- **风险等级**: safe
- **说明**: 列出所有已注册的服务器，包括状态和基本信息。
- **参数**: 无
- **返回**: 服务器列表（ID/名称/IP/状态/标签/最后心跳）
- **使用场景**: 查看舰队状态，获取 server_id 供后续操作

---

#### server_test_connectivity

- **风险等级**: safe
- **说明**: 测试指定服务器的连通性（Ping + SSH + Agent API）。
- **参数**: `server_id: str`（通过 server_list 获取）
- **返回**: Ping 延迟、SSH 连接状态、Agent API 状态
- **使用场景**: 诊断服务器连接问题

---

#### get_page_data

- **风险等级**: safe
- **说明**: 获取指定页面的实时数据摘要。用户从浮动气泡对话框提问时调用。
- **参数**: `page_name: str`（dashboard/docker/users/services 等 14 种页面）
- **返回**: 页面最新数据摘要
- **使用场景**: ChatWidget 页面上下文感知

---

### moderate — 可逆操作（10 个）

这些工具会修改系统状态，但操作可撤销。supervised 模式下需要审批。

---

#### docker_container_action

- **风险等级**: moderate
- **说明**: 对单个 Docker 容器执行操作。
- **参数**: `name: str`（容器名）、`action: str`（start / stop / restart）
- **返回**: 执行结果描述
- **审批触发**: supervised 模式下触发 interrupt_on 审批（approve/reject）
- **使用场景**: 重启异常容器、启动已停止的服务

---

#### docker_compose_action

- **风险等级**: moderate
- **说明**: 对 Docker Compose 堆栈执行操作。
- **参数**: `stack_name: str`（dify / lobe / grid-autopilot）、`action: str`（up / down / restart / pull）
- **返回**: 执行结果描述
- **审批触发**: supervised 模式下触发 interrupt_on 审批（approve/reject）
- **使用场景**: 重启整个服务栈、更新镜像

---

#### service_control

- **风险等级**: moderate
- **说明**: 管理 systemd 服务（只允许白名单内的服务）。
- **参数**: `name: str`（服务名）、`action: str`（start / stop / restart）
- **返回**: 执行结果描述
- **审批触发**: supervised 模式下触发 interrupt_on 审批（approve/reject）
- **使用场景**: 重启崩溃的服务、手动停止维护中的服务

---

#### update_user_quotas

- **风险等级**: moderate
- **说明**: 修改用户资源配额（写入 `config/user-quotas.conf`）。
- **参数**: `key: str`（用户名或 @组名）、`mem_gb: int`、`proc_limit: int`、`comment: str`（可选）
- **返回**: 更新确认信息
- **使用场景**: 调整用户资源限制、新增用户配额

---

#### service_enable_disable_tool

- **风险等级**: moderate
- **说明**: 启用或禁用 systemd 服务的自启动。
- **参数**: `name: str`（服务名称，如 nginx, docker）、`action: str`（"enable" 开机自启 / "disable" 禁止自启）
- **返回**: 操作结果描述
- **审批触发**: supervised 模式下触发 interrupt_on 审批（approve/reject）
- **使用场景**: 设置服务开机自启、禁止不需要的服务自动运行

---

#### docker_container_exec

- **风险等级**: moderate
- **说明**: 在运行中的 Docker 容器内执行命令。
- **参数**: `container_name: str`（容器名称）、`command: str`（要执行的 shell 命令）
- **返回**: 命令输出（最多截取 5000 字符）
- **审批触发**: supervised 模式下触发 interrupt_on 审批（approve/reject）
- **使用场景**: 在容器内排查问题、查看容器内部状态、执行维护命令

---

#### kill_single_process_tool

- **风险等级**: moderate
- **说明**: 终止指定用户的单个进程。
- **参数**: `pid: int`（进程 ID）、`username: str`（进程所属用户，用于安全校验）
- **返回**: 操作结果描述
- **审批触发**: supervised 模式下触发 interrupt_on 审批（approve/reject）
- **使用场景**: 终止占用资源过高的单个进程，比 kill_user_processes 更精细

---

#### create_cron_job

- **风险等级**: moderate
- **说明**: 创建新的 cron 定时任务。内置安全检查：命令不能包含 Shell 黑名单模式。
- **参数**: `cron_user: str`（Linux 用户名）、`schedule: str`（cron 表达式）、`command: str`（完整命令，使用绝对路径）、`comment: str`（可选备注）
- **返回**: 创建结果 + 下次执行时间
- **审批触发**: supervised 模式下触发 interrupt_on 审批（approve/reject）
- **使用场景**: 添加定时监控脚本、定期清理任务

---

#### modify_cron_schedule

- **风险等级**: moderate
- **说明**: 修改已有 cron 任务的执行时间。
- **参数**: `cron_user: str`（Linux 用户名）、`old_schedule: str`（当前表达式）、`command: str`（任务命令，用于定位）、`new_schedule: str`（新表达式）
- **返回**: 修改结果 + 新的下次执行时间
- **使用场景**: 调整任务执行频率

---

#### toggle_cron_job_tool

- **风险等级**: moderate
- **说明**: 启用或禁用 cron 定时任务（通过注释/取消注释实现）。
- **参数**: `cron_user: str`、`schedule: str`、`command: str`、`enabled: bool`（True=启用, False=禁用）
- **返回**: 操作结果描述
- **使用场景**: 临时停用某个定时任务而不删除它

---

### danger — 高风险操作（6 个）

这些工具操作不可逆或风险极高。supervised 模式下始终触发审批，autonomous 模式下仍受 Shell 黑名单约束。

---

#### kill_user_processes

- **风险等级**: danger
- **说明**: 终止指定用户的所有进程。不能终止管理员用户的进程。
- **参数**: `username: str`（要终止进程的用户名）
- **返回**: 执行结果描述
- **限制**: 不能终止管理员用户（zhengxiaodong, root）
- **审批触发**: supervised 模式下始终触发审批
- **使用场景**: 用户进程失控时的紧急清理

---

#### auto_fix_compliance

- **风险等级**: danger
- **说明**: 自动修复指定的不合规项，执行 `fix_cmd` 并验证修复结果。
- **参数**: `item_id: str`（合规基线项 ID，如 ssh_empty_password, ssh_max_auth_tries）
- **返回**: 修复前 / 后对比 + 修复状态
- **限制**: 仅对 `auto_fixable: true` 的基线项有效
- **审批触发**: supervised 模式下始终触发审批
- **使用场景**: 自动化修复安全合规问题

---

#### execute_ops_script

- **风险等级**: danger
- **说明**: 执行注册的运维管理脚本（通过 `scripts_bridge` 白名单机制）。
- **参数**: `script_key: str`（如 dify_manage, health_check）、`args: list[str]`（可选参数列表）
- **返回**: 脚本 stdout + 退出码，最多截取 3000 字符
- **限制**: 只能执行 `SCRIPT_REGISTRY` 白名单中的脚本
- **审批触发**: supervised 模式下始终触发审批
- **使用场景**: 执行预定义的运维脚本，如健康检查、Dify 管理

---

#### manage_linux_user

- **风险等级**: danger
- **说明**: 管理 Linux 用户：创建、删除或修改。此操作影响系统级别用户，需谨慎。
- **参数**: `action: str`（"create" / "delete" / "modify"）、`username: str`（目标用户名）、`groups: str`（逗号分隔的附加组，如 "students,docker"，可选）、`shell: str`（登录 shell，默认 /bin/bash）
- **返回**: 操作结果描述
- **审批触发**: supervised 模式下始终触发审批
- **使用场景**: 新增学生用户、调整用户组、删除离职用户

---

#### docker_prune

- **风险等级**: danger
- **说明**: 清理未使用的 Docker 资源。此操作不可逆。
- **参数**: `resource_type: str`（"container" 停止的容器 / "image" 悬空镜像 / "volume" 未用卷 / "all" 全部，默认 "all"）
- **返回**: 清理结果（最多 2000 字符）
- **审批触发**: supervised 模式下始终触发审批
- **使用场景**: 回收磁盘空间，清理无用的容器/镜像/卷

---

#### delete_cron_job_tool

- **风险等级**: danger
- **说明**: 删除 cron 定时任务。此操作不可逆，建议先备份 crontab。
- **参数**: `cron_user: str`（Linux 用户名）、`schedule: str`（cron 表达式）、`command: str`（任务命令）
- **返回**: 删除确认信息
- **审批触发**: supervised 模式下始终触发审批
- **使用场景**: 删除不再需要的定时任务

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

`write_file` / `edit_file` 在写入路径匹配 `/etc/|\.api_keys|\.telegram_config|config\.yaml|\.env` 时触发审批。

---

## RAG 知识库工具（2 个）— `tools/knowledge.py`

#### retrieve_knowledge

- **风险等级**: safe
- **说明**: 语义搜索 + 关键词混合检索知识库，支持多种数据源。
- **参数**: `query: str`（搜索查询）、`source: str`（数据源：ops-docs/api-docs/fault_case/patrol_history/agent-memory，留空搜索全部）、`top_k: int`（返回数量，默认 5）
- **返回**: 检索到的相关文档片段（含来源和相似度）
- **使用场景**: 查找运维文档、API 说明、历史巡检报告、故障案例

---

#### reindex_knowledge_base

- **风险等级**: safe
- **说明**: 手动触发知识库全量重建索引（ChromaDB）。
- **参数**: 无
- **返回**: 索引构建结果统计
- **使用场景**: 文档更新后刷新知识库索引

---

## 工具风险分布汇总

| 风险级别 | 自定义工具 | 框架内置 | SubAgent 专属 | 合计 |
|---------|-----------|---------|-------------|------|
| safe | 28 | 5 | 2 | 35 |
| moderate | 12 | 2 | 0 | 14 |
| danger | 7 | 1 | 0 | 8 |
| **合计** | **47** | **8** | **2** | **57** |

> 注：自定义工具 49 个（含 5 个剧本工具 + 2 个服务器工具 + 1 个页面上下文工具），部分工具未在 TOOL_RISK_MAP 中注册但默认为 safe。框架通过 Middleware 注入 8 个内置工具（不含 execute 的 9 个），SubAgent 专属工具 2 个（web_search, think）。

---

## 运维剧本工具 — playbook.py（5 个）

| 工具 | 风险 | 说明 |
|------|------|------|
| `ssh_execute_command` | danger | SSH 连接远程设备执行命令，支持密码/密钥认证，内置命令黑名单 |
| `playbook_create` | moderate | 从对话创建新剧本模板（参数化工作流） |
| `playbook_execute` | moderate | 执行已保存的剧本，自动解析参数和解密凭据 |
| `playbook_list` | safe | 列出可用剧本，支持按类别筛选 |
| `playbook_search` | safe | 按关键词搜索剧本 |

`ssh_execute_command` 使用 `asyncssh` 库，支持:
- 密码或 SSH 私钥认证
- 每条命令独立超时（默认 30s）
- 输出截断（10000 字符/命令）+ ANSI 转义码清理
- 命令黑名单（rm -rf /, mkfs, dd, reboot, shutdown 等）
- supervised 模式下需要用户审批

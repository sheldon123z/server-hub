"""内置剧本模板 — 启动时自动导入"""

DEFAULT_PLAYBOOKS = [
    # ═══════════════════════════════════════════════════════════
    # 一、网络设备运维
    # ═══════════════════════════════════════════════════════════
    {
        "id": "vlan_info_collect",
        "name": "交换机 VLAN 信息采集",
        "description": "通过 SSH 连接交换机，执行 show vlan 命令并分析配置",
        "category": "network",
        "parameters": '[{"name":"switch_ip","type":"string","required":true,"description":"交换机 IP 地址","validation":"^[0-9.]+$"},{"name":"username","type":"string","required":false,"default":"admin"},{"name":"password","type":"secret","required":true,"description":"SSH 密码"},{"name":"commands","type":"string[]","required":false,"default":["show vlan brief"]}]',
        "tools_required": "ssh_execute_command,think",
        "system_prompt": (
            "你是网络设备运维专家。\n\n"
            "## 任务\n通过 SSH 连接交换机 {switch_ip}，采集 VLAN 信息并分析。\n\n"
            "## 步骤\n"
            "1. 使用 ssh_execute_command 连接 {switch_ip}（用户: {username}，端口: 22）\n"
            "2. 依次执行命令: {commands}\n"
            "3. 使用 think 分析 VLAN 配置\n"
            "4. 输出结构化报告：VLAN ID、名称、端口分配、状态\n"
            "5. 标记异常配置（如 VLAN 1 未隔离、Trunk 口配置不当）\n\n"
            "## 输出格式\n### VLAN 配置概览\n| VLAN ID | 名称 | 端口 | 状态 |\n\n"
            "### 异常发现\n- [严重程度] 问题描述\n\n### 建议"
        ),
        "validation_rules": '{"timeout_seconds":120,"max_tool_calls":10}',
    },
    {
        "id": "network_device_backup",
        "name": "网络设备配置备份",
        "description": "批量 SSH 到网络设备，导出运行配置并保存到本地",
        "category": "network",
        "parameters": '[{"name":"device_ips","type":"string[]","required":true,"description":"设备 IP 列表"},{"name":"username","type":"string","required":false,"default":"admin"},{"name":"password","type":"secret","required":true,"description":"SSH 密码"},{"name":"backup_dir","type":"string","required":false,"default":"/tmp/serverhub-sandbox/network-backups"}]',
        "tools_required": "ssh_execute_command,write_file,think,send_notification",
        "system_prompt": (
            "你是网络设备运维专家，负责配置备份。\n\n"
            "## 任务\n对以下网络设备执行配置备份: {device_ips}\n\n"
            "## 步骤\n对每台设备:\n"
            "1. SSH 连接（用户: {username}）\n"
            "2. 执行 `show running-config` 或 `display current-configuration`（根据设备类型自动判断）\n"
            "3. 将输出保存到 {backup_dir}/{device_ip}_$(date +%Y%m%d).cfg\n"
            "4. 如果连接失败，记录错误并继续下一台\n\n"
            "## 汇总\n"
            "1. 输出备份结果表格\n"
            "2. 如有失败设备，发送告警通知\n\n"
            "## 输出格式\n### 备份结果\n| IP | 状态 | 文件 | 大小 | 备注 |\n\n"
            "### 失败设备\n- IP: 错误原因"
        ),
        "validation_rules": '{"timeout_seconds":300,"max_tool_calls":30}',
    },
    # ═══════════════════════════════════════════════════════════
    # 二、服务器健康检查
    # ═══════════════════════════════════════════════════════════
    {
        "id": "batch_server_health",
        "name": "批量服务器健康检查",
        "description": "SSH 到多台服务器执行健康检查，汇总报告",
        "category": "system",
        "parameters": '[{"name":"server_ips","type":"string[]","required":true,"description":"服务器 IP 列表"},{"name":"username","type":"string","required":false,"default":"root"},{"name":"check_items","type":"string[]","required":false,"default":["uptime","free -h","df -h","systemctl --failed"]}]',
        "tools_required": "ssh_execute_command,think,send_notification",
        "system_prompt": (
            "你是服务器运维专家。\n\n"
            "## 任务\n对以下服务器进行批量健康检查: {server_ips}\n\n"
            "## 步骤\n对每台服务器依次执行:\n"
            "1. SSH 连接（用户: {username}）\n"
            "2. 执行检查命令: {check_items}\n"
            "3. 分析输出，标记异常（内存>80%、磁盘>90%、failed 服务）\n\n"
            "## 汇总\n所有服务器检查完毕后:\n"
            "1. 输出汇总表格\n"
            "2. 对有问题的服务器标记告警级别\n"
            "3. 如有严重问题，调用 send_notification 发送告警\n\n"
            "## 输出格式\n### 服务器健康概览\n"
            "| IP | 状态 | CPU | 内存 | 磁盘 | 异常服务 |\n\n"
            "### 告警项\n- [级别] 服务器 IP: 问题描述"
        ),
        "validation_rules": '{"timeout_seconds":600,"max_tool_calls":50}',
    },
    {
        "id": "tms_fault_detection",
        "name": "TMS 日常故障检测",
        "description": "综合检测系统和容器状态，分析趋势，生成故障报告",
        "category": "system",
        "parameters": '[{"name":"severity_threshold","type":"string","required":false,"default":"warning","description":"告警阈值: info/warning/critical"}]',
        "tools_required": "get_system_overview,list_docker_containers,get_container_logs,check_compliance,analyze_resource_trend,send_notification,think",
        "system_prompt": (
            "你是故障检测专家，执行 TMS 日常故障检测。告警阈值: {severity_threshold}\n\n"
            "## 步骤\n"
            "1. 调用 get_system_overview 获取系统整体状态\n"
            "2. 调用 list_docker_containers 检查所有容器状态\n"
            "3. 对异常容器（非 running/非健康）调用 get_container_logs 分析日志\n"
            "4. 调用 check_compliance 检查安全合规状态\n"
            "5. 调用 analyze_resource_trend 分析最近 24h 资源趋势\n"
            "6. 综合分析所有数据\n"
            "7. 如发现超过 {severity_threshold} 级别的问题，调用 send_notification\n\n"
            "## 输出格式\n### 系统状态\n- CPU/内存/磁盘/网络 概要\n\n"
            "### 容器健康\n| 容器 | 状态 | 运行时间 | 异常 |\n\n"
            "### 故障发现\n- [CRITICAL/WARNING/INFO] 描述\n\n"
            "### 趋势分析\n24h 资源变化趋势\n\n### 建议"
        ),
        "validation_rules": '{"timeout_seconds":300,"max_tool_calls":30}',
    },
    # ═══════════════════════════════════════════════════════════
    # 三、Docker / 容器运维
    # ═══════════════════════════════════════════════════════════
    {
        "id": "docker_cleanup",
        "name": "Docker 资源深度清理",
        "description": "清理未使用的容器、镜像、网络和卷，释放磁盘空间",
        "category": "system",
        "parameters": '[{"name":"dry_run","type":"boolean","required":false,"default":true,"description":"预览模式（不实际删除）"},{"name":"keep_recent_days","type":"number","required":false,"default":7,"description":"保留最近 N 天的镜像"}]',
        "tools_required": "list_docker_containers,get_disk_info,docker_prune,think,send_notification",
        "system_prompt": (
            "你是 Docker 运维专家，负责清理未使用的资源。\n\n"
            "## 任务\n执行 Docker 资源清理。预览模式: {dry_run}，保留 {keep_recent_days} 天内的镜像。\n\n"
            "## 步骤\n"
            "1. 调用 get_disk_info 查看当前磁盘使用情况\n"
            "2. 调用 list_docker_containers 列出所有容器，识别已停止的\n"
            "3. 使用 think 分析哪些资源可以安全清理\n"
            "4. 如果 dry_run 为 false:\n"
            "   - 清理已停止容器: docker_prune containers\n"
            "   - 清理悬空镜像: docker_prune images\n"
            "   - 清理未使用卷: docker_prune volumes\n"
            "   - 清理未使用网络: docker_prune networks\n"
            "5. 重新检查磁盘使用，计算释放空间\n"
            "6. 发送清理报告通知\n\n"
            "## 输出格式\n### 清理前\n- 磁盘使用: X GB / Y GB\n\n"
            "### 清理内容\n| 类型 | 数量 | 释放空间 |\n\n"
            "### 清理后\n- 磁盘使用: X GB / Y GB（释放了 Z GB）"
        ),
        "validation_rules": '{"timeout_seconds":180,"max_tool_calls":15}',
    },
    {
        "id": "docker_service_restart",
        "name": "Docker 服务编排重启",
        "description": "按依赖顺序重启 Docker Compose 堆栈，确保服务可用",
        "category": "system",
        "parameters": '[{"name":"stack_name","type":"string","required":true,"description":"Compose 堆栈名称（如 dify/lobe）"},{"name":"health_check_timeout","type":"number","required":false,"default":60,"description":"健康检查超时（秒）"}]',
        "tools_required": "docker_compose_action,list_docker_containers,get_container_logs,think,send_notification",
        "system_prompt": (
            "你是 Docker 编排专家，负责安全重启服务堆栈。\n\n"
            "## 任务\n重启 Compose 堆栈: {stack_name}，健康检查超时: {health_check_timeout}s\n\n"
            "## 步骤\n"
            "1. 调用 list_docker_containers 检查当前堆栈状态\n"
            "2. 记录当前运行中的容器列表作为基线\n"
            "3. 执行 docker_compose_action restart 重启堆栈\n"
            "4. 等待后重新检查容器状态\n"
            "5. 对每个容器验证是否恢复 running 状态\n"
            "6. 如有容器未恢复，获取其日志分析原因\n"
            "7. 输出重启报告\n\n"
            "## 输出格式\n### 重启结果\n| 容器 | 重启前 | 重启后 | 耗时 |\n\n"
            "### 异常\n- 未恢复的容器及原因\n\n### 建议"
        ),
        "validation_rules": '{"timeout_seconds":180,"max_tool_calls":20}',
    },
    # ═══════════════════════════════════════════════════════════
    # 四、安全审计
    # ═══════════════════════════════════════════════════════════
    {
        "id": "security_full_audit",
        "name": "安全合规全面审计",
        "description": "CIS 基线检查 + SSH 安全 + 用户审计 + 端口扫描",
        "category": "security",
        "parameters": '[{"name":"auto_fix","type":"boolean","required":false,"default":false,"description":"自动修复可安全修复的项目"},{"name":"notify_on_critical","type":"boolean","required":false,"default":true}]',
        "tools_required": "check_compliance,get_system_overview,get_active_sessions_tool,get_user_login_history_tool,auto_fix_compliance,send_notification,think",
        "system_prompt": (
            "你是安全审计专家，执行全面安全审计。自动修复: {auto_fix}\n\n"
            "## 步骤\n"
            "1. 调用 check_compliance 执行 CIS 基线合规检查\n"
            "2. 调用 get_system_overview 检查系统安全状态\n"
            "3. 调用 get_active_sessions_tool 检查当前活跃会话\n"
            "4. 检查异常登录（非工作时间、异常 IP）\n"
            "5. 使用 think 综合分析安全风险\n"
            "6. 如果 auto_fix 为 true，对安全的项目调用 auto_fix_compliance\n"
            "7. 如有 CRITICAL 发现且 notify_on_critical 为 true，发送告警\n\n"
            "## 输出格式\n### 合规检查\n| 检查项 | 状态 | 严重性 | 说明 |\n\n"
            "### 活跃会话审计\n| 用户 | 来源 IP | 登录时间 | 空闲 | 风险 |\n\n"
            "### 安全风险摘要\n- [CRITICAL/WARNING/INFO] 描述\n\n"
            "### 修复操作\n| 项目 | 修复结果 |\n\n### 建议"
        ),
        "validation_rules": '{"timeout_seconds":300,"max_tool_calls":25}',
    },
    {
        "id": "ssh_bruteforce_check",
        "name": "SSH 暴力破解检测",
        "description": "分析 auth.log 检测 SSH 暴力破解尝试，识别恶意 IP",
        "category": "security",
        "parameters": '[{"name":"hours","type":"number","required":false,"default":24,"description":"检查最近 N 小时"},{"name":"threshold","type":"number","required":false,"default":10,"description":"失败次数阈值"}]',
        "tools_required": "get_service_logs,get_active_sessions_tool,think,send_notification",
        "system_prompt": (
            "你是安全分析师，检测 SSH 暴力破解。时间范围: {hours}h，阈值: {threshold} 次失败\n\n"
            "## 步骤\n"
            "1. 调用 get_service_logs 获取 sshd/auth.log 最近 {hours} 小时日志\n"
            "2. 分析失败登录记录，按 IP 统计失败次数\n"
            "3. 识别超过 {threshold} 次失败的 IP\n"
            "4. 检查这些 IP 是否在当前活跃会话中\n"
            "5. 使用 think 评估威胁级别\n"
            "6. 如发现高危 IP，发送告警\n\n"
            "## 输出格式\n### SSH 登录统计\n| IP | 失败次数 | 成功次数 | 首次 | 末次 | 用户名 |\n\n"
            "### 高危 IP\n- IP: 风险评估\n\n### fail2ban 状态\n当前封禁列表\n\n### 建议"
        ),
        "validation_rules": '{"timeout_seconds":120,"max_tool_calls":10}',
    },
    # ═══════════════════════════════════════════════════════════
    # 五、用户资源管理
    # ═══════════════════════════════════════════════════════════
    {
        "id": "student_resource_audit",
        "name": "学生用户资源审计",
        "description": "检查所有学生用户的资源使用，识别超配额和异常进程",
        "category": "system",
        "parameters": '[{"name":"action_level","type":"string","required":false,"default":"report","description":"处理级别: report(仅报告) / warn(通知) / enforce(强制清理)"}]',
        "tools_required": "get_user_resources,get_user_quotas,get_user_full_processes,check_quota_violations,kill_user_processes,send_notification,think",
        "system_prompt": (
            "你是资源管理专员，审计学生用户资源。处理级别: {action_level}\n\n"
            "## 步骤\n"
            "1. 调用 get_user_resources 获取所有用户资源使用\n"
            "2. 调用 get_user_quotas 获取配额规则\n"
            "3. 调用 check_quota_violations 检查配额违规\n"
            "4. 对超配额用户，调用 get_user_full_processes 查看详细进程\n"
            "5. 识别异常进程（挖矿、大量 Python 长时间运行、僵尸进程）\n"
            "6. 根据 action_level 执行操作:\n"
            "   - report: 仅输出报告\n"
            "   - warn: 输出报告 + 发送通知\n"
            "   - enforce: 输出报告 + 通知 + kill 超配额进程\n\n"
            "## 输出格式\n### 资源使用概览\n| 用户 | 内存(GB) | 配额 | 使用率 | 进程数 | CPU% | 状态 |\n\n"
            "### 超配额用户\n- 用户: 详情 + 处理结果\n\n"
            "### 异常进程\n| 用户 | PID | 命令 | CPU% | 内存 | 运行时间 | 可疑原因 |\n\n### 建议"
        ),
        "validation_rules": '{"timeout_seconds":180,"max_tool_calls":30}',
    },
    # ═══════════════════════════════════════════════════════════
    # 六、日志分析
    # ═══════════════════════════════════════════════════════════
    {
        "id": "error_log_analysis",
        "name": "错误日志智能分析",
        "description": "分析系统和服务日志中的错误，关联多源数据定位根因",
        "category": "system",
        "parameters": '[{"name":"services","type":"string[]","required":false,"default":["nginx","docker","sshd"],"description":"要分析的服务列表"},{"name":"hours","type":"number","required":false,"default":6,"description":"分析最近 N 小时"}]',
        "tools_required": "get_service_logs,get_container_logs,list_docker_containers,get_system_overview,think,send_notification",
        "system_prompt": (
            "你是日志分析专家，对服务错误进行根因分析。服务: {services}，时间: {hours}h\n\n"
            "## 步骤\n"
            "1. 获取系统概览了解整体状态\n"
            "2. 对每个服务调用 get_service_logs 获取日志\n"
            "3. 提取 ERROR/FATAL/CRITICAL 级别日志条目\n"
            "4. 如果涉及 Docker 服务，同时获取容器日志\n"
            "5. 使用 think 进行关联分析:\n"
            "   - 时间线重建: 按时间排序所有错误\n"
            "   - 因果链分析: 哪个错误导致了下游错误\n"
            "   - 资源关联: 错误是否伴随资源异常\n"
            "6. 如发现 CRITICAL 错误，发送告警\n\n"
            "## 输出格式\n### 错误时间线\n| 时间 | 服务 | 级别 | 消息摘要 |\n\n"
            "### 根因分析\n1. 根本原因: ...\n2. 影响范围: ...\n3. 因果链: A → B → C\n\n"
            "### 修复建议\n- 短期: ...\n- 长期: ..."
        ),
        "validation_rules": '{"timeout_seconds":180,"max_tool_calls":20}',
    },
    # ═══════════════════════════════════════════════════════════
    # 七、定时任务管理
    # ═══════════════════════════════════════════════════════════
    {
        "id": "cron_health_check",
        "name": "定时任务健康检查",
        "description": "检查所有 cron 任务的运行状态、失败记录和资源消耗",
        "category": "system",
        "parameters": '[{"name":"check_root","type":"boolean","required":false,"default":true,"description":"是否检查 root crontab"}]',
        "tools_required": "list_cron_jobs,get_service_logs,think",
        "system_prompt": (
            "你是运维专家，检查定时任务健康状况。检查 root: {check_root}\n\n"
            "## 步骤\n"
            "1. 调用 list_cron_jobs 获取用户 crontab\n"
            "2. 如果 check_root=true，也获取 root crontab\n"
            "3. 调用 get_service_logs 获取 cron 守护进程日志\n"
            "4. 分析:\n"
            "   - 是否有任务频繁失败\n"
            "   - 是否有任务从未执行（表达式错误？）\n"
            "   - 是否有重叠执行风险（间隔太短+执行太久）\n"
            "   - 是否有废弃任务（指向不存在的脚本）\n\n"
            "## 输出格式\n### 任务清单\n| 用户 | 表达式 | 命令 | 状态 | 最后运行 | 问题 |\n\n"
            "### 问题发现\n- [级别] 描述\n\n### 优化建议"
        ),
        "validation_rules": '{"timeout_seconds":120,"max_tool_calls":10}',
    },
    # ═══════════════════════════════════════════════════════════
    # 八、性能诊断
    # ═══════════════════════════════════════════════════════════
    {
        "id": "performance_diagnosis",
        "name": "性能瓶颈诊断",
        "description": "全面分析 CPU/内存/磁盘/网络性能，定位瓶颈",
        "category": "system",
        "parameters": '[{"name":"focus","type":"string","required":false,"default":"auto","description":"聚焦领域: auto/cpu/memory/disk/network/gpu"}]',
        "tools_required": "get_system_overview,analyze_resource_trend,get_user_full_processes,get_disk_info,think,send_notification",
        "system_prompt": (
            "你是性能工程师，诊断系统性能瓶颈。聚焦: {focus}\n\n"
            "## 步骤\n"
            "1. 调用 get_system_overview 获取实时系统指标\n"
            "2. 调用 analyze_resource_trend 分析 24h 趋势（识别高峰和异常）\n"
            "3. 调用 get_disk_info 检查磁盘 I/O 和空间\n"
            "4. 调用 get_user_full_processes 获取 Top 进程\n"
            "5. 使用 think 进行瓶颈定位:\n"
            "   - CPU: 是否存在 CPU 密集进程？负载均衡情况？\n"
            "   - 内存: 是否有内存泄漏？Swap 使用趋势？\n"
            "   - 磁盘: I/O 等待？空间不足？\n"
            "   - 网络: 带宽饱和？连接数异常？\n"
            "   - GPU: 利用率？显存？\n"
            "6. 如检测到严重瓶颈，发送告警\n\n"
            "## 输出格式\n### 性能概览\n| 指标 | 当前 | 24h 均值 | 24h 峰值 | 状态 |\n\n"
            "### 瓶颈分析\n1. 主要瓶颈: ...\n2. 次要瓶颈: ...\n\n"
            "### Top 资源消费者\n| PID | 命令 | CPU% | 内存 | 运行时间 |\n\n"
            "### 优化建议\n- 短期: ...\n- 长期: ..."
        ),
        "validation_rules": '{"timeout_seconds":180,"max_tool_calls":15}',
    },
    # ═══════════════════════════════════════════════════════════
    # 九、备份与恢复
    # ═══════════════════════════════════════════════════════════
    {
        "id": "system_backup_verify",
        "name": "系统备份完整性验证",
        "description": "检查关键配置文件、数据库和 Docker 数据的备份状态",
        "category": "system",
        "parameters": '[{"name":"backup_paths","type":"string[]","required":false,"default":["/etc/nginx/","/etc/crontab","/etc/login-monitor/"],"description":"需检查的配置目录"}]',
        "tools_required": "get_disk_info,list_cron_jobs,list_docker_containers,think,send_notification",
        "system_prompt": (
            "你是备份管理专家，验证系统备份完整性。\n\n"
            "## 任务\n检查以下路径的备份状态: {backup_paths}\n\n"
            "## 步骤\n"
            "1. 检查关键配置文件的最后修改时间\n"
            "2. 检查 crontab 中是否有备份任务\n"
            "3. 检查 Docker 数据卷的备份情况\n"
            "4. 验证备份文件的完整性（大小是否合理）\n"
            "5. 综合评估备份覆盖度\n\n"
            "## 输出格式\n### 备份状态\n| 项目 | 最后备份 | 大小 | 频率 | 状态 |\n\n"
            "### 未备份项\n- 缺失的关键备份\n\n### 建议"
        ),
        "validation_rules": '{"timeout_seconds":120,"max_tool_calls":10}',
    },
    # ═══════════════════════════════════════════════════════════
    # 十、Nginx 运维
    # ═══════════════════════════════════════════════════════════
    {
        "id": "nginx_config_check",
        "name": "Nginx 配置检查与优化",
        "description": "检查 Nginx 配置语法、SSL 证书、性能参数和安全头",
        "category": "system",
        "parameters": '[{"name":"check_ssl","type":"boolean","required":false,"default":true,"description":"检查 SSL 证书有效期"},{"name":"check_performance","type":"boolean","required":false,"default":true}]',
        "tools_required": "get_service_logs,check_compliance,think",
        "system_prompt": (
            "你是 Nginx 运维专家。SSL 检查: {check_ssl}，性能检查: {check_performance}\n\n"
            "## 步骤\n"
            "1. 检查 Nginx 配置语法\n"
            "2. 检查虚拟主机配置\n"
            "3. 如果 check_ssl=true:\n"
            "   - 检查所有 SSL 证书有效期\n"
            "   - 标记 30 天内到期的证书\n"
            "4. 如果 check_performance=true:\n"
            "   - worker_processes 是否匹配 CPU 核心数\n"
            "   - keepalive_timeout 是否合理\n"
            "   - gzip 是否启用\n"
            "5. 检查安全头: X-Frame-Options, CSP, HSTS\n"
            "6. 分析最近的错误日志\n\n"
            "## 输出格式\n### 配置检查\n| 检查项 | 状态 | 当前值 | 建议值 |\n\n"
            "### SSL 证书\n| 域名 | 到期日 | 剩余天数 | 状态 |\n\n"
            "### 安全头\n| 头部 | 状态 | 建议 |\n\n### 优化建议"
        ),
        "validation_rules": '{"timeout_seconds":120,"max_tool_calls":10}',
    },
]


async def seed_builtin_playbooks():
    """导入内置剧本（仅在不存在时）"""
    from database import get_db

    db = await get_db()
    for pb in DEFAULT_PLAYBOOKS:
        existing = await (await db.execute("SELECT id FROM playbooks WHERE id = ?", (pb["id"],))).fetchone()
        if not existing:
            await db.execute(
                "INSERT INTO playbooks "
                "(id, name, description, category, system_prompt, parameters, "
                "tools_required, validation_rules, is_builtin, created_by) "
                "VALUES (?,?,?,?,?,?,?,?,1,'system')",
                (
                    pb["id"],
                    pb["name"],
                    pb["description"],
                    pb["category"],
                    pb["system_prompt"],
                    pb["parameters"],
                    pb["tools_required"],
                    pb["validation_rules"],
                ),
            )
    await db.commit()

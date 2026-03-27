"""内置剧本模板 — 启动时自动导入"""

DEFAULT_PLAYBOOKS = [
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
]


async def seed_builtin_playbooks():
    """导入内置剧本（仅在不存在时）"""
    from database import get_db

    db = await get_db()
    for pb in DEFAULT_PLAYBOOKS:
        existing = await (
            await db.execute(
                "SELECT id FROM playbooks WHERE id = ?", (pb["id"],)
            )
        ).fetchone()
        if not existing:
            await db.execute(
                "INSERT INTO playbooks "
                "(id, name, description, category, system_prompt, parameters, "
                "tools_required, validation_rules, is_builtin, created_by) "
                "VALUES (?,?,?,?,?,?,?,?,1,'system')",
                (
                    pb["id"], pb["name"], pb["description"], pb["category"],
                    pb["system_prompt"], pb["parameters"],
                    pb["tools_required"], pb["validation_rules"],
                ),
            )
    await db.commit()

"""内置团队模板 — 5 个预设团队 + seed 函数

模板在首次启动时自动写入数据库，用户可在 Web UI 上基于模板创建自定义团队。
"""

import logging

logger = logging.getLogger(__name__)


# ─── 模板定义 ───


BUILTIN_TEMPLATES: list[dict] = [
    # ── 模板 1: 安全审计团队 (Supervisor) ──
    {
        "id": "tpl-security-audit",
        "name": "安全审计团队",
        "description": "组长分配安全审计任务给专业成员，覆盖系统合规、用户权限、服务暴露面等维度",
        "topology": "supervisor",
        "config": {"output_mode": "full_history"},
        "safety_mode": "supervised",
        "max_steps": 60,
        "timeout_seconds": 300,
        "members": [
            {
                "name": "安全组长",
                "agent_type": "leader",
                "description": "安全审计团队组长，负责任务分配和最终汇总",
                "system_prompt": (
                    "你是安全审计团队的组长。你的职责是:\n"
                    "1. 分析用户的安全审计需求，拆解为具体子任务\n"
                    "2. 将子任务分配给合适的团队成员（合规审查员、权限审计员、网络安全员）\n"
                    "3. 汇总各成员的审计结果，生成结构化的安全审计报告\n"
                    "4. 对发现的安全问题按严重程度分级（严重/高/中/低）\n\n"
                    "输出格式要求:\n"
                    "- 使用 Markdown 格式\n"
                    "- 包含「审计概要」「发现问题」「风险等级」「修复建议」四个部分\n"
                    "- 每个问题标注发现者和风险等级"
                ),
                "tools": [],
                "position": 0,
            },
            {
                "name": "合规审查员",
                "agent_type": "worker",
                "description": "检查系统合规性配置",
                "system_prompt": (
                    "你是安全审计团队的合规审查员。你的职责是:\n"
                    "1. 使用 check_compliance 工具检查系统安全合规性\n"
                    "2. 检查 SSH 配置、防火墙规则、密码策略等基线\n"
                    "3. 检查关键服务的安全配置（nginx, mysql 等）\n"
                    "4. 输出不合规项清单，每项包含当前状态和建议修复方案\n\n"
                    "只输出你的审查结果，不要做超出职责范围的事情。"
                ),
                "tools": [
                    "check_compliance",
                    "get_system_overview",
                    "list_systemd_services",
                    "get_service_logs",
                ],
                "position": 1,
            },
            {
                "name": "权限审计员",
                "agent_type": "worker",
                "description": "审计用户权限和会话安全",
                "system_prompt": (
                    "你是安全审计团队的权限审计员。你的职责是:\n"
                    "1. 检查系统上所有用户的权限配置和资源使用\n"
                    "2. 审计活跃登录会话，发现异常登录行为\n"
                    "3. 检查用户配额设置是否合理\n"
                    "4. 检查 sudo 权限和用户组配置\n\n"
                    "重点关注: 异常登录时间、异常来源 IP、超配额使用、僵尸会话。\n"
                    "只输出你的审查结果，不要做超出职责范围的事情。"
                ),
                "tools": [
                    "get_user_resources",
                    "get_user_quotas",
                    "get_user_login_history_tool",
                    "get_active_sessions_tool",
                    "get_user_full_processes",
                    "check_quota_violations",
                ],
                "position": 2,
            },
            {
                "name": "网络安全员",
                "agent_type": "worker",
                "description": "检查网络服务暴露面和容器安全",
                "system_prompt": (
                    "你是安全审计团队的网络安全员。你的职责是:\n"
                    "1. 检查 Docker 容器的运行状态和网络暴露\n"
                    "2. 审查容器端口映射和网络配置\n"
                    "3. 检查是否有容器使用特权模式或过度开放端口\n"
                    "4. 检查服务依赖关系中的安全风险\n\n"
                    "重点关注: 不必要的端口暴露、特权容器、过时镜像。\n"
                    "只输出你的审查结果，不要做超出职责范围的事情。"
                ),
                "tools": [
                    "list_docker_containers",
                    "list_docker_networks",
                    "get_container_logs",
                    "list_systemd_services",
                    "get_service_dependencies_tool",
                ],
                "position": 3,
            },
        ],
    },
    # ── 模板 2: 故障诊断团队 (Swarm) ──
    {
        "id": "tpl-fault-diagnosis",
        "name": "故障诊断团队",
        "description": "分诊员接收问题后自主 handoff 给系统/容器/网络专家协作排查",
        "topology": "swarm",
        "config": {},
        "safety_mode": "supervised",
        "max_steps": 80,
        "timeout_seconds": 600,
        "members": [
            {
                "name": "分诊员",
                "agent_type": "worker",
                "description": "接收故障描述，初步判断故障域并 handoff",
                "system_prompt": (
                    "你是故障诊断团队的分诊员，是问题的第一接触人。你的职责是:\n"
                    "1. 获取系统概览信息，快速了解当前系统状态\n"
                    "2. 根据故障现象判断属于哪个领域（系统/容器/服务）\n"
                    "3. 将问题 handoff 给对应的专家进一步排查\n\n"
                    "判断规则:\n"
                    "- CPU/内存/磁盘问题 → 系统专家\n"
                    "- Docker/容器异常 → 容器专家\n"
                    "- 服务不可用/网络问题 → 服务专家\n"
                    "- 不确定时，先发给系统专家做全面检查\n\n"
                    "分诊完成后立即 handoff，不要自己做深入排查。"
                ),
                "tools": [
                    "get_system_overview",
                    "get_disk_info",
                ],
                "handoff_targets": ["系统专家", "容器专家", "服务专家"],
                "position": 0,
            },
            {
                "name": "系统专家",
                "agent_type": "worker",
                "description": "排查系统级问题（CPU/内存/磁盘/进程）",
                "system_prompt": (
                    "你是故障诊断团队的系统专家。你的职责是:\n"
                    "1. 深入排查系统资源问题（CPU、内存、磁盘、进程）\n"
                    "2. 分析资源趋势，找到异常时间点和异常进程\n"
                    "3. 检查用户资源配额违规情况\n"
                    "4. 如果发现问题与容器或服务相关，handoff 给对应专家\n\n"
                    "输出要求: 列出排查步骤、发现的问题、根因分析和建议操作。"
                ),
                "tools": [
                    "get_system_overview",
                    "get_disk_info",
                    "analyze_resource_trend",
                    "get_user_resources",
                    "get_user_full_processes",
                    "check_quota_violations",
                ],
                "handoff_targets": ["容器专家", "服务专家", "分诊员"],
                "position": 1,
            },
            {
                "name": "容器专家",
                "agent_type": "worker",
                "description": "排查 Docker 容器和编排问题",
                "system_prompt": (
                    "你是故障诊断团队的容器专家。你的职责是:\n"
                    "1. 检查 Docker 容器运行状态、重启次数、资源占用\n"
                    "2. 分析容器日志，查找错误和警告信息\n"
                    "3. 检查容器网络连通性和端口映射\n"
                    "4. 对 docker compose 管理的堆栈进行整体健康检查\n\n"
                    "如果发现问题的根因在系统层面或服务层面，handoff 给对应专家。\n"
                    "输出要求: 列出检查过的容器、发现的异常、日志关键片段和修复建议。"
                ),
                "tools": [
                    "list_docker_containers",
                    "get_container_logs",
                    "list_docker_networks",
                    "docker_container_exec",
                ],
                "handoff_targets": ["系统专家", "服务专家", "分诊员"],
                "position": 2,
            },
            {
                "name": "服务专家",
                "agent_type": "worker",
                "description": "排查 systemd 服务和网络问题",
                "system_prompt": (
                    "你是故障诊断团队的服务专家。你的职责是:\n"
                    "1. 检查 systemd 服务状态和日志\n"
                    "2. 分析服务依赖关系，找到故障传播路径\n"
                    "3. 检查定时任务执行状态\n"
                    "4. 如果需要系统或容器层面的配合，handoff 给对应专家\n\n"
                    "输出要求: 列出检查过的服务、故障链路分析、日志关键片段和建议操作。"
                ),
                "tools": [
                    "list_systemd_services",
                    "get_service_logs",
                    "get_service_dependencies_tool",
                    "list_cron_jobs",
                ],
                "handoff_targets": ["系统专家", "容器专家", "分诊员"],
                "position": 3,
            },
        ],
    },
    # ── 模板 3: 全面巡检流水线 (Pipeline) ──
    {
        "id": "tpl-full-patrol",
        "name": "全面巡检流水线",
        "description": "三阶段流水线: 数据采集 → 深度分析 → 报告生成",
        "topology": "pipeline",
        "config": {},
        "safety_mode": "supervised",
        "max_steps": 50,
        "timeout_seconds": 300,
        "members": [
            {
                "name": "数据采集员",
                "agent_type": "worker",
                "description": "第一阶段: 全面采集系统状态数据",
                "system_prompt": (
                    "你是全面巡检流水线的第一阶段 — 数据采集员。你的职责是:\n"
                    "1. 获取系统概览（CPU/内存/磁盘/负载）\n"
                    "2. 获取磁盘详细信息\n"
                    "3. 列出所有运行中的 Docker 容器状态\n"
                    "4. 列出关键 systemd 服务状态\n"
                    "5. 检查用户资源使用情况\n"
                    "6. 检查定时任务状态\n\n"
                    "输出要求: 将所有采集到的原始数据以结构化格式输出，不做分析判断。\n"
                    "使用 Markdown 表格和代码块组织数据，确保下游分析员能直接使用。"
                ),
                "tools": [
                    "get_system_overview",
                    "get_disk_info",
                    "list_docker_containers",
                    "list_systemd_services",
                    "get_user_resources",
                    "list_cron_jobs",
                ],
                "position": 0,
            },
            {
                "name": "分析员",
                "agent_type": "worker",
                "description": "第二阶段: 基于采集数据进行深度分析",
                "system_prompt": (
                    "你是全面巡检流水线的第二阶段 — 分析员。你的职责是:\n"
                    "基于上游「数据采集员」提供的原始数据，进行深度分析:\n\n"
                    "1. **资源健康分析**: CPU/内存/磁盘使用率是否正常，趋势是否恶化\n"
                    "2. **容器健康分析**: 是否有容器异常重启、OOM、状态异常\n"
                    "3. **服务健康分析**: 关键服务是否正常运行，有无启动失败\n"
                    "4. **用户行为分析**: 是否有用户超配额使用资源\n"
                    "5. **安全合规分析**: 调用合规检查工具评估安全状态\n\n"
                    "输出要求:\n"
                    "- 每个分析维度给出「正常/警告/异常」状态\n"
                    "- 异常项要列出具体原因和影响\n"
                    "- 如需额外调查，使用可用工具获取更多信息"
                ),
                "tools": [
                    "analyze_resource_trend",
                    "check_compliance",
                    "check_quota_violations",
                    "get_container_logs",
                    "get_service_logs",
                ],
                "position": 1,
            },
            {
                "name": "报告员",
                "agent_type": "worker",
                "description": "第三阶段: 生成最终巡检报告",
                "system_prompt": (
                    "你是全面巡检流水线的第三阶段 — 报告员。你的职责是:\n"
                    "基于上游「数据采集员」和「分析员」的输出，生成最终巡检报告。\n\n"
                    "报告格式:\n"
                    "# 系统巡检报告\n\n"
                    "## 总体评分: X/100\n\n"
                    "## 健康状态总览\n"
                    "| 维度 | 状态 | 说明 |\n\n"
                    "## 发现的问题（按严重程度排序）\n"
                    "### 严重\n"
                    "### 警告\n"
                    "### 建议\n\n"
                    "## 建议操作\n"
                    "按优先级列出需要执行的操作。\n\n"
                    "要求: 报告语言简洁专业，面向运维管理员。"
                ),
                "tools": [],
                "position": 2,
            },
        ],
    },
    # ── 模板 4: 容器运维团队 (Supervisor) ──
    {
        "id": "tpl-docker-ops",
        "name": "容器运维团队",
        "description": "容器主管管理镜像、容器和日志分析成员，处理 Docker 相关运维任务",
        "topology": "supervisor",
        "config": {"output_mode": "full_history"},
        "safety_mode": "supervised",
        "max_steps": 50,
        "timeout_seconds": 300,
        "members": [
            {
                "name": "容器主管",
                "agent_type": "leader",
                "description": "容器运维团队组长，负责任务分配和决策",
                "system_prompt": (
                    "你是容器运维团队的主管。你的职责是:\n"
                    "1. 分析用户的容器运维需求\n"
                    "2. 将任务分配给合适的成员:\n"
                    "   - 容器状态和操作 → 容器管理员\n"
                    "   - 日志分析和故障排查 → 日志分析员\n"
                    "3. 汇总结果并给出最终决策建议\n\n"
                    "注意: 涉及容器启停、清理等危险操作时，要确认操作的必要性和影响范围。"
                ),
                "tools": [
                    "list_docker_containers",
                ],
                "position": 0,
            },
            {
                "name": "容器管理员",
                "agent_type": "worker",
                "description": "执行容器和编排操作",
                "system_prompt": (
                    "你是容器运维团队的容器管理员。你的职责是:\n"
                    "1. 管理 Docker 容器的生命周期（启动/停止/重启）\n"
                    "2. 管理 Docker Compose 堆栈\n"
                    "3. 检查容器网络配置\n"
                    "4. 在容器内执行诊断命令\n"
                    "5. 清理无用的镜像和容器资源\n\n"
                    "操作前务必确认目标容器，操作后验证结果。\n"
                    "输出操作步骤和结果。"
                ),
                "tools": [
                    "list_docker_containers",
                    "docker_container_action",
                    "docker_compose_action",
                    "list_docker_networks",
                    "docker_container_exec",
                    "docker_prune",
                ],
                "position": 1,
            },
            {
                "name": "日志分析员",
                "agent_type": "worker",
                "description": "分析容器日志和服务日志",
                "system_prompt": (
                    "你是容器运维团队的日志分析员。你的职责是:\n"
                    "1. 获取并分析容器日志，查找错误和警告\n"
                    "2. 分析相关 systemd 服务的日志\n"
                    "3. 关联多个日志源，找出问题的时间线\n"
                    "4. 识别常见错误模式（OOM、连接拒绝、认证失败等）\n\n"
                    "输出要求: 列出关键日志片段、错误模式、时间线和根因推测。"
                ),
                "tools": [
                    "get_container_logs",
                    "get_service_logs",
                    "list_docker_containers",
                ],
                "position": 2,
            },
        ],
    },
    # ── 模板 5: 用户资源管理流水线 (Pipeline) ──
    {
        "id": "tpl-user-resource",
        "name": "用户资源管理流水线",
        "description": "三阶段流水线: 巡查用户资源 → 执行管控措施 → 通知相关方",
        "topology": "pipeline",
        "config": {},
        "safety_mode": "supervised",
        "max_steps": 40,
        "timeout_seconds": 240,
        "members": [
            {
                "name": "资源巡查员",
                "agent_type": "worker",
                "description": "第一阶段: 全面检查用户资源使用和配额违规",
                "system_prompt": (
                    "你是用户资源管理流水线的第一阶段 — 资源巡查员。你的职责是:\n"
                    "1. 获取所有用户的资源使用情况（CPU、内存、进程数）\n"
                    "2. 获取当前配额设置\n"
                    "3. 检查是否有配额违规\n"
                    "4. 获取活跃登录会话信息\n"
                    "5. 检查用户近期登录历史\n\n"
                    "输出要求:\n"
                    "- 列出每个用户的资源使用 vs 配额限制\n"
                    "- 标注违规用户和违规类型\n"
                    "- 标注异常会话（如深夜登录、长时间空闲）\n"
                    "- 数据以表格形式呈现"
                ),
                "tools": [
                    "get_user_resources",
                    "get_user_quotas",
                    "check_quota_violations",
                    "get_active_sessions_tool",
                    "get_user_login_history_tool",
                    "get_user_full_processes",
                ],
                "position": 0,
            },
            {
                "name": "配额执行员",
                "agent_type": "worker",
                "description": "第二阶段: 根据巡查结果执行资源管控",
                "system_prompt": (
                    "你是用户资源管理流水线的第二阶段 — 配额执行员。你的职责是:\n"
                    "基于上游「资源巡查员」的检查结果，执行必要的资源管控:\n\n"
                    "1. 对超配额用户，调整配额或标记处理建议\n"
                    "2. 对资源消耗异常的进程，标记需要处理的进程列表\n"
                    "3. 对空闲超时会话，标记建议清理的会话\n\n"
                    "注意: 不要自行执行 kill 操作，只输出建议操作列表。\n"
                    "输出格式: 按用户列出需要执行的操作和理由。"
                ),
                "tools": [
                    "get_user_resources",
                    "get_user_quotas",
                    "update_user_quotas",
                ],
                "position": 1,
            },
            {
                "name": "通知员",
                "agent_type": "worker",
                "description": "第三阶段: 生成通知和报告",
                "system_prompt": (
                    "你是用户资源管理流水线的第三阶段 — 通知员。你的职责是:\n"
                    "基于上游「资源巡查员」和「配额执行员」的结果:\n\n"
                    "1. 生成用户资源使用报告摘要\n"
                    "2. 对需要通知的情况，通过通知工具发送告警\n"
                    "3. 生成最终的管理报告\n\n"
                    "报告格式:\n"
                    "# 用户资源管理报告\n"
                    "## 总览: X 个用户在线，Y 个违规\n"
                    "## 违规详情\n"
                    "## 已执行/建议操作\n"
                    "## 通知记录"
                ),
                "tools": [
                    "send_notification",
                ],
                "position": 2,
            },
        ],
    },
]


# ─── Seed 函数 ───


async def seed_builtin_teams():
    """在启动时检查并插入内置团队模板

    仅在团队不存在时插入，不会覆盖用户的修改。
    """
    from modules.agents.teams.store import TeamStore

    store = TeamStore()
    inserted_count = 0

    for tmpl in BUILTIN_TEMPLATES:
        try:
            existing = await store.get_team(tmpl["id"])
            if existing:
                logger.debug("内置团队 '%s' 已存在，跳过", tmpl["name"])
                continue

            # 创建团队
            team = await store.create_team(
                {
                    "id": tmpl["id"],
                    "name": tmpl["name"],
                    "description": tmpl.get("description", ""),
                    "topology": tmpl["topology"],
                    "config": tmpl.get("config", {}),
                    "safety_mode": tmpl.get("safety_mode", "supervised"),
                    "max_steps": tmpl.get("max_steps", 50),
                    "timeout_seconds": tmpl.get("timeout_seconds", 300),
                    "is_builtin": 1,
                    "created_by": "system",
                }
            )

            # 添加成员
            for member in tmpl.get("members", []):
                await store.add_member(team["id"], member)

            inserted_count += 1
            logger.info("已创建内置团队: %s (%s)", tmpl["name"], tmpl["topology"])

        except Exception as e:
            logger.error("创建内置团队 '%s' 失败: %s", tmpl["name"], e)

    if inserted_count:
        logger.info("共创建 %d 个内置团队", inserted_count)
    else:
        logger.debug("所有内置团队已存在，无需创建")


def get_template_list() -> list[dict]:
    """返回所有模板的摘要信息（不含完整 system_prompt）"""
    result = []
    for tmpl in BUILTIN_TEMPLATES:
        member_summary = []
        for m in tmpl.get("members", []):
            member_summary.append(
                {
                    "name": m["name"],
                    "agent_type": m.get("agent_type", "worker"),
                    "description": m.get("description", ""),
                    "tools_count": len(m.get("tools", [])),
                }
            )

        result.append(
            {
                "id": tmpl["id"],
                "name": tmpl["name"],
                "description": tmpl.get("description", ""),
                "topology": tmpl["topology"],
                "member_count": len(tmpl.get("members", [])),
                "members": member_summary,
                "safety_mode": tmpl.get("safety_mode", "supervised"),
                "max_steps": tmpl.get("max_steps", 50),
                "timeout_seconds": tmpl.get("timeout_seconds", 300),
            }
        )
    return result


def get_template_by_id(template_id: str) -> dict | None:
    """根据 ID 获取完整模板"""
    for tmpl in BUILTIN_TEMPLATES:
        if tmpl["id"] == template_id:
            return tmpl
    return None

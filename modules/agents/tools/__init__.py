"""运维工具集 — 封装现有 services 为 LangChain @tool"""

# ─── 系统 ───
from modules.agents.tools.system import (
    get_system_overview,
    get_disk_info,
    analyze_resource_trend,
)

# ─── Docker ───
from modules.agents.tools.docker import (
    list_docker_containers,
    get_container_logs,
    docker_container_action,
    docker_compose_action,
    list_docker_networks,
    docker_container_exec,
    docker_prune,
)

# ─── Systemd 服务 ───
from modules.agents.tools.services import (
    list_systemd_services,
    get_service_logs,
    service_control,
    service_enable_disable_tool,
    get_service_dependencies_tool,
)

# ─── 用户 ───
from modules.agents.tools.users import (
    get_user_resources,
    get_user_quotas,
    update_user_quotas,
    kill_user_processes,
    get_user_login_history_tool,
    get_active_sessions_tool,
    manage_linux_user,
    kill_single_process_tool,
    get_user_full_processes,
    check_quota_violations,
)

# ─── 定时任务 ───
from modules.agents.tools.cron import (
    list_cron_jobs,
    validate_cron_expr,
    create_cron_job,
    modify_cron_schedule,
    toggle_cron_job_tool,
    delete_cron_job_tool,
)

# ─── 安全合规 ───
from modules.agents.tools.security import (
    check_compliance,
    auto_fix_compliance,
)

# ─── 通知 ───
from modules.agents.tools.notifications import send_notification

# ─── 资产与故障案例 ───
from modules.agents.tools.assets import (
    get_asset_inventory,
    get_asset_topology,
    save_fault_case,
    search_fault_cases,
)

# ─── 运维脚本 ───
from modules.agents.tools.scripts import execute_ops_script

# ─── RAG 知识库 ───
from modules.agents.tools.knowledge import (
    retrieve_knowledge,
    reindex_knowledge_base,
)

# ─── 页面上下文 ───
from modules.agents.tools.page_context_tool import get_page_data

# ─── 运维剧本 ───
from modules.agents.tools.playbook import (
    ssh_execute_command,
    playbook_create,
    playbook_execute,
    playbook_list,
    playbook_search,
)

# ─── 服务器舰队管理 ───
from modules.agents.tools.servers import (
    server_list,
    server_test_connectivity,
)


# ─── 工具注册表 ───


def get_server_tools(user_role: str = "admin") -> list:
    """返回服务器管理工具列表

    Args:
        user_role: "admin" 返回全部工具，"user" 只返回只读安全工具
    """
    all_tools = [
        get_system_overview,
        get_disk_info,
        get_user_resources,
        get_user_quotas,
        list_docker_containers,
        get_container_logs,
        list_systemd_services,
        get_service_logs,
        send_notification,
        docker_container_action,
        docker_compose_action,
        service_control,
        update_user_quotas,
        execute_ops_script,
        kill_user_processes,
        check_compliance,
        analyze_resource_trend,
        search_fault_cases,
        save_fault_case,
        get_asset_inventory,
        get_asset_topology,
        auto_fix_compliance,
        # 服务增强
        service_enable_disable_tool,
        get_service_dependencies_tool,
        # Docker 增强
        list_docker_networks,
        docker_container_exec,
        docker_prune,
        # 用户审计与管理
        get_user_login_history_tool,
        get_active_sessions_tool,
        manage_linux_user,
        kill_single_process_tool,
        get_user_full_processes,
        check_quota_violations,
        # 定时任务
        list_cron_jobs,
        validate_cron_expr,
        create_cron_job,
        modify_cron_schedule,
        toggle_cron_job_tool,
        delete_cron_job_tool,
        # RAG 知识库
        retrieve_knowledge,
        reindex_knowledge_base,
        # 页面上下文
        get_page_data,
        # 运维剧本
        ssh_execute_command,
        playbook_create,
        playbook_execute,
        playbook_list,
        playbook_search,
        # 服务器舰队管理
        server_list,
        server_test_connectivity,
    ]

    if user_role == "admin":
        return all_tools

    # 普通用户：只返回 SAFE 级别工具
    from modules.agents.safety import TOOL_RISK_MAP, RiskLevel
    excluded = {"send_notification", "save_fault_case"}
    return [
        t for t in all_tools
        if TOOL_RISK_MAP.get(t.name, RiskLevel.DANGER) == RiskLevel.SAFE
        and t.name not in excluded
    ]


# 向后兼容
get_all_tools = get_server_tools

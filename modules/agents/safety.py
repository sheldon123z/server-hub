"""安全层：interrupt_on 配置 + Shell 黑名单 + 风险标签

Deep Agents 使用 interrupt_on 参数控制人工审批，替代旧的自定义 safety_check 节点。
TOOL_RISK_MAP 仅用于前端 UI 展示风险等级标签。
"""

import re
from enum import Enum


class RiskLevel(str, Enum):
    SAFE = "safe"
    MODERATE = "moderate"
    DANGER = "danger"


# 风险标签（仅 UI 展示用）
TOOL_RISK_MAP = {
    # 自定义工具
    "get_system_overview": RiskLevel.SAFE,
    "get_disk_info": RiskLevel.SAFE,
    "get_user_resources": RiskLevel.SAFE,
    "get_user_quotas": RiskLevel.SAFE,
    "list_docker_containers": RiskLevel.SAFE,
    "get_container_logs": RiskLevel.SAFE,
    "list_systemd_services": RiskLevel.SAFE,
    "get_service_logs": RiskLevel.SAFE,
    "send_notification": RiskLevel.SAFE,
    "check_compliance": RiskLevel.SAFE,
    "analyze_resource_trend": RiskLevel.SAFE,
    "search_fault_cases": RiskLevel.SAFE,
    "save_fault_case": RiskLevel.SAFE,
    "get_asset_inventory": RiskLevel.SAFE,
    "get_asset_topology": RiskLevel.SAFE,
    "auto_fix_compliance": RiskLevel.DANGER,
    "update_user_quotas": RiskLevel.MODERATE,
    "docker_container_action": RiskLevel.MODERATE,
    "docker_compose_action": RiskLevel.MODERATE,
    "service_control": RiskLevel.MODERATE,
    "execute_ops_script": RiskLevel.DANGER,
    "kill_user_processes": RiskLevel.DANGER,
    # Deep Agents 内置工具
    "execute": RiskLevel.DANGER,
    "write_file": RiskLevel.MODERATE,
    "edit_file": RiskLevel.MODERATE,
    "read_file": RiskLevel.SAFE,
    "ls": RiskLevel.SAFE,
    "glob": RiskLevel.SAFE,
    "grep": RiskLevel.SAFE,
    "write_todos": RiskLevel.SAFE,
    "task": RiskLevel.SAFE,
    # 服务增强工具
    "service_enable_disable_tool": RiskLevel.MODERATE,
    "get_service_dependencies_tool": RiskLevel.SAFE,
    # Docker 增强工具
    "list_docker_networks": RiskLevel.SAFE,
    "docker_container_exec": RiskLevel.MODERATE,
    "docker_prune": RiskLevel.DANGER,
    # 用户审计与管理工具
    "get_user_login_history_tool": RiskLevel.SAFE,
    "get_active_sessions_tool": RiskLevel.SAFE,
    "manage_linux_user": RiskLevel.DANGER,
    "kill_single_process_tool": RiskLevel.MODERATE,
    # 定时任务工具
    "list_cron_jobs": RiskLevel.SAFE,
    "validate_cron_expr": RiskLevel.SAFE,
    "create_cron_job": RiskLevel.MODERATE,
    "modify_cron_schedule": RiskLevel.MODERATE,
    "toggle_cron_job_tool": RiskLevel.MODERATE,
    "delete_cron_job_tool": RiskLevel.DANGER,
    # SubAgent 工具
    "web_search": RiskLevel.SAFE,
    "think": RiskLevel.SAFE,
    # RAG 工具
    "retrieve_knowledge": RiskLevel.SAFE,
    "reindex_knowledge_base": RiskLevel.SAFE,
    # 后台异步任务工具
    "start_background_analysis": RiskLevel.MODERATE,
    "check_background_task": RiskLevel.SAFE,
    "list_background_tasks": RiskLevel.SAFE,
    "cancel_background_task": RiskLevel.MODERATE,
}


def build_interrupt_config(safety_mode: str, user_role: str = "admin") -> dict:
    """根据安全模式和用户角色生成 Deep Agents 的 interrupt_on 配置

    Args:
        safety_mode: "supervised"(危险操作需审批) 或 "autonomous"(全自动)
        user_role: "admin" 或 "user"
    """
    # 普通用户：拦截所有非 SAFE 工具
    if user_role != "admin":
        return {
            name: True
            for name, risk in TOOL_RISK_MAP.items()
            if risk != RiskLevel.SAFE
        }

    if safety_mode == "autonomous":
        return {}

    return {
        # 自定义危险工具 — 始终审批
        "kill_user_processes": True,
        "auto_fix_compliance": True,
        "execute_ops_script": True,
        "delete_cron_job_tool": True,
        "manage_linux_user": True,
        # 单进程终止 — 审批
        "kill_single_process_tool": {"allowed_decisions": ["approve", "reject"]},
        "docker_prune": True,
        "service_enable_disable_tool": {"allowed_decisions": ["approve", "reject"]},
        # Docker exec — 审批
        "docker_container_exec": {"allowed_decisions": ["approve", "reject"]},
        # 定时任务创建 — 审批
        "create_cron_job": {"allowed_decisions": ["approve", "reject"]},
        # Docker/服务管理 — stop/down 操作需审批
        "docker_container_action": {"allowed_decisions": ["approve", "reject"]},
        "docker_compose_action": {"allowed_decisions": ["approve", "reject"]},
        "service_control": {"allowed_decisions": ["approve", "reject"]},
        # Deep Agents 内置 Shell — 危险命令需审批
        "execute": {
            "always": False,
            "pattern": r"rm|sudo|kill|shutdown|reboot|mkfs|dd|chmod|chown|systemctl.*(stop|disable)|iptables",
        },
        # 文件写入 — 系统敏感路径需审批
        "write_file": {
            "always": False,
            "pattern": r"/etc/|\.api_keys|\.telegram_config|config\.yaml|\.env",
        },
        "edit_file": {
            "always": False,
            "pattern": r"/etc/|\.api_keys|\.telegram_config|config\.yaml|\.env",
        },
    }


# Shell 命令黑名单（即使在 autonomous 模式下也阻止）
SHELL_BLACKLIST = [
    r"\brm\s+(-[rfR]+\s+)?/",
    r"\bmkfs\b",
    r"\bdd\s+.*of=/dev/",
    r":\(\)\s*\{",
    r"\bshutdown\b",
    r"\breboot\b",
    r"\binit\s+[06]\b",
    r"\bsystemctl\s+(halt|poweroff)\b",
    r"\bpasswd\b",
    r"\busermod\b",
    r"\buseradd\b",
    r"\buserdel\b",
    r"\bchmod\s+(-R\s+)?777\s+/",
    r"\bchown\s+(-R\s+)?.*\s+/",
    r">\s*/etc/",
    r"\btee\s+/etc/",
    r"\bcurl\b.*\|\s*(ba)?sh",
    r"\bwget\b.*\|\s*(ba)?sh",
    r"\biptables\s+-F\b",
    r"\.api_keys\b",
    r"\.telegram_config\b",
    r"\bconfig\.yaml\b",
    r"\blobe\.env\b",
    r"\bcrontab\s+-r\b",
]

_SHELL_PATTERNS = [re.compile(p, re.IGNORECASE) for p in SHELL_BLACKLIST]


def check_shell_command(command: str) -> tuple[bool, str]:
    """检查 shell 命令安全性（用于 autonomous 模式的底线防护）"""
    for pattern in _SHELL_PATTERNS:
        if pattern.search(command):
            return False, f"命令被安全策略拦截: 匹配黑名单规则"
    return True, ""

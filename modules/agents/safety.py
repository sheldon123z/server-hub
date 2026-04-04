"""安全层：interrupt_on 配置 + Shell 黑名单 + 风险标签

Deep Agents 使用 interrupt_on 参数控制人工审批，替代旧的自定义 safety_check 节点。
TOOL_RISK_MAP 仅用于前端 UI 展示风险等级标签。
"""

import re
import string
from enum import StrEnum


class RiskLevel(StrEnum):
    SAFE = "safe"
    MODERATE = "moderate"
    DANGER = "danger"


# 风险标签（仅 UI 展示用）
TOOL_RISK_MAP = {
    # 澄清工具
    "ask_clarification": RiskLevel.SAFE,
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
    # 页面上下文
    "get_page_data": RiskLevel.SAFE,
    # 用户深度管理
    "get_user_full_processes": RiskLevel.SAFE,
    "check_quota_violations": RiskLevel.SAFE,
    # 运维剧本工具
    "ssh_execute_command": RiskLevel.DANGER,
    "playbook_create": RiskLevel.MODERATE,
    "playbook_execute": RiskLevel.MODERATE,
    "playbook_list": RiskLevel.SAFE,
    "playbook_search": RiskLevel.SAFE,
    # 服务器舰队管理工具（非 SAFE，防止非 admin 用户通过 Agent 访问服务器信息）
    "server_list": RiskLevel.MODERATE,
    "server_test_connectivity": RiskLevel.MODERATE,
}


def build_interrupt_config(safety_mode: str, user_role: str = "admin") -> dict:
    """根据安全模式和用户角色生成 Deep Agents 的 interrupt_on 配置

    Args:
        safety_mode: "supervised"(危险操作需审批) 或 "autonomous"(全自动)
        user_role: "admin" 或 "user"
    """
    # 普通用户：拦截所有非 SAFE 工具
    if user_role != "admin":
        return {name: True for name, risk in TOOL_RISK_MAP.items() if risk != RiskLevel.SAFE}

    if safety_mode == "autonomous":
        return {}

    return {
        # 自定义危险工具 — 始终审批
        "kill_user_processes": True,
        "auto_fix_compliance": True,
        "execute_ops_script": True,
        "delete_cron_job_tool": True,
        "manage_linux_user": True,
        "ssh_execute_command": True,
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

# ---------------------------------------------------------------------------
# 编码/引号拼接绕过防护
# ---------------------------------------------------------------------------

# 管道到 shell 执行的模式（base64 -d | sh, echo xxx | bash 等）
_PIPE_TO_SHELL_RE = re.compile(
    r"\|\s*(ba)?sh\b|\|\s*zsh\b|\|\s*/bin/(ba)?sh\b|\|\s*/bin/zsh\b",
    re.IGNORECASE,
)

# 危险的间接执行原语
_INDIRECT_EXEC_PATTERNS = [
    re.compile(r"\beval\s+", re.IGNORECASE),
    re.compile(r"\bbase64\s+(-d|--decode)", re.IGNORECASE),
    re.compile(r"\bpython[23]?\s+(-c|--command)\b", re.IGNORECASE),
    re.compile(r"\bperl\s+-e\b", re.IGNORECASE),
    re.compile(r"\bruby\s+-e\b", re.IGNORECASE),
    re.compile(r"\bnode\s+-e\b", re.IGNORECASE),
    re.compile(r"\bphp\s+-r\b", re.IGNORECASE),
    # $() 子命令与反引号（嵌套执行）
    re.compile(r"\$\("),
    re.compile(r"`[^`]+`"),
    # source / . 执行远程内容
    re.compile(r"\bsource\s+/dev/(tcp|udp)/", re.IGNORECASE),
]


def _normalize_command(cmd: str) -> str:
    """对命令进行规范化处理，移除常见的编码/引号拼接绕过手法。

    处理的绕过手法：
    - Shell 引号拼接：'r'"m" → rm, "mk""fs" → mkfs
    - $'\\x??' ANSI-C 转义：$'\\x72\\x6d' → rm
    - $'\\0???' 八进制转义：$'\\0162\\0155' → rm
    - \\x?? 十六进制转义（裸转义）
    - \\u???? Unicode 转义
    - 连续空白折叠
    """
    normalized = cmd

    # 1. 展开 $'...' ANSI-C 引号内的转义序列
    def _expand_ansi_c(m: re.Match) -> str:
        inner = m.group(1)
        result: list[str] = []
        i = 0
        while i < len(inner):
            if inner[i] == "\\" and i + 1 < len(inner):
                nxt = inner[i + 1]
                if nxt == "x" and i + 3 < len(inner):
                    # \xHH
                    hex_val = inner[i + 2 : i + 4]
                    if all(c in string.hexdigits for c in hex_val):
                        result.append(chr(int(hex_val, 16)))
                        i += 4
                        continue
                elif nxt == "0" and i + 2 < len(inner):
                    # \0NNN 八进制
                    oct_chars = ""
                    j = i + 2
                    while j < len(inner) and j < i + 5 and inner[j] in "01234567":
                        oct_chars += inner[j]
                        j += 1
                    if oct_chars:
                        result.append(chr(int(oct_chars, 8)))
                        i = j
                        continue
                elif nxt == "u" and i + 5 < len(inner):
                    # \uHHHH
                    hex_val = inner[i + 2 : i + 6]
                    if all(c in string.hexdigits for c in hex_val):
                        result.append(chr(int(hex_val, 16)))
                        i += 6
                        continue
                elif nxt == "n":
                    result.append("\n")
                    i += 2
                    continue
                elif nxt == "t":
                    result.append("\t")
                    i += 2
                    continue
                # 其他转义，保留原字符
                result.append(nxt)
                i += 2
                continue
            result.append(inner[i])
            i += 1
        return "".join(result)

    normalized = re.sub(r"\$'([^']*)'", _expand_ansi_c, normalized)

    # 2. 展开裸 \xHH 十六进制转义
    def _expand_hex(m: re.Match) -> str:
        return chr(int(m.group(1), 16))

    normalized = re.sub(r"\\x([0-9a-fA-F]{2})", _expand_hex, normalized)

    # 3. 展开裸 \0NNN 八进制转义
    def _expand_oct(m: re.Match) -> str:
        return chr(int(m.group(1), 8))

    normalized = re.sub(r"\\0([0-7]{1,3})", _expand_oct, normalized)

    # 4. 移除引号拼接（移除不在转义序列中的引号字符）
    #    "r""m" → rm, 'mk''fs' → mkfs, "r"'m' → rm
    normalized = re.sub(r"""(?<!\\)['"]""", "", normalized)

    # 5. 移除反斜杠续行（r\m → rm）
    normalized = re.sub(r"\\(?=[a-zA-Z])", "", normalized)

    # 6. 折叠连续空白
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return normalized


def check_shell_command(command: str) -> tuple[bool, str]:
    """检查 shell 命令安全性（用于 autonomous 模式的底线防护）

    检测层次：
    1. 管道到 shell 的模式（| sh, | bash）
    2. 危险的间接执行原语（eval, base64 -d, python -c 等）
    3. 对原始命令进行规范化后匹配黑名单
    4. 对原始命令直接匹配黑名单（保留原有行为）
    """
    # --- 第一层：管道到 shell 检测 ---
    if _PIPE_TO_SHELL_RE.search(command):
        return False, "命令被安全策略拦截: 检测到管道到 shell 执行模式"

    # --- 第二层：间接执行原语检测 ---
    for pattern in _INDIRECT_EXEC_PATTERNS:
        if pattern.search(command):
            return False, "命令被安全策略拦截: 检测到间接代码执行模式"

    # --- 第三层：规范化后匹配黑名单 ---
    normalized = _normalize_command(command)
    if normalized != command:
        # 仅当规范化后有变化时，额外检查规范化结果
        for pattern in _SHELL_PATTERNS:
            if pattern.search(normalized):
                return False, "命令被安全策略拦截: 规范化后匹配黑名单规则"

    # --- 第四层：原始命令匹配黑名单（保留原有行为）---
    for pattern in _SHELL_PATTERNS:
        if pattern.search(command):
            return False, "命令被安全策略拦截: 匹配黑名单规则"

    return True, ""

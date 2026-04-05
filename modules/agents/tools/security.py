"""安全合规工具"""

from modules.agents.tools.registry import RiskLevel, register_tool


@register_tool(risk=RiskLevel.SAFE, group="security:read", icon="Shield", label="合规检查")
def check_compliance(category: str = "") -> str:
    """执行安全合规基线检查。基于 CIS Benchmark 标准检查 SSH、口令策略、文件权限、网络安全等配置。

    Args:
        category: 可选，只检查指定分类（如 SSH安全、口令策略、网络安全）。留空检查全部。
    """
    from modules.agents.compliance import run_compliance_checks

    return run_compliance_checks(category)


@register_tool(risk=RiskLevel.DANGER, group="security:write", icon="ShieldCheck", label="自动修复合规")
def auto_fix_compliance(item_id: str) -> str:
    """自动修复指定的不合规项。仅对白名单中的 auto_fixable 项生效，并在执行后验证结果。

    Args:
        item_id: 合规基线项 ID（如 ssh_empty_password, ssh_max_auth_tries）
    """
    from modules.agents.compliance import fix_compliance_item

    return fix_compliance_item(item_id)

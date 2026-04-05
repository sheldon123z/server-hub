"""告警管理工具"""

from langchain_core.tools import tool


@tool
async def list_active_alerts(server_id: str = "local") -> str:
    """列出当前所有活跃（firing）告警。

    Args:
        server_id: 服务器 ID，默认为 'local'，'*' 表示所有服务器
    """
    from modules.alerts.services import get_active_alerts

    sid = None if server_id == "*" else server_id
    alerts = await get_active_alerts(server_id=sid, limit=50)
    if not alerts:
        return "当前无活跃告警。"

    lines = [f"当前活跃告警 ({len(alerts)} 条):"]
    for a in alerts:
        lines.append(
            f"  [{a.get('severity', 'warning').upper()}] {a.get('rule_name') or a.get('rule_id')} "
            f"| 值={a.get('value')} | {a.get('message') or ''} | 触发时间={a.get('fired_at')}"
        )
    return "\n".join(lines)


@tool
async def acknowledge_alert(alert_id: int, username: str = "agent") -> str:
    """确认（acknowledge）一条活跃告警。

    Args:
        alert_id: 告警历史记录 ID
        username: 确认操作者名称
    """
    from modules.alerts.services import acknowledge_alert as ack

    ok = await ack(alert_id, username)
    if ok:
        return f"告警 #{alert_id} 已确认（操作者: {username}）。"
    return f"告警 #{alert_id} 不存在或已不处于 firing 状态。"

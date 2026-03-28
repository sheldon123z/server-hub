"""Network management API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse

from auth.dependencies import require_role
from modules.network.services import (
    get_listening_ports,
    get_proxy_status,
    get_connections_summary,
    get_firewall_rules,
)

router = APIRouter(prefix="/api/network", tags=["网络管理"])


@router.get("/ports")
async def list_listening_ports(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(require_role("admin")),
):
    """List all listening TCP ports."""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.execute_command("ss -tlnp", timeout=10)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        # 解析 ss 输出为结构化数据
        ports = []
        for line in result["data"].get("output", "").strip().splitlines()[1:]:  # 跳过表头
            parts = line.split()
            if len(parts) >= 4:
                local_addr = parts[3]
                process = parts[5] if len(parts) >= 6 else ""
                ports.append({"local_address": local_addr, "process": process, "state": parts[0]})
        return {"ports": ports, "count": len(ports)}
    try:
        ports = await get_listening_ports()
        return {"ports": ports, "count": len(ports)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/proxy")
async def proxy_status(user=Depends(require_role("admin"))):
    """Check proxy and clash status."""
    try:
        status = await get_proxy_status()
        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections")
async def connections_summary(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(require_role("admin")),
):
    """Get network connection statistics."""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.execute_command("ss -s", timeout=10)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        return {"raw": result["data"].get("output", "")}
    try:
        summary = await get_connections_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/firewall")
async def firewall_rules(user=Depends(require_role("admin"))):
    """Get iptables firewall rules. Returns plain text."""
    try:
        rules = await get_firewall_rules()
        return PlainTextResponse(content=rules)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

"""Network management API routes."""

from fastapi import APIRouter, Depends, HTTPException
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
async def list_listening_ports(user=Depends(require_role("admin"))):
    """List all listening TCP ports."""
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
async def connections_summary(user=Depends(require_role("admin"))):
    """Get network connection statistics."""
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

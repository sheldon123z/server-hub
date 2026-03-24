"""System settings API routes.

Exposes non-sensitive configuration values only.
"""

from fastapi import APIRouter, Depends

from auth.dependencies import require_role
from config import settings

router = APIRouter(prefix="/api/settings", tags=["系统设置"])


@router.get("/")
async def get_settings(user=Depends(require_role("admin"))):
    """Return current non-sensitive system settings.

    Excludes secret_key, passwords, and other sensitive values.
    """
    return {
        "metrics_interval": getattr(settings, "metrics_interval", None),
        "retention_days": getattr(settings, "retention_days", None),
        "managed_services": getattr(settings, "managed_services", []),
        "compose_stacks": getattr(settings, "compose_stacks", []),
        "log_dirs": getattr(settings, "log_dirs", []),
        "admin_linux_users": getattr(settings, "admin_linux_users", []),
    }

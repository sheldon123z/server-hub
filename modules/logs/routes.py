"""Log viewer API routes."""

from fastapi import APIRouter, Depends, HTTPException, Query

from auth.dependencies import require_role
from modules.logs.services import list_log_files, tail_log, search_log, stream_log

router = APIRouter(prefix="/api/logs", tags=["日志查看"])


@router.get("/files")
async def get_log_files(
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(require_role("admin")),
):
    """List all discoverable log files in configured directories."""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        client = await get_agent_client(server_id)
        result = await client.execute_command(
            "find /var/log -maxdepth 2 -type f -name '*.log' -o -name 'syslog' -o -name 'auth.log' 2>/dev/null | head -50",
            timeout=10,
        )
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        files = [
            {"path": f.strip(), "name": f.strip().split("/")[-1]}
            for f in result["data"].get("output", "").strip().splitlines()
            if f.strip()
        ]
        return {"files": files, "count": len(files)}
    files = list_log_files()
    return {"files": files, "count": len(files)}


@router.get("/tail")
async def get_log_tail(
    path: str = Query(..., description="Log file path"),
    lines: int = Query(200, ge=1, le=10000, description="Number of lines"),
    server_id: str = Query(default="local", description="目标服务器"),
    user=Depends(require_role("admin")),
):
    """Read the last N lines of a log file."""
    if server_id != "local":
        from modules.servers.agent_client import get_agent_client
        # 基本路径安全检查 — 只允许 /var/log 下的文件
        if not path.startswith("/var/log"):
            raise HTTPException(status_code=403, detail="远程日志仅允许读取 /var/log 下的文件")
        client = await get_agent_client(server_id)
        result = await client.execute_command(f"tail -n {lines} {path} 2>&1", timeout=15)
        if not result.get("ok"):
            raise HTTPException(status_code=502, detail=result.get("error", "远程请求失败"))
        return {"path": path, "lines": lines, "content": result["data"].get("output", "")}
    try:
        content = await tail_log(path, lines)
        return {"path": path, "lines": lines, "content": content}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search")
async def search_in_log(
    path: str = Query(..., description="Log file path"),
    q: str = Query(..., min_length=1, max_length=500, description="Search pattern"),
    max: int = Query(100, ge=1, le=5000, alias="max", description="Max results"),
    user=Depends(require_role("admin")),
):
    """Search for a pattern in a log file."""
    try:
        results = await search_log(path, q, max)
        return {"path": path, "pattern": q, "results": results, "count": len(results)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stream")
async def stream_log_sse(
    path: str = Query(..., description="Log file path"),
    user=Depends(require_role("admin")),
):
    """Stream new log lines via Server-Sent Events."""
    from sse_starlette.sse import EventSourceResponse

    try:
        # Validate path before starting stream
        from modules.logs.services import _validate_log_path
        _validate_log_path(path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

    async def event_generator():
        async for line in stream_log(path):
            yield {"event": "log", "data": line}

    return EventSourceResponse(event_generator())

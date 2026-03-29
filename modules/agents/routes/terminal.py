"""WebSocket 终端路由"""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

logger = logging.getLogger(__name__)


@router.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    """WebSocket 驱动的 PTY 终端（仅管理员）"""
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4001, reason="未认证")
        return
    try:
        from auth.dependencies import get_user_from_access_token

        user = await get_user_from_access_token(token)
        if not user or user.get("disabled") or user["role"] != "admin":
            await websocket.close(code=4003, reason="权限不足")
            return
    except Exception:
        await websocket.close(code=4001, reason="认证失败")
        return
    await websocket.accept()

    from modules.agents.terminal import WebTerminal
    terminal = WebTerminal()
    terminal.spawn()

    try:
        async def read_terminal():
            """持续读取终端输出并发送到 WebSocket"""
            while terminal.is_alive():
                data = terminal.read()
                if data:
                    await websocket.send_text(data)
                else:
                    await asyncio.sleep(0.05)

        async def write_terminal():
            """接收 WebSocket 输入并写入终端"""
            while True:
                data = await websocket.receive_text()
                # 支持 resize 消息
                if data.startswith("\x1b[resize:"):
                    try:
                        parts = data.split(":")[1].rstrip("]").split(",")
                        cols, rows = int(parts[0]), int(parts[1])
                        terminal.resize(cols, rows)
                    except Exception as e:
                        logger.debug("终端 resize 解析失败: %s", e)
                else:
                    terminal.write(data)

        await asyncio.gather(read_terminal(), write_terminal())

    except WebSocketDisconnect:
        logger.info("Terminal WebSocket disconnected")
    except Exception as e:
        logger.error("Terminal error: %s", e)
    finally:
        terminal.close()

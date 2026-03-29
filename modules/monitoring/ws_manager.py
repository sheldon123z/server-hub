"""
WebSocket 连接管理器
管理实时指标推送的 WebSocket 连接、订阅过滤和内存缓存
"""

import logging
from collections import deque

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class MetricsWSManager:
    """WebSocket 管理器 — 支持 per-client 服务器订阅过滤 + 内存缓存"""

    def __init__(self):
        self._connections: dict[WebSocket, set[str]] = {}  # ws → subscribed server_ids
        self._cache: dict[str, deque] = {}  # server_id → recent snapshots (5min)
        self._cache_max = 60  # 5min @ 5s interval

    async def connect(self, ws: WebSocket, server_ids: set[str] | None = None):
        await ws.accept()
        subs = server_ids or {"local"}
        self._connections[ws] = subs
        logger.info("WebSocket 客户端连接, 订阅=%s (当前: %d)", subs, len(self._connections))

        # Push cached data immediately so client doesn't wait
        for sid in subs:
            if sid in self._cache:
                for snapshot in self._cache[sid]:
                    try:
                        await ws.send_json(snapshot)
                    except Exception:
                        break

    def disconnect(self, ws: WebSocket):
        subs = self._connections.pop(ws, None)
        logger.info("WebSocket 客户端断开, 订阅=%s (当前: %d)", subs, len(self._connections))

    async def update_subscription(self, ws: WebSocket, server_ids: set[str]):
        """Update a client's subscription list and push cached data for new subscriptions"""
        if ws in self._connections:
            old = self._connections[ws]
            self._connections[ws] = server_ids
            logger.debug("WebSocket 订阅更新: %s → %s", old, server_ids)

            # Push cached snapshots for newly subscribed servers
            new_sids = server_ids - old if "*" not in old else set()
            if "*" in server_ids:
                new_sids = set(self._cache.keys()) - (old if "*" not in old else set())
            for sid in new_sids:
                if sid in self._cache:
                    for snapshot in self._cache[sid]:
                        try:
                            await ws.send_json(snapshot)
                        except Exception:
                            return

    async def broadcast(self, message: dict):
        """Broadcast to subscribed clients only"""
        server_id = message.get("server_id", "local")

        # Update cache
        if server_id not in self._cache:
            self._cache[server_id] = deque(maxlen=self._cache_max)
        self._cache[server_id].append(message)

        # Send to subscribed clients
        if not self._connections:
            return
        disconnected = []
        for ws, subscribed in self._connections.items():
            if "*" in subscribed or server_id in subscribed:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# 模块级单例
ws_manager = MetricsWSManager()

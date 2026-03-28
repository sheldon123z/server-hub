"""HTTP 客户端 — 与远程 serverhub-agent 通信"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# 模块级连接池，复用跨请求的 TCP 连接
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    """获取/创建全局 httpx 异步客户端（连接池复用）"""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
            follow_redirects=False,
        )
    return _http_client


async def close_http_client() -> None:
    """关闭全局 HTTP 客户端（应用关闭时调用）"""
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None


def _error_result(msg: str, **extra) -> dict:
    """构造统一的错误返回结构"""
    return {"ok": False, "error": msg, **extra}


class AgentClient:
    """与单台远程服务器上的 serverhub-agent 交互的 HTTP 客户端"""

    def __init__(self, server: dict):
        self.server_id: str = server["id"]
        self.server_name: str = server.get("name", "unknown")
        self.base_url: str = f"http://{server['ip_address']}:{server.get('agent_port', 9901)}"
        self.token: str = server.get("_decrypted_token", "")

    @property
    def _headers(self) -> dict[str, str]:
        """构造认证请求头"""
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        timeout: float | None = None,
        json_body: dict | None = None,
        need_auth: bool = True,
    ) -> dict[str, Any]:
        """
        统一请求方法，处理超时/连接错误，返回结构化结果。
        成功时返回 {"ok": True, "data": <response_json>}
        失败时返回 {"ok": False, "error": "<描述>"}
        """
        client = _get_http_client()
        headers = self._headers if need_auth else {"Accept": "application/json"}
        url = f"{self.base_url}{path}"

        try:
            kwargs: dict[str, Any] = {"headers": headers}
            if timeout is not None:
                kwargs["timeout"] = timeout
            if json_body is not None:
                kwargs["json"] = json_body

            resp = await client.request(method, url, **kwargs)

            if resp.status_code == 401:
                return _error_result("认证失败: token 无效或未提供", status_code=401)
            if resp.status_code == 403:
                return _error_result("认证失败: token 被拒绝", status_code=403)

            if resp.status_code >= 400:
                detail = ""
                try:
                    detail = resp.json().get("detail", "")
                except Exception:
                    detail = resp.text[:200]
                return _error_result(
                    f"Agent 返回错误 HTTP {resp.status_code}: {detail}",
                    status_code=resp.status_code,
                )

            return {"ok": True, "data": resp.json()}

        except httpx.ConnectError:
            msg = f"无法连接到 Agent ({self.server_name} @ {self.base_url})"
            logger.warning(msg)
            return _error_result(msg)
        except httpx.TimeoutException:
            msg = f"Agent 请求超时 ({self.server_name} @ {url})"
            logger.warning(msg)
            return _error_result(msg)
        except httpx.HTTPError as e:
            msg = f"Agent HTTP 错误 ({self.server_name}): {type(e).__name__}: {e}"
            logger.error(msg)
            return _error_result(msg)
        except Exception as e:
            msg = f"Agent 请求异常 ({self.server_name}): {type(e).__name__}: {e}"
            logger.error(msg, exc_info=True)
            return _error_result(msg)

    # ─── 公开方法 ───

    async def health_check(self) -> dict:
        """
        检查 agent 是否存活。
        health 端点不需要认证（与 hub 端 test_connectivity 行为一致）。
        """
        return await self._request("GET", "/health", timeout=5.0, need_auth=False)

    async def get_metrics(self) -> dict:
        """获取完整指标快照（含 CPU 1s 阻塞采样，耗时较长）"""
        return await self._request("GET", "/metrics", timeout=20.0)

    async def get_fast_metrics(self) -> dict:
        """获取轻量级指标快照（用于仪表盘 sparkline）"""
        return await self._request("GET", "/metrics/fast", timeout=8.0)

    async def execute_command(self, command: str, timeout: int = 30) -> dict:
        """
        在远程服务器上执行命令。
        timeout 参数传给 agent 端的命令执行超时。
        HTTP 请求本身的超时设为 timeout + 5 秒（留出网络余量）。
        """
        return await self._request(
            "POST",
            "/execute",
            json_body={"command": command, "timeout": timeout},
            timeout=float(timeout + 5),
        )

    async def get_docker_containers(self) -> dict:
        """列出远程服务器上的 Docker 容器"""
        return await self._request("GET", "/docker/containers", timeout=15.0)

    async def get_services(self) -> dict:
        """列出远程服务器上的 systemd 服务"""
        return await self._request("GET", "/services", timeout=10.0)


# ─── 工厂函数 ───


async def get_agent_client(server_id: str) -> AgentClient:
    """
    工厂函数: 根据 server_id 从数据库加载服务器信息并创建 AgentClient。
    自动解密 agent_token_hash (Fernet 加密) 为明文 token。
    """
    from modules.servers.services import get_server, decrypt_agent_token

    server = await get_server(server_id)
    if not server:
        raise ValueError(f"服务器 {server_id} 不存在")

    server["_decrypted_token"] = decrypt_agent_token(server.get("agent_token_hash", ""))

    return AgentClient(server)


async def get_all_agent_clients(status_filter: str | None = "online") -> list[AgentClient]:
    """
    批量获取所有（在线）服务器的 AgentClient。
    排除 is_local=True 的本机（本机指标直接采集，不走 agent）。
    """
    from modules.servers.services import list_servers

    from modules.servers.services import decrypt_agent_token

    servers = await list_servers(status_filter=status_filter)
    clients = []
    for srv in servers:
        if srv.get("is_local"):
            continue
        srv["_decrypted_token"] = decrypt_agent_token(srv.get("agent_token_hash", ""))
        clients.append(AgentClient(srv))
    return clients

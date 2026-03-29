"""多服务器管理模块测试 — 覆盖 Schema 校验、服务层 CRUD、Agent 客户端、心跳、远程采集、路由"""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ═══════════════════════════════════════════════════════════════════════════
# 1. Schema Validation Tests (sync, no DB)
# ═══════════════════════════════════════════════════════════════════════════


class TestServerCreateRequest:
    def test_valid_input(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="test-server", ip_address="192.168.1.100")
        assert req.name == "test-server"
        assert req.ip_address == "192.168.1.100"
        assert req.agent_port == 9901
        assert req.ssh_port == 22
        assert req.tags == []

    def test_missing_required_name(self):
        from pydantic import ValidationError

        from modules.servers.schemas import ServerCreateRequest

        with pytest.raises(ValidationError):
            ServerCreateRequest(ip_address="192.168.1.1")

    def test_missing_required_ip(self):
        from pydantic import ValidationError

        from modules.servers.schemas import ServerCreateRequest

        with pytest.raises(ValidationError):
            ServerCreateRequest(name="server1")

    def test_ip_max_length(self):
        from pydantic import ValidationError

        from modules.servers.schemas import ServerCreateRequest

        with pytest.raises(ValidationError):
            ServerCreateRequest(name="s", ip_address="x" * 46)

    def test_hostname_auto_fill_from_name(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="my-host", ip_address="10.0.0.1", hostname="")
        assert req.hostname == "my-host"

    def test_hostname_explicit(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="alias", ip_address="10.0.0.1", hostname="real.host")
        assert req.hostname == "real.host"

    def test_full_input(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(
            name="prod-1",
            hostname="prod-server-1.local",
            ip_address="10.0.0.5",
            agent_port=9999,
            ssh_user="root",
            ssh_port=2222,
            ssh_key_credential="cred-id-123",
            tags="web,production,gpu",
        )
        assert req.agent_port == 9999
        assert req.ssh_user == "root"
        assert req.ssh_port == 2222
        assert req.ssh_key_credential == "cred-id-123"
        assert req.tags == ["web", "production", "gpu"]


class TestServerUpdateRequest:
    def test_partial_update(self):
        from modules.servers.schemas import ServerUpdateRequest

        req = ServerUpdateRequest(name="new-name")
        assert req.name == "new-name"
        assert req.ip_address is None
        assert req.tags is None

    def test_empty_update(self):
        from modules.servers.schemas import ServerUpdateRequest

        req = ServerUpdateRequest()
        dump = req.model_dump(exclude_unset=True)
        assert dump == {}

    def test_tags_none_preserved(self):
        from modules.servers.schemas import ServerUpdateRequest

        req = ServerUpdateRequest()
        assert req.tags is None  # None means "not updating tags"


class TestServerGroupCreateRequest:
    def test_valid_input(self):
        from modules.servers.schemas import ServerGroupCreateRequest

        req = ServerGroupCreateRequest(name="production")
        assert req.name == "production"
        assert req.color == "#38bdf8"
        assert req.description is None

    def test_invalid_color(self):
        from pydantic import ValidationError

        from modules.servers.schemas import ServerGroupCreateRequest

        with pytest.raises(ValidationError):
            ServerGroupCreateRequest(name="g", color="red")

    def test_valid_color(self):
        from modules.servers.schemas import ServerGroupCreateRequest

        req = ServerGroupCreateRequest(name="g", color="#ff0000")
        assert req.color == "#ff0000"


class TestNormalizeTags:
    def test_string_input(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="s", ip_address="1.2.3.4", tags="web, api, gpu")
        assert req.tags == ["web", "api", "gpu"]

    def test_list_input(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="s", ip_address="1.2.3.4", tags=["web", "api"])
        assert req.tags == ["web", "api"]

    def test_empty_string(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="s", ip_address="1.2.3.4", tags="")
        assert req.tags == []

    def test_empty_list(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="s", ip_address="1.2.3.4", tags=[])
        assert req.tags == []

    def test_strips_whitespace(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="s", ip_address="1.2.3.4", tags="  web , api  ")
        assert req.tags == ["web", "api"]

    def test_filters_empty_strings(self):
        from modules.servers.schemas import ServerCreateRequest

        req = ServerCreateRequest(name="s", ip_address="1.2.3.4", tags="web,,api,")
        assert req.tags == ["web", "api"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Services Tests (async, need DB)
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(scope="session")
async def test_db():
    """Initialize an in-memory test database and patch database._db"""
    import aiosqlite

    import database

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    # Patch the module-level _db so get_db() returns our test connection
    database._db = db
    await database.init_tables(db)
    yield db
    await db.close()
    database._db = None


class TestBootstrapLocalServer:
    async def test_local_server_exists(self, test_db):
        """init_tables should create a 'local' server record"""
        from modules.servers.services import get_server

        server = await get_server("local")
        assert server is not None
        assert server["is_local"] is True
        assert server["status"] == "online"
        assert server["ip_address"] == "127.0.0.1"


class TestCreateServer:
    async def test_create_valid(self, test_db):
        from modules.servers.services import create_server, get_server

        sid = await create_server(
            {
                "name": "test-remote-1",
                "hostname": "remote-1.local",
                "ip_address": "10.0.0.10",
                "agent_port": 9901,
                "tags": ["gpu", "training"],
            },
            created_by="admin",
        )
        assert sid  # non-empty ID
        server = await get_server(sid)
        assert server is not None
        assert server["name"] == "test-remote-1"
        assert server["hostname"] == "remote-1.local"
        assert server["ip_address"] == "10.0.0.10"
        assert server["tags"] == ["gpu", "training"]
        assert server["is_local"] is False
        assert server["status"] == "unknown"

    async def test_create_duplicate_name(self, test_db):
        from modules.servers.services import create_server

        await create_server(
            {"name": "unique-test", "hostname": "h", "ip_address": "10.0.0.20"},
            created_by="admin",
        )
        # Second create with same name should fail (UNIQUE constraint)
        with pytest.raises(Exception, match="UNIQUE"):
            await create_server(
                {"name": "unique-test", "hostname": "h2", "ip_address": "10.0.0.21"},
                created_by="admin",
            )


class TestListServers:
    async def test_list_includes_local(self, test_db):
        from modules.servers.services import list_servers

        servers = await list_servers()
        names = [s["name"] for s in servers]
        # Local server should be present
        assert any(s["is_local"] for s in servers)
        # Previously created server should be present
        assert "test-remote-1" in names

    async def test_list_filter_status(self, test_db):
        from modules.servers.services import list_servers

        online = await list_servers(status_filter="online")
        # Local server is 'online'
        assert any(s["is_local"] for s in online)
        # test-remote-1 has status 'unknown', should not appear in 'online' filter
        assert not any(s["name"] == "test-remote-1" for s in online)

        unknown = await list_servers(status_filter="unknown")
        assert any(s["name"] == "test-remote-1" for s in unknown)


class TestGetServer:
    async def test_get_existing(self, test_db):
        from modules.servers.services import get_server

        server = await get_server("local")
        assert server is not None
        assert server["id"] == "local"

    async def test_get_nonexistent(self, test_db):
        from modules.servers.services import get_server

        server = await get_server("nonexistent-id-12345")
        assert server is None


class TestUpdateServer:
    async def test_update_name(self, test_db):
        from modules.servers.services import create_server, get_server, update_server

        sid = await create_server(
            {"name": "update-test", "hostname": "h", "ip_address": "10.0.0.30"},
            created_by="admin",
        )
        await update_server(sid, {"name": "updated-name"})
        server = await get_server(sid)
        assert server["name"] == "updated-name"

    async def test_update_clear_field(self, test_db):
        from modules.servers.services import create_server, get_server, update_server

        sid = await create_server(
            {
                "name": "clear-test",
                "hostname": "h",
                "ip_address": "10.0.0.31",
                "ssh_user": "root",
            },
            created_by="admin",
        )
        server = await get_server(sid)
        assert server["ssh_user"] == "root"

        # Clear ssh_user by setting to None
        await update_server(sid, {"ssh_user": None})
        server = await get_server(sid)
        assert server["ssh_user"] is None

    async def test_update_nonexistent(self, test_db):
        from modules.servers.services import update_server

        with pytest.raises(ValueError, match="不存在"):
            await update_server("no-such-id", {"name": "x"})

    async def test_update_empty(self, test_db):
        """Empty update dict should be a no-op"""
        from modules.servers.services import update_server

        await update_server("local", {})  # should not raise


class TestDeleteServer:
    async def test_delete_normal(self, test_db):
        from modules.servers.services import create_server, delete_server, get_server

        sid = await create_server(
            {"name": "delete-me", "hostname": "h", "ip_address": "10.0.0.40"},
            created_by="admin",
        )
        assert await get_server(sid) is not None
        await delete_server(sid)
        assert await get_server(sid) is None

    async def test_delete_local_server(self, test_db):
        from modules.servers.services import delete_server

        with pytest.raises(ValueError, match="不能删除本机"):
            await delete_server("local")

    async def test_delete_nonexistent(self, test_db):
        from modules.servers.services import delete_server

        with pytest.raises(ValueError, match="不存在"):
            await delete_server("no-such-id")


class TestFleetOverview:
    async def test_fleet_counts(self, test_db):
        from modules.servers.services import get_fleet_overview

        overview = await get_fleet_overview()
        assert "total" in overview
        assert "online" in overview
        assert "offline" in overview
        assert overview["total"] >= 1  # at least local
        assert overview["online"] >= 1  # local is online


class TestGroups:
    async def test_create_group(self, test_db):
        from modules.servers.services import create_group, list_groups

        gid = await create_group({"name": "production", "description": "Prod servers", "color": "#ff0000"})
        assert gid

        groups = await list_groups()
        assert any(g["name"] == "production" for g in groups)

    async def test_delete_group(self, test_db):
        from modules.servers.services import create_group, delete_group, list_groups

        gid = await create_group({"name": "temp-group"})
        await delete_group(gid)

        groups = await list_groups()
        assert not any(g["name"] == "temp-group" for g in groups)

    async def test_delete_nonexistent_group(self, test_db):
        from modules.servers.services import delete_group

        with pytest.raises(ValueError, match="不存在"):
            await delete_group("no-such-group")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Agent Client Tests (async, mock HTTP)
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentClient:
    def _make_client(self, **overrides):
        from modules.servers.agent_client import AgentClient

        server = {
            "id": "test-id",
            "name": "test-server",
            "ip_address": "10.0.0.50",
            "agent_port": 9901,
            "_decrypted_token": "test-token",
        }
        server.update(overrides)
        return AgentClient(server)

    async def test_health_check_success(self):
        import httpx

        from modules.servers.agent_client import _get_http_client

        client = self._make_client()

        mock_response = httpx.Response(
            200,
            json={"status": "ok", "version": "0.1.0"},
            request=httpx.Request("GET", "http://test"),
        )

        with patch.object(
            _get_http_client().__class__, "request", new_callable=AsyncMock, return_value=mock_response
        ) as mock_req:
            # Patch the global client's request method
            pass

        # Use a simpler approach: patch _get_http_client
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False

        with patch("modules.servers.agent_client._get_http_client", return_value=mock_http):
            result = await client.health_check()

        assert result["ok"] is True
        assert result["data"]["status"] == "ok"

    async def test_health_check_timeout(self):
        import httpx

        client = self._make_client()

        mock_http = AsyncMock()
        mock_http.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_http.is_closed = False

        with patch("modules.servers.agent_client._get_http_client", return_value=mock_http):
            result = await client.health_check()

        assert result["ok"] is False
        assert "超时" in result["error"]

    async def test_get_metrics_success(self):
        import httpx

        client = self._make_client()
        metrics_data = {"cpu": {"overall_percent": 25.0}, "memory": {"ram": {"percent": 60.0}}}

        mock_response = httpx.Response(200, json=metrics_data, request=httpx.Request("GET", "http://test"))
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False

        with patch("modules.servers.agent_client._get_http_client", return_value=mock_http):
            result = await client.get_metrics()

        assert result["ok"] is True
        assert result["data"]["cpu"]["overall_percent"] == 25.0

    async def test_get_metrics_connection_error(self):
        import httpx

        client = self._make_client()

        mock_http = AsyncMock()
        mock_http.request = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        mock_http.is_closed = False

        with patch("modules.servers.agent_client._get_http_client", return_value=mock_http):
            result = await client.get_metrics()

        assert result["ok"] is False
        assert "无法连接" in result["error"]

    async def test_execute_command_success(self):
        import httpx

        client = self._make_client()
        exec_data = {"stdout": "Hello\n", "stderr": "", "exit_code": 0}

        mock_response = httpx.Response(200, json=exec_data, request=httpx.Request("POST", "http://test"))
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False

        with patch("modules.servers.agent_client._get_http_client", return_value=mock_http):
            result = await client.execute_command("echo Hello")

        assert result["ok"] is True
        assert result["data"]["stdout"] == "Hello\n"

    async def test_auth_failure_401(self):
        import httpx

        client = self._make_client()

        mock_response = httpx.Response(
            401, json={"detail": "Missing token"}, request=httpx.Request("GET", "http://test")
        )
        mock_http = AsyncMock()
        mock_http.request = AsyncMock(return_value=mock_response)
        mock_http.is_closed = False

        with patch("modules.servers.agent_client._get_http_client", return_value=mock_http):
            result = await client.get_metrics()

        assert result["ok"] is False
        assert "认证失败" in result["error"]

    async def test_base_url_construction(self):
        client = self._make_client(ip_address="192.168.1.1", agent_port=8080)
        assert client.base_url == "http://192.168.1.1:8080"

    async def test_headers_with_token(self):
        client = self._make_client(_decrypted_token="my-secret")
        assert client._headers["Authorization"] == "Bearer my-secret"

    async def test_headers_without_token(self):
        client = self._make_client(_decrypted_token="")
        assert "Authorization" not in client._headers


class TestGetAgentClientFactory:
    async def test_creates_client(self, test_db):
        from modules.servers.agent_client import get_agent_client
        from modules.servers.services import create_server

        sid = await create_server(
            {"name": "factory-test", "hostname": "h", "ip_address": "10.0.0.60"},
            created_by="admin",
        )
        client = await get_agent_client(sid)
        assert client.server_id == sid
        assert client.base_url == "http://10.0.0.60:9901"

    async def test_nonexistent_raises(self, test_db):
        from modules.servers.agent_client import get_agent_client

        with pytest.raises(ValueError, match="不存在"):
            await get_agent_client("no-such-id")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Heartbeat Tests (async, mock)
# ═══════════════════════════════════════════════════════════════════════════


class TestHeartbeat:
    async def test_check_all_servers_updates_status(self, test_db):
        """When health_check returns ok, server status should be updated to online"""
        from modules.servers.services import create_server, get_server

        sid = await create_server(
            {"name": "hb-test-online", "hostname": "h", "ip_address": "10.0.0.70"},
            created_by="admin",
        )
        # Verify initial status is 'unknown'
        server = await get_server(sid)
        assert server["status"] == "unknown"

        # AgentClient is imported inside _check_all_servers from modules.servers.agent_client
        # heartbeat code checks result.get("status") == "ok" directly
        mock_health = AsyncMock(return_value={"status": "ok", "version": "0.1.0"})

        with patch("modules.servers.agent_client.AgentClient") as MockClient:
            instance = MagicMock()
            instance.health_check = mock_health
            MockClient.return_value = instance
            from modules.servers.heartbeat import _check_all_servers

            await _check_all_servers()

        server = await get_server(sid)
        assert server["status"] == "online"

    async def test_check_offline_server(self, test_db):
        """When health_check times out, server status should be offline"""
        from database import get_db
        from modules.servers.services import create_server, get_server

        sid = await create_server(
            {"name": "hb-test-offline", "hostname": "h", "ip_address": "10.0.0.71"},
            created_by="admin",
        )

        # Set status to online first so we can verify it changes to offline
        db = await get_db()
        await db.execute("UPDATE servers SET status = 'online' WHERE id = ?", (sid,))
        await db.commit()

        mock_health = AsyncMock(side_effect=TimeoutError())

        with patch("modules.servers.agent_client.AgentClient") as MockClient:
            instance = MagicMock()
            instance.health_check = mock_health
            MockClient.return_value = instance
            from modules.servers.heartbeat import _check_all_servers

            await _check_all_servers()

        server = await get_server(sid)
        assert server["status"] == "offline"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Scheduler Remote Collection Tests (async, mock)
# ═══════════════════════════════════════════════════════════════════════════


class TestRemoteCollect:
    async def test_remote_collect_stores_metrics(self, test_db):
        """Mock agent client, verify metrics stored with server_id"""
        from database import get_db
        from modules.servers.services import create_server

        sid = await create_server(
            {"name": "remote-collect-test", "hostname": "h", "ip_address": "10.0.0.80"},
            created_by="admin",
        )
        # Set status to online so it gets collected
        db = await get_db()
        await db.execute("UPDATE servers SET status = 'online' WHERE id = ?", (sid,))
        await db.commit()

        fake_metrics = {"cpu": {"overall_percent": 50.0}, "memory": {"ram": {"percent": 70.0}}}

        mock_client_instance = MagicMock()
        mock_client_instance.get_metrics_full = AsyncMock(return_value=fake_metrics)

        # Mock ws_manager.broadcast to avoid import errors
        mock_ws = MagicMock()
        mock_ws.broadcast = AsyncMock()

        with patch("modules.servers.agent_client.AgentClient", return_value=mock_client_instance):
            with patch("modules.monitoring.scheduler.ws_manager", mock_ws, create=True):
                from modules.monitoring.scheduler import _collect_remote_metrics

                await _collect_remote_metrics()

        # Check that metrics were stored
        row = await (
            await db.execute("SELECT * FROM metrics WHERE server_id = ? ORDER BY id DESC LIMIT 1", (sid,))
        ).fetchone()
        assert row is not None
        stored = json.loads(row["value_json"])
        assert stored["cpu"]["overall_percent"] == 50.0

    async def test_remote_collect_skips_offline(self, test_db):
        """Offline servers should not be queried"""
        from database import get_db
        from modules.servers.services import create_server

        sid = await create_server(
            {"name": "remote-offline-skip", "hostname": "h", "ip_address": "10.0.0.81"},
            created_by="admin",
        )
        # Leave status as 'unknown' (not 'online')
        db = await get_db()

        # Count metrics before
        before = await (await db.execute("SELECT COUNT(*) as cnt FROM metrics WHERE server_id = ?", (sid,))).fetchone()

        with patch("modules.servers.agent_client.AgentClient") as MockClient:
            from modules.monitoring.scheduler import _collect_remote_metrics

            await _collect_remote_metrics()

        # Count metrics after - should be same (no new metrics)
        after = await (await db.execute("SELECT COUNT(*) as cnt FROM metrics WHERE server_id = ?", (sid,))).fetchone()
        assert after["cnt"] == before["cnt"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. serverhub-agent Tests (sync)
# ═══════════════════════════════════════════════════════════════════════════


class TestAgentCollectors:
    def test_collect_fast(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "serverhub-agent"))
        from serverhub_agent_collectors import collect_fast

        result = collect_fast()
        assert "cpu_percent" in result
        assert "memory_percent" in result
        assert "timestamp" in result
        assert isinstance(result["cpu_percent"], (int, float))
        assert isinstance(result["memory_percent"], (int, float))

    def test_collect_all(self):
        from serverhub_agent_collectors import collect_all

        result = collect_all()
        assert "cpu" in result
        assert "memory" in result
        assert "disk" in result
        assert "network" in result
        assert "hostname" in result
        assert "uptime" in result
        assert "timestamp" in result


# Import helper for serverhub-agent collectors with a unique module name
# to avoid collision with hub-side collectors
@pytest.fixture(scope="session", autouse=True)
def _setup_agent_module_path():
    """Register serverhub-agent/collectors.py under a unique module name"""
    import importlib.util

    agent_dir = os.path.join(os.path.dirname(__file__), "..", "serverhub-agent")
    spec = importlib.util.spec_from_file_location(
        "serverhub_agent_collectors",
        os.path.join(agent_dir, "collectors.py"),
    )
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules["serverhub_agent_collectors"] = mod
        spec.loader.exec_module(mod)


class TestAgentEndpoints:
    """Test serverhub-agent FastAPI endpoints using TestClient"""

    @pytest.fixture(scope="class")
    def agent_app(self):
        """Create the agent app with a test token"""
        # Set token before importing the agent module
        os.environ["AGENT_TOKEN"] = "test-secret-token"
        os.environ["AGENT_PORT"] = "9901"

        # Import with fresh config
        agent_dir = os.path.join(os.path.dirname(__file__), "..", "serverhub-agent")
        import importlib.util

        # Load config first
        config_spec = importlib.util.spec_from_file_location("agent_config", os.path.join(agent_dir, "config.py"))
        config_mod = importlib.util.module_from_spec(config_spec)
        config_spec.loader.exec_module(config_mod)

        # Load collectors
        coll_spec = importlib.util.spec_from_file_location("agent_collectors", os.path.join(agent_dir, "collectors.py"))
        coll_mod = importlib.util.module_from_spec(coll_spec)
        coll_spec.loader.exec_module(coll_mod)

        # Load main with patched imports
        with patch.dict(sys.modules, {"config": config_mod, "collectors": coll_mod}):
            main_spec = importlib.util.spec_from_file_location("agent_main", os.path.join(agent_dir, "main.py"))
            main_mod = importlib.util.module_from_spec(main_spec)
            main_spec.loader.exec_module(main_mod)

        return main_mod.app

    def test_health_endpoint(self, agent_app):
        from fastapi.testclient import TestClient

        with TestClient(agent_app) as client:
            resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "hostname" in data

    def test_metrics_no_auth(self, agent_app):
        from fastapi.testclient import TestClient

        with TestClient(agent_app) as client:
            resp = client.get("/metrics")
        assert resp.status_code in (401, 403, 422)

    def test_metrics_with_auth(self, agent_app):
        from fastapi.testclient import TestClient

        with TestClient(agent_app) as client:
            resp = client.get(
                "/metrics",
                headers={"Authorization": "Bearer test-secret-token"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert "cpu" in data
        assert "memory" in data


# ═══════════════════════════════════════════════════════════════════════════
# 7. Route Integration Tests (async)
# ═══════════════════════════════════════════════════════════════════════════


class TestServerRoutes:
    """Test server module routes via FastAPI TestClient with mocked auth"""

    @pytest_asyncio.fixture
    async def route_client(self, test_db):
        """Create an httpx AsyncClient with mocked authentication.

        We patch get_current_user at the auth.dependencies level so that
        require_role() which internally calls get_current_user will get our mock.
        """
        import httpx
        from fastapi import FastAPI

        from modules.servers.routes import router

        app = FastAPI()
        app.include_router(router)

        mock_admin = {"username": "test-admin", "role": "admin"}

        async def mock_get_current_user(request):
            return mock_admin

        # Patch get_current_user which is called by require_role()
        with patch("auth.dependencies.get_current_user", mock_get_current_user):
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                yield client

    async def test_list_servers_endpoint(self, route_client):
        resp = await route_client.get("/api/servers/")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(s["id"] == "local" for s in data)

    async def test_create_server_endpoint(self, route_client):
        resp = await route_client.post(
            "/api/servers/",
            json={
                "name": "route-test-create",
                "ip_address": "10.0.0.90",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert "id" in data

    async def test_groups_not_confused_with_server_id(self, route_client):
        """GET /api/servers/groups should return groups list, not 404 as if 'groups' were a server_id"""
        resp = await route_client.get("/api/servers/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_get_server_endpoint(self, route_client):
        resp = await route_client.get("/api/servers/local")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "local"
        assert data["is_local"] is True

    async def test_get_nonexistent_server(self, route_client):
        resp = await route_client.get("/api/servers/nonexistent-12345")
        assert resp.status_code == 404

    async def test_fleet_overview_endpoint(self, route_client):
        resp = await route_client.get("/api/servers/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "online" in data

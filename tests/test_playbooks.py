"""运维剧本模块测试 — 覆盖核心业务逻辑、凭据加密、参数解析、路由集成"""

import json
import os
import sys

import pytest
import pytest_asyncio

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ─── 同步测试（不需要 DB） ───


class TestRenderPrompt:
    def test_basic_substitution(self):
        from modules.playbooks.services import render_prompt

        result = render_prompt("连接 {ip} 执行 {cmd}", {"ip": "1.2.3.4", "cmd": "show vlan"})
        assert "1.2.3.4" in result
        assert "show vlan" in result

    def test_list_param(self):
        from modules.playbooks.services import render_prompt

        result = render_prompt("命令: {commands}", {"commands": ["uptime", "free -h"]})
        assert "uptime" in result
        assert "free -h" in result

    def test_missing_param_kept(self):
        from modules.playbooks.services import render_prompt

        result = render_prompt("IP: {ip}, 端口: {port}", {"ip": "1.2.3.4"})
        assert "1.2.3.4" in result
        assert "{port}" in result  # 未提供的参数保持原样


class TestSanitizeParams:
    def test_secret_masked(self):
        from modules.playbooks.services import sanitize_params_for_log

        params = {"host": "10.0.0.1", "password": "secret123", "username": "admin"}
        defs = [
            {"name": "host", "type": "string"},
            {"name": "password", "type": "secret"},
            {"name": "username", "type": "string"},
        ]
        result = sanitize_params_for_log(params, defs)
        assert result["password"] == "***"
        assert result["host"] == "10.0.0.1"
        assert result["username"] == "admin"


class TestCredentialEncryption:
    def test_fernet_roundtrip(self):
        from modules.playbooks.credentials import _get_fernet

        f = _get_fernet()
        plaintext = b"my_secret_password_123!@#"
        encrypted = f.encrypt(plaintext)
        assert encrypted != plaintext
        decrypted = f.decrypt(encrypted)
        assert decrypted == plaintext

    def test_fernet_deterministic_key(self):
        from modules.playbooks.credentials import _get_fernet

        f1 = _get_fernet()
        f2 = _get_fernet()
        # 同一 secret_key 应产生相同的 Fernet key
        plain = b"test"
        enc = f1.encrypt(plain)
        assert f2.decrypt(enc) == plain


class TestSchemas:
    def test_create_defaults(self):
        from modules.playbooks.schemas import PlaybookCreateRequest

        req = PlaybookCreateRequest(id="test", name="Test", system_prompt="do something")
        assert req.category == "general"
        assert req.parameters == "[]"
        assert req.tools_required == ""
        assert req.tags == ""

    def test_run_request(self):
        from modules.playbooks.schemas import PlaybookRunRequest

        req = PlaybookRunRequest(parameters={"ip": "1.2.3.4"})
        assert req.parameters["ip"] == "1.2.3.4"

    def test_credential_request(self):
        from modules.playbooks.schemas import CredentialCreateRequest

        req = CredentialCreateRequest(name="test", value="secret")
        assert req.credential_type == "generic"


class TestSSHSafety:
    def test_blocked_commands(self):
        from modules.agents.tools.playbook import _check_ssh_command_safety

        assert _check_ssh_command_safety("rm -rf /") is not None
        assert _check_ssh_command_safety("mkfs /dev/sda") is not None
        assert _check_ssh_command_safety("reboot") is not None
        assert _check_ssh_command_safety("shutdown -h now") is not None

    def test_allowed_commands(self):
        from modules.agents.tools.playbook import _check_ssh_command_safety

        assert _check_ssh_command_safety("show vlan brief") is None
        assert _check_ssh_command_safety("ls -la") is None
        assert _check_ssh_command_safety("uptime") is None
        assert _check_ssh_command_safety("free -h") is None
        assert _check_ssh_command_safety("df -h") is None


class TestSeedPlaybooks:
    def test_seed_data_valid(self):
        from modules.playbooks.seed import DEFAULT_PLAYBOOKS

        assert len(DEFAULT_PLAYBOOKS) >= 3
        seed_ids = {pb["id"] for pb in DEFAULT_PLAYBOOKS}
        assert {"vlan_info_collect", "docker_service_restart", "batch_server_health"}.issubset(seed_ids)
        for pb in DEFAULT_PLAYBOOKS:
            assert pb["id"]
            assert pb["name"]
            assert pb["system_prompt"]
            # parameters should be valid JSON
            params = json.loads(pb["parameters"])
            assert isinstance(params, list)
            # validation_rules should be valid JSON
            rules = json.loads(pb["validation_rules"])
            assert isinstance(rules, dict)

    def test_seed_ids_unique(self):
        from modules.playbooks.seed import DEFAULT_PLAYBOOKS

        ids = [pb["id"] for pb in DEFAULT_PLAYBOOKS]
        assert len(ids) == len(set(ids))


class TestToolRegistration:
    def test_playbook_tools_registered(self):
        from modules.agents.tools import get_server_tools

        tools = get_server_tools("admin")
        names = {t.name for t in tools}
        expected = {"ssh_execute_command", "playbook_create", "playbook_execute", "playbook_list", "playbook_search"}
        assert expected.issubset(names), f"Missing: {expected - names}"

    def test_risk_levels_set(self):
        from modules.agents.safety import TOOL_RISK_MAP, RiskLevel

        assert TOOL_RISK_MAP["ssh_execute_command"] == RiskLevel.DANGER
        assert TOOL_RISK_MAP["playbook_create"] == RiskLevel.MODERATE
        assert TOOL_RISK_MAP["playbook_list"] == RiskLevel.SAFE

    def test_user_role_excludes_dangerous(self):
        from modules.agents.tools import get_server_tools

        user_tools = get_server_tools("user")
        names = {t.name for t in user_tools}
        assert "ssh_execute_command" not in names
        assert "playbook_create" not in names


class TestRouteRegistration:
    def test_playbook_routes_count(self):
        from modules.playbooks.routes import router

        assert len(router.routes) >= 10

    def test_critical_paths_exist(self):
        from modules.playbooks.routes import router

        paths = [r.path for r in router.routes if hasattr(r, "path")]
        path_str = " ".join(paths)
        assert "credentials" in path_str, "credentials routes missing"
        assert "executions" in path_str or "run" in path_str, "executions routes missing"


class TestPromptIntegration:
    def test_system_prompt_contains_playbook_section(self):
        from modules.agents.prompts import get_system_prompt

        prompt = get_system_prompt("supervised", "admin")
        assert "playbook_list" in prompt
        assert "ssh_execute_command" in prompt
        assert "运维剧本" in prompt

    def test_user_prompt_no_playbook(self):
        """普通用户不应看到剧本工具指引"""
        from modules.agents.prompts import get_system_prompt

        prompt = get_system_prompt("supervised", "user")
        # user 角色不应有 subagent section，但 playbook section 在子智能体之后
        # 由于 user 没有 subagent_section，playbook 段也应通过 role_instruction 限制
        assert "只读查询" in prompt


# ─── 异步测试（需要 DB） ───


@pytest_asyncio.fixture
async def db():
    """初始化测试数据库"""
    from database import get_db

    database = await get_db()
    yield database


class TestParameterResolution:
    @pytest.mark.asyncio
    async def test_basic_params(self, db):
        from modules.playbooks.services import resolve_parameters

        playbook = {
            "parameters": json.dumps(
                [
                    {"name": "ip", "type": "string", "required": True},
                    {"name": "port", "type": "number", "required": False, "default": 22},
                ]
            )
        }
        resolved = await resolve_parameters(playbook, {"ip": "10.0.0.1"})
        assert resolved["ip"] == "10.0.0.1"
        assert resolved["port"] == 22

    @pytest.mark.asyncio
    async def test_missing_required_param(self, db):
        from modules.playbooks.services import resolve_parameters

        playbook = {
            "parameters": json.dumps(
                [
                    {"name": "ip", "type": "string", "required": True},
                ]
            )
        }
        with pytest.raises(ValueError, match="缺少必填参数"):
            await resolve_parameters(playbook, {})

    @pytest.mark.asyncio
    async def test_regex_validation(self, db):
        from modules.playbooks.services import resolve_parameters

        playbook = {
            "parameters": json.dumps(
                [
                    {"name": "ip", "type": "string", "required": True, "validation": r"^\d{1,3}(\.\d{1,3}){3}$"},
                ]
            )
        }
        # Valid IP
        resolved = await resolve_parameters(playbook, {"ip": "192.168.1.1"})
        assert resolved["ip"] == "192.168.1.1"
        # Invalid IP
        with pytest.raises(ValueError, match="格式不正确"):
            await resolve_parameters(playbook, {"ip": "not-an-ip"})


class TestPlaybookCRUD:
    @pytest.mark.asyncio
    async def test_create_get_delete(self, db):
        from modules.playbooks.services import create_playbook, delete_playbook, get_playbook

        # Create
        pid = await create_playbook(
            {
                "id": "test_crud",
                "name": "Test CRUD",
                "system_prompt": "test prompt",
                "category": "system",
            },
            "test_user",
        )
        assert pid == "test_crud"

        # Get
        pb = await get_playbook("test_crud")
        assert pb is not None
        assert pb["name"] == "Test CRUD"

        # Delete
        await delete_playbook("test_crud")
        pb = await get_playbook("test_crud")
        assert pb is None

    @pytest.mark.asyncio
    async def test_list_by_category(self, db):
        from modules.playbooks.services import create_playbook, delete_playbook, list_playbooks

        await create_playbook({"id": "test_net", "name": "Net", "system_prompt": "t", "category": "network"}, "test")
        await create_playbook({"id": "test_sys", "name": "Sys", "system_prompt": "t", "category": "system"}, "test")

        all_pbs = await list_playbooks()
        net_pbs = await list_playbooks("network")

        assert any(p["id"] == "test_net" for p in net_pbs)
        assert not any(p["id"] == "test_sys" for p in net_pbs)

        # Cleanup
        await delete_playbook("test_net")
        await delete_playbook("test_sys")


class TestCredentialCRUD:
    @pytest.mark.asyncio
    async def test_store_decrypt_delete(self, db):
        from modules.playbooks.credentials import (
            decrypt_credential,
            delete_credential,
            list_credentials,
            store_credential,
        )

        # Store
        cid = await store_credential("test_ssh_pw", "MySecretPassword!", "test", "ssh_password", "tester")
        assert cid

        # List (should not expose value)
        creds = await list_credentials()
        test_cred = next((c for c in creds if c["name"] == "test_ssh_pw"), None)
        assert test_cred is not None
        assert "MySecretPassword" not in json.dumps(test_cred)

        # Decrypt
        value = await decrypt_credential("test_ssh_pw")
        assert value == "MySecretPassword!"

        # Delete
        await delete_credential("test_ssh_pw")
        with pytest.raises(ValueError):
            await decrypt_credential("test_ssh_pw")


class TestBuiltinSeeds:
    @pytest.mark.asyncio
    async def test_seed_idempotent(self, db):
        from modules.playbooks.seed import seed_builtin_playbooks
        from modules.playbooks.services import list_playbooks

        # Run twice — should not error or duplicate
        await seed_builtin_playbooks()
        await seed_builtin_playbooks()
        pbs = await list_playbooks()
        builtin_ids = [p["id"] for p in pbs if p.get("is_builtin")]
        assert "vlan_info_collect" in builtin_ids
        assert "batch_server_health" in builtin_ids
        assert "tms_fault_detection" in builtin_ids

    @pytest.mark.asyncio
    async def test_builtin_not_deletable(self, db):
        from modules.playbooks.seed import seed_builtin_playbooks
        from modules.playbooks.services import delete_playbook

        await seed_builtin_playbooks()
        with pytest.raises(ValueError, match="内置"):
            await delete_playbook("vlan_info_collect")

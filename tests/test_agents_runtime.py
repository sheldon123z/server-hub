import asyncio
import io
import json
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

import aiosqlite
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from langchain_core.messages import AIMessage, ToolMessage


@pytest_asyncio.fixture
async def test_db(tmp_path, monkeypatch):
    import database
    from modules.agents import skill_service

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    database._db = db
    await database.init_tables(db)

    monkeypatch.setattr(skill_service, "SKILLS_ROOT", tmp_path / "builtin-skills")
    monkeypatch.setattr(skill_service, "INSTALLED_SKILLS_ROOT", tmp_path / "installed-skills")
    monkeypatch.setattr(skill_service, "SKILL_SOURCE_FILE", tmp_path / "skill-source-roots.json")

    yield db

    await db.close()
    database._db = None


@pytest_asyncio.fixture
async def admin_client(test_db):
    import auth.dependencies as auth_deps
    from modules.agents.routes.approvals import router as approvals_router
    from modules.agents.routes.chat import router as chat_router
    from modules.agents.routes.conversations import router as conversations_router
    from modules.agents.routes.runs import router as runs_router
    from modules.agents.routes.skills import router as skills_router

    app = FastAPI()
    for router in (chat_router, approvals_router, conversations_router, runs_router, skills_router):
        app.include_router(router, prefix="/api/agents")

    async def mock_get_current_user(request: Request):
        return {"username": "admin", "role": "admin"}

    app.dependency_overrides[auth_deps.get_current_user] = mock_get_current_user
    with patch("auth.dependencies.get_current_user", mock_get_current_user):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest_asyncio.fixture
async def user_client(test_db):
    import auth.dependencies as auth_deps
    from modules.agents.routes.approvals import router as approvals_router
    from modules.agents.routes.chat import router as chat_router
    from modules.agents.routes.conversations import router as conversations_router
    from modules.agents.routes.runs import router as runs_router
    from modules.agents.routes.skills import router as skills_router

    app = FastAPI()
    for router in (chat_router, approvals_router, conversations_router, runs_router, skills_router):
        app.include_router(router, prefix="/api/agents")

    async def mock_get_current_user(request: Request):
        return {"username": "alice", "role": "user"}

    app.dependency_overrides[auth_deps.get_current_user] = mock_get_current_user
    with patch("auth.dependencies.get_current_user", mock_get_current_user):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


def _build_skill_dir(root, *, skill_id="incident-local", name="Incident Local", roles=None):
    skill_dir = root / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "skill.yaml").write_text(
        "\n".join(
            [
                f"id: {skill_id}",
                f"name: {name}",
                "version: 1.0.0",
                "summary: Handle dashboard incidents",
                "triggers:",
                "  keywords:",
                "    - incident",
                "    - alert",
                "  page_contexts:",
                "    - dashboard",
                "allowed_roles:",
                *(f"  - {role}" for role in (roles or ["admin", "user"])),
                "entrypoints:",
                "  type: prompt",
            ]
        ),
        encoding="utf-8",
    )
    (skill_dir / "SKILL.md").write_text("# Incident Local\n\nUse this skill for incident response.\n", encoding="utf-8")
    return skill_dir


async def _collect_sse_events(client: httpx.AsyncClient, payload: dict) -> list[tuple[str, dict]]:
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit_event = asyncio.Event()
    events: list[tuple[str, dict]] = []
    async with client.stream("POST", "/api/agents/chat", json=payload) as response:
        assert response.status_code == 200
        current_event = ""
        async for line in response.aiter_lines():
            if not line:
                current_event = ""
                continue
            if line.startswith("event:"):
                current_event = line.split(":", 1)[1].strip()
                continue
            if not line.startswith("data:"):
                continue
            data = json.loads(line.split(":", 1)[1].strip())
            events.append((current_event, data))
    return events


class FakeStreamingAgent:
    def __init__(self):
        self._final_state = False

    async def aget_state(self, config):
        return SimpleNamespace(values={"messages": [], "todos": []}, next=[], tasks=[])

    async def astream(self, input_state, config, stream_mode="values"):
        yield {"todos": [{"content": "collect metrics", "status": "in_progress"}], "messages": []}
        ai_tool = AIMessage(
            content="",
            tool_calls=[{"name": "get_system_overview", "args": {"scope": "current"}, "id": "tool-1"}],
        )
        tool = ToolMessage(content="cpu ok", tool_call_id="tool-1", name="get_system_overview")
        ai_final = AIMessage(content="诊断完成")
        yield {
            "todos": [{"content": "collect metrics", "status": "completed"}],
            "messages": [ai_tool, tool, ai_final],
        }
        self._final_state = True


class FakeInterruptAgent:
    def __init__(self):
        self._calls = 0

    async def aget_state(self, config):
        self._calls += 1
        if self._calls == 1:
            return SimpleNamespace(values={"messages": [], "todos": []}, next=[], tasks=[])
        return SimpleNamespace(
            values={"messages": [], "todos": []},
            next=["approval"],
            tasks=[
                SimpleNamespace(
                    interrupts=[
                        SimpleNamespace(
                            value={
                                "action_requests": [{"name": "restart_service", "args": {"service": "nginx"}}],
                                "review_configs": [{"action": "approve"}],
                            }
                        )
                    ]
                )
            ],
        )

    async def astream(self, input_state, config, stream_mode="values"):
        if False:
            yield {}


class FakeResumeAgent:
    async def ainvoke(self, command, config):
        return {"messages": [AIMessage(content="审批已通过，服务重启完成")]}


class TestRunLifecycle:
    async def test_create_and_cancel_run(self, admin_client):
        response = await admin_client.post(
            "/api/agents/runs",
            json={"message": "检查 dashboard 异常", "page_context": "dashboard"},
        )
        assert response.status_code == 200
        payload = response.json()
        run_id = payload["run_id"]
        conversation_id = payload["conversation_id"]

        run_response = await admin_client.get(f"/api/agents/runs/{run_id}")
        assert run_response.status_code == 200
        assert run_response.json()["conversation_id"] == conversation_id
        assert run_response.json()["status"] == "running"

        cancel_response = await admin_client.post(f"/api/agents/runs/{run_id}/cancel", json={"reason": "用户取消"})
        assert cancel_response.status_code == 200

        run_response = await admin_client.get(f"/api/agents/runs/{run_id}")
        assert run_response.json()["status"] == "cancel_requested"
        assert run_response.json()["error"] == "用户取消"

    async def test_chat_sse_persists_run_events_and_conversation_summary(self, admin_client):
        fake_agent = FakeStreamingAgent()
        with patch("modules.agents.deep_agent.build_agent", return_value=fake_agent):
            events = await _collect_sse_events(
                admin_client,
                {
                    "message": "请帮我分析告警",
                    "page_context": "dashboard",
                },
            )

        event_names = [name for name, _ in events]
        assert "run.started" in event_names
        assert "todo.update" in event_names
        assert "tool.call" in event_names
        assert "tool.result" in event_names
        assert "message.final" in event_names
        assert "run.completed" in event_names
        assert event_names.index("tool.call") < event_names.index("tool.result") < event_names.index("message.final")

        started_payload = next(payload for event, payload in events if event == "run.started")
        run_id = started_payload["run_id"]
        conversation_id = started_payload["conversation_id"]

        events_response = await admin_client.get(f"/api/agents/runs/{run_id}/events")
        assert events_response.status_code == 200
        persisted = events_response.json()["events"]
        persisted_types = [item["event_type"] for item in persisted]
        assert "tool.call" in persisted_types
        assert "message.final" in persisted_types

        conversation_response = await admin_client.get(f"/api/agents/conversations/{conversation_id}")
        assert conversation_response.status_code == 200
        conversation = conversation_response.json()
        assert conversation["latest_run_summary"]["id"] == run_id
        assert any(item["role"] == "assistant" and "诊断完成" in item["content"] for item in conversation["messages"])
        assert conversation["todos"][0]["status"] == "completed"

    async def test_approval_resume_updates_run_status(self, admin_client):
        with patch(
            "modules.agents.deep_agent.build_agent",
            side_effect=[FakeInterruptAgent(), FakeResumeAgent()],
        ):
            events = await _collect_sse_events(
                admin_client,
                {
                    "message": "重启 nginx",
                    "page_context": "services",
                },
            )

            approval_payload = next(payload for event, payload in events if event == "approval.request")
            run_id = approval_payload["run_id"]
            approval_id = approval_payload["approval_id"]

            approval_response = await admin_client.post(
                f"/api/agents/approvals/{approval_id}",
                json={"action": "approve", "reason": ""},
            )
            assert approval_response.status_code == 200
            assert approval_response.json()["ok"] is True
            assert "重启完成" in approval_response.json()["result"]

        run_response = await admin_client.get(f"/api/agents/runs/{run_id}")
        assert run_response.status_code == 200
        assert run_response.json()["status"] == "completed"

        events_response = await admin_client.get(f"/api/agents/runs/{run_id}/events")
        persisted_types = [item["event_type"] for item in events_response.json()["events"]]
        assert "approval.request" in persisted_types
        assert persisted_types[-2:] == ["message.final", "run.completed"]


class TestSkillSystem:
    async def test_skill_discovery_install_recommend_and_upload_guard(self, test_db, tmp_path):
        from modules.agents.skill_service import (
            discover_skills,
            install_skill_from_repo,
            install_skill_from_upload,
            recommend_skills,
            save_skill_sources,
        )

        repo_root = tmp_path / "skill-repo"
        repo_root.mkdir()
        skill_dir = _build_skill_dir(repo_root)

        save_skill_sources([str(repo_root)])
        discovered = await discover_skills()
        assert len(discovered) == 1
        assert discovered[0]["manifest"]["id"] == "incident-local"
        assert discovered[0]["installed"] is False

        installed = await install_skill_from_repo(str(skill_dir), created_by="admin")
        assert installed["id"] == "incident-local"
        assert installed["enabled"] is True

        recommendations = await recommend_skills(
            message="incident on dashboard needs alert triage",
            page_context="dashboard",
            user_role="user",
        )
        assert recommendations
        assert recommendations[0]["id"] == "incident-local"

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("../evil.txt", "boom")
        with pytest.raises(ValueError, match="非法路径"):
            await install_skill_from_upload("bad-skill.zip", buffer.getvalue(), created_by="admin")

    async def test_skill_admin_routes_forbid_user(self, user_client):
        forbidden = await user_client.get("/api/agents/admin/skills")
        assert forbidden.status_code == 403

    async def test_skill_admin_routes_install_toggle(self, admin_client, tmp_path):
        repo_root = tmp_path / "repo-skills"
        repo_root.mkdir()
        skill_dir = _build_skill_dir(repo_root, skill_id="fleet-local", name="Fleet Local")

        save_sources = await admin_client.put(
            "/api/agents/admin/skill-sources",
            json={"roots": [str(repo_root)]},
        )
        assert save_sources.status_code == 200
        assert str(repo_root) in save_sources.json()["roots"]

        discover_response = await admin_client.post("/api/agents/admin/skills/discover")
        assert discover_response.status_code == 200
        assert discover_response.json()["items"][0]["manifest"]["id"] == "fleet-local"

        install_response = await admin_client.post(
            "/api/agents/admin/skills/install-from-repo",
            json={"repo_path": str(skill_dir)},
        )
        assert install_response.status_code == 200
        assert install_response.json()["skill"]["id"] == "fleet-local"

        disable_response = await admin_client.post("/api/agents/admin/skills/fleet-local/disable")
        assert disable_response.status_code == 200
        enable_response = await admin_client.post("/api/agents/admin/skills/fleet-local/enable")
        assert enable_response.status_code == 200

        list_response = await admin_client.get("/api/agents/admin/skills")
        assert list_response.status_code == 200
        assert list_response.json()["skills"][0]["id"] == "fleet-local"

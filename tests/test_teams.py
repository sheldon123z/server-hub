"""智能体团队模块测试 — CRUD、模板 seed、引擎构建、状态合并"""

import os
import sys
from unittest.mock import MagicMock, patch

import aiosqlite
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

pytestmark = pytest.mark.asyncio(loop_scope="session")


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest_asyncio.fixture(scope="session")
async def teams_db():
    """初始化内存数据库"""
    import database

    db = await aiosqlite.connect(":memory:")
    db.row_factory = aiosqlite.Row
    database._db = db
    await database.init_tables(db)
    yield db
    await db.close()
    database._db = None


# ═══════════════════════════════════════════════════════════════════════════
# 1. TeamStore CRUD 测试
# ═══════════════════════════════════════════════════════════════════════════


class TestTeamCRUD:
    async def test_create_team(self, teams_db):
        """创建团队并验证返回记录"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        team = await store.create_team(
            {
                "name": "测试团队A",
                "description": "用于单元测试",
                "topology": "supervisor",
                "config": {"output_mode": "full_history"},
                "safety_mode": "supervised",
                "max_steps": 30,
                "timeout_seconds": 120,
                "created_by": "test",
            }
        )
        assert team is not None
        assert team["name"] == "测试团队A"
        assert team["topology"] == "supervisor"
        assert team["safety_mode"] == "supervised"
        assert team["max_steps"] == 30
        assert team["enabled"] == 1

    async def test_get_team(self, teams_db):
        """获取已创建团队"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team_a = next((t for t in teams if t["name"] == "测试团队A"), None)
        assert team_a is not None

        fetched = await store.get_team(team_a["id"])
        assert fetched is not None
        assert fetched["name"] == "测试团队A"

    async def test_get_nonexistent_team(self, teams_db):
        """获取不存在的团队返回 None"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        result = await store.get_team("nonexistent-id")
        assert result is None

    async def test_list_teams(self, teams_db):
        """列出所有团队"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        assert len(teams) >= 1
        names = [t["name"] for t in teams]
        assert "测试团队A" in names

    async def test_update_team(self, teams_db):
        """更新团队字段"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team_a = next(t for t in teams if t["name"] == "测试团队A")

        updated = await store.update_team(team_a["id"], {"name": "测试团队A-改名", "max_steps": 60})
        assert updated is not None
        assert updated["name"] == "测试团队A-改名"
        assert updated["max_steps"] == 60

        # 还原名称
        await store.update_team(team_a["id"], {"name": "测试团队A"})

    async def test_update_team_empty(self, teams_db):
        """空更新不报错"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team_a = next(t for t in teams if t["name"] == "测试团队A")
        result = await store.update_team(team_a["id"], {})
        assert result is not None

    async def test_delete_team(self, teams_db):
        """删除非内置团队"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        team = await store.create_team({"name": "待删除团队", "topology": "pipeline", "created_by": "test"})
        assert await store.get_team(team["id"]) is not None

        deleted = await store.delete_team(team["id"])
        assert deleted is True
        assert await store.get_team(team["id"]) is None

    async def test_delete_builtin_team_fails(self, teams_db):
        """内置团队不可通过 delete_team 删除"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        team = await store.create_team(
            {"name": "内置团队测试", "topology": "supervisor", "is_builtin": 1, "created_by": "system"}
        )

        deleted = await store.delete_team(team["id"])
        assert deleted is False
        assert await store.get_team(team["id"]) is not None


# ═══════════════════════════════════════════════════════════════════════════
# 2. Member CRUD 测试
# ═══════════════════════════════════════════════════════════════════════════


class TestMemberCRUD:
    async def test_add_member(self, teams_db):
        """添加团队成员"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team_a = next(t for t in teams if t["name"] == "测试团队A")

        member = await store.add_member(
            team_a["id"],
            {
                "name": "组长",
                "agent_type": "leader",
                "system_prompt": "你是组长",
                "tools": ["get_system_overview"],
                "position": 0,
            },
        )
        assert member["name"] == "组长"
        assert member["team_id"] == team_a["id"]

    async def test_add_worker_member(self, teams_db):
        """添加 worker 成员"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team_a = next(t for t in teams if t["name"] == "测试团队A")

        member = await store.add_member(
            team_a["id"],
            {
                "name": "分析员",
                "agent_type": "worker",
                "system_prompt": "你是分析员",
                "tools": ["check_compliance"],
                "position": 1,
            },
        )
        assert member["name"] == "分析员"

    async def test_get_members(self, teams_db):
        """获取团队所有成员"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team_a = next(t for t in teams if t["name"] == "测试团队A")

        members = await store.get_members(team_a["id"])
        assert len(members) >= 2
        names = [m["name"] for m in members]
        assert "组长" in names
        assert "分析员" in names

    async def test_update_member(self, teams_db):
        """更新成员字段"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team_a = next(t for t in teams if t["name"] == "测试团队A")
        members = await store.get_members(team_a["id"])
        worker = next(m for m in members if m["name"] == "分析员")

        updated = await store.update_member(worker["id"], {"description": "深度分析专家"})
        assert updated is not None
        assert updated["description"] == "深度分析专家"

    async def test_remove_member(self, teams_db):
        """移除成员"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        team = await store.create_team({"name": "成员删除测试团队", "topology": "pipeline", "created_by": "test"})
        member = await store.add_member(team["id"], {"name": "临时成员", "system_prompt": "测试"})
        removed = await store.remove_member(member["id"])
        assert removed is True

        members = await store.get_members(team["id"])
        assert not any(m["name"] == "临时成员" for m in members)


# ═══════════════════════════════════════════════════════════════════════════
# 3. 模板系统测试
# ═══════════════════════════════════════════════════════════════════════════


class TestTemplates:
    def test_template_list_completeness(self):
        """模板列表包含所有 5 个内置模板"""
        from modules.agents.teams.templates import BUILTIN_TEMPLATES, get_template_list

        assert len(BUILTIN_TEMPLATES) == 5
        summaries = get_template_list()
        assert len(summaries) == 5
        topologies = {t["topology"] for t in summaries}
        assert "supervisor" in topologies
        assert "swarm" in topologies
        assert "pipeline" in topologies

    def test_template_by_id(self):
        """根据 ID 获取模板"""
        from modules.agents.teams.templates import get_template_by_id

        tmpl = get_template_by_id("tpl-security-audit")
        assert tmpl is not None
        assert tmpl["topology"] == "supervisor"
        assert len(tmpl["members"]) == 4

        assert get_template_by_id("nonexistent") is None

    def test_template_members_have_required_fields(self):
        """每个模板成员都有必填字段"""
        from modules.agents.teams.templates import BUILTIN_TEMPLATES

        for tmpl in BUILTIN_TEMPLATES:
            for member in tmpl["members"]:
                assert "name" in member, f"模板 {tmpl['id']} 成员缺少 name"
                assert "system_prompt" in member, f"模板 {tmpl['id']} 成员 {member['name']} 缺少 system_prompt"

    def test_template_ids_unique(self):
        """模板 ID 唯一"""
        from modules.agents.teams.templates import BUILTIN_TEMPLATES

        ids = [t["id"] for t in BUILTIN_TEMPLATES]
        assert len(ids) == len(set(ids))

    async def test_seed_builtin_teams_idempotent(self, teams_db):
        """seed_builtin_teams 幂等执行"""
        from modules.agents.teams.store import TeamStore
        from modules.agents.teams.templates import seed_builtin_teams

        await seed_builtin_teams()
        store = TeamStore()
        teams_after_first = await store.list_teams()
        builtin_count_1 = sum(1 for t in teams_after_first if t.get("is_builtin"))

        # 再次执行不应产生新记录
        await seed_builtin_teams()
        teams_after_second = await store.list_teams()
        builtin_count_2 = sum(1 for t in teams_after_second if t.get("is_builtin"))

        assert builtin_count_1 == builtin_count_2
        assert builtin_count_1 >= 5


# ═══════════════════════════════════════════════════════════════════════════
# 4. TeamState 测试
# ═══════════════════════════════════════════════════════════════════════════


class TestTeamState:
    def test_merge_dicts_reducer(self):
        """agent_outputs 字典合并 reducer"""
        from modules.agents.teams.state import _merge_dicts

        a = {"agent1": "output1"}
        b = {"agent2": "output2"}
        merged = _merge_dicts(a, b)
        assert merged == {"agent1": "output1", "agent2": "output2"}

    def test_merge_dicts_overwrite(self):
        """同名 key 后者覆盖前者"""
        from modules.agents.teams.state import _merge_dicts

        a = {"agent1": "old"}
        b = {"agent1": "new"}
        merged = _merge_dicts(a, b)
        assert merged["agent1"] == "new"


# ═══════════════════════════════════════════════════════════════════════════
# 5. TeamEngine 测试（Mock LLM）
# ═══════════════════════════════════════════════════════════════════════════


class TestTeamEngine:
    async def test_build_graph_nonexistent_team(self, teams_db):
        """构建不存在团队的图抛出 ValueError"""
        from modules.agents.teams.engine import TeamEngine
        from modules.agents.teams.store import TeamStore

        engine = TeamEngine(store=TeamStore())
        with pytest.raises(ValueError, match="不存在"):
            await engine.build_team_graph("nonexistent-team-id")

    async def test_build_graph_no_members(self, teams_db):
        """无成员团队构建图抛出 ValueError"""
        from modules.agents.teams.engine import TeamEngine
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        team = await store.create_team({"name": "空成员团队", "topology": "supervisor", "created_by": "test"})

        engine = TeamEngine(store=store)
        with pytest.raises(ValueError, match="无成员"):
            await engine.build_team_graph(team["id"])

    async def test_build_supervisor_needs_workers(self, teams_db):
        """Supervisor 拓扑至少需要 1 个 worker"""
        from modules.agents.teams.engine import TeamEngine
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        team = await store.create_team({"name": "单Leader团队", "topology": "supervisor", "created_by": "test"})
        await store.add_member(
            team["id"],
            {"name": "唯一Leader", "agent_type": "leader", "system_prompt": "test"},
        )

        engine = TeamEngine(store=store)
        # mock LLM 避免真实调用
        mock_model = MagicMock()
        with patch("modules.agents.teams.engine._get_chat_model_by_id", return_value=mock_model):
            with pytest.raises(ValueError, match="worker"):
                await engine.build_team_graph(team["id"])

    async def test_build_pipeline_graph(self, teams_db):
        """Pipeline 拓扑按 position 排序构建"""
        from modules.agents.teams.engine import TeamEngine
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        team = await store.create_team({"name": "Pipeline测试", "topology": "pipeline", "created_by": "test"})
        await store.add_member(
            team["id"],
            {"name": "Stage2", "system_prompt": "second", "position": 2},
        )
        await store.add_member(
            team["id"],
            {"name": "Stage1", "system_prompt": "first", "position": 1},
        )

        engine = TeamEngine(store=store)

        # mock create_react_agent 和 model
        mock_model = MagicMock()
        mock_agent = MagicMock()
        with patch("modules.agents.teams.engine._get_chat_model_by_id", return_value=mock_model):
            with patch("modules.agents.teams.engine._resolve_tools_safe", return_value=[]):
                with patch("modules.agents.teams.engine._wrap_tools_safe", return_value=[]):
                    with patch("langgraph.prebuilt.create_react_agent", return_value=mock_agent):
                        graph = await engine.build_team_graph(team["id"])

        assert graph is not None

    async def test_cache_invalidation(self, teams_db):
        """图缓存可清除"""
        from modules.agents.teams.engine import TeamEngine
        from modules.agents.teams.store import TeamStore

        engine = TeamEngine(store=TeamStore())
        engine._graph_cache["test-id"] = ("fake_graph", "2024-01-01")
        assert "test-id" in engine._graph_cache

        engine.invalidate_cache("test-id")
        assert "test-id" not in engine._graph_cache

    async def test_invalidate_all_cache(self, teams_db):
        """清除所有缓存"""
        from modules.agents.teams.engine import TeamEngine
        from modules.agents.teams.store import TeamStore

        engine = TeamEngine(store=TeamStore())
        engine._graph_cache["a"] = ("g1", "t1")
        engine._graph_cache["b"] = ("g2", "t2")

        engine.invalidate_all_cache()
        assert len(engine._graph_cache) == 0

    async def test_summarize_outputs(self, teams_db):
        """输出汇总为 Markdown"""
        from modules.agents.teams.engine import TeamEngine

        result = TeamEngine._summarize_outputs(
            {"Agent1": "分析完成", "Agent2": "报告已生成"},
            "pipeline",
        )
        assert "Agent1" in result
        assert "Agent2" in result
        assert "pipeline" in result

    async def test_summarize_empty_outputs(self, teams_db):
        """空输出汇总"""
        from modules.agents.teams.engine import TeamEngine

        result = TeamEngine._summarize_outputs({}, "supervisor")
        assert "未产生输出" in result


# ═══════════════════════════════════════════════════════════════════════════
# 6. 执行记录测试
# ═══════════════════════════════════════════════════════════════════════════


class TestExecutionRecords:
    async def test_create_and_get_execution(self, teams_db):
        """创建和获取执行记录"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team = teams[0]

        execution = await store.create_execution(team["id"], "测试指令", "testuser", "supervisor")
        assert execution["id"]
        assert execution["instruction"] == "测试指令"

        fetched = await store.get_execution(execution["id"])
        assert fetched is not None
        assert fetched["status"] == "running"

    async def test_complete_execution(self, teams_db):
        """完成执行记录"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team = teams[0]

        execution = await store.create_execution(team["id"], "测试", "testuser", "pipeline")
        await store.complete_execution(
            execution["id"],
            status="success",
            result="执行成功",
            agent_outputs={"agent1": "output1"},
            duration=10.5,
            steps=5,
        )
        fetched = await store.get_execution(execution["id"])
        assert fetched["status"] == "success"
        assert fetched["result"] == "执行成功"

    async def test_list_executions(self, teams_db):
        """列出执行历史"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        executions = await store.list_executions(limit=50)
        assert len(executions) >= 2

    async def test_log_and_get_messages(self, teams_db):
        """记录和获取消息流"""
        from modules.agents.teams.store import TeamStore

        store = TeamStore()
        teams = await store.list_teams()
        team = teams[0]

        execution = await store.create_execution(team["id"], "消息测试", "testuser", "swarm")

        await store.log_message(execution["id"], "Agent1", None, "status", "开始工作")
        await store.log_message(execution["id"], "Agent1", "Agent2", "handoff", "移交任务")
        await store.flush_messages()

        messages = await store.get_messages(execution["id"])
        assert len(messages) == 2
        assert messages[0]["from_agent"] == "Agent1"
        assert messages[1]["message_type"] == "handoff"

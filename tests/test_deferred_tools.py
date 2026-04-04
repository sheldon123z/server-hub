"""tests/test_deferred_tools.py — 延迟工具加载单元测试

覆盖:
  - DeferredToolRegistry.register / get_tool_names
  - DeferredToolRegistry.search: select: / +keyword / 模糊匹配
  - DeferredToolRegistry.promote (移除已发现工具)
  - DeferredToolRegistry.get_deferred_tool_descriptions
  - ContextVar 隔离: get/set/reset_deferred_registry
  - tool_search LangChain 工具 — 未初始化/搜索命中/搜索未命中
  - CORE_TOOL_NAMES 集合完整性检查
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from modules.agents.deferred_tools import (
    CORE_TOOL_NAMES,
    DeferredToolRegistry,
    get_deferred_registry,
    reset_deferred_registry,
    set_deferred_registry,
    tool_search,
)

# ── 辅助工具 ─────────────────────────────────────────────────────


def _make_mock_tool(name: str, description: str = "") -> MagicMock:
    """创建带 name/description 属性的假工具对象。"""
    t = MagicMock()
    t.name = name
    t.description = description
    return t


@pytest.fixture
def registry():
    """空的 DeferredToolRegistry。"""
    return DeferredToolRegistry()


@pytest.fixture(autouse=True)
def cleanup_context_var():
    """每个测试后重置 ContextVar，防止状态泄漏。"""
    yield
    reset_deferred_registry()


# ── DeferredToolRegistry 基础操作 ─────────────────────────────────


class TestRegistryBasics:
    def test_empty_registry(self, registry):
        assert registry.get_tool_names() == []

    def test_register_single_tool(self, registry):
        t = _make_mock_tool("get_disk_info")
        registry.register(t)
        assert "get_disk_info" in registry.get_tool_names()

    def test_register_multiple_tools(self, registry):
        names = ["tool_a", "tool_b", "tool_c"]
        for n in names:
            registry.register(_make_mock_tool(n))
        assert set(registry.get_tool_names()) == set(names)

    def test_register_overwrites_same_name(self, registry):
        t1 = _make_mock_tool("dup_tool", description="first")
        t2 = _make_mock_tool("dup_tool", description="second")
        registry.register(t1)
        registry.register(t2)
        # 仅保留一个（最新），key 不重复
        assert registry.get_tool_names().count("dup_tool") == 1
        assert registry._tools["dup_tool"].description == "second"


# ── DeferredToolRegistry.search ───────────────────────────────────


class TestRegistrySearch:
    @pytest.fixture
    def populated_registry(self):
        r = DeferredToolRegistry()
        r.register(_make_mock_tool("list_docker_containers", "列出 Docker 容器"))
        r.register(_make_mock_tool("docker_container_action", "控制 Docker 容器生命周期"))
        r.register(_make_mock_tool("get_system_overview", "获取系统整体状态概览"))
        r.register(_make_mock_tool("manage_linux_user", "管理 Linux 用户账号"))
        return r

    def test_select_exact_names(self, populated_registry):
        """select: 精确选择多个工具。"""
        results = populated_registry.search("select:list_docker_containers,get_system_overview")
        names = [t.name for t in results]
        assert "list_docker_containers" in names
        assert "get_system_overview" in names
        assert "manage_linux_user" not in names

    def test_select_nonexistent_name(self, populated_registry):
        results = populated_registry.search("select:no_such_tool")
        assert results == []

    def test_keyword_prefix_search(self, populated_registry):
        """+keyword 只匹配名称中含 keyword 的工具。"""
        results = populated_registry.search("+docker")
        names = [t.name for t in results]
        assert "list_docker_containers" in names
        assert "docker_container_action" in names
        assert "get_system_overview" not in names

    def test_fuzzy_search_by_name(self, populated_registry):
        """模糊搜索匹配名称片段。"""
        results = populated_registry.search("system")
        assert any(t.name == "get_system_overview" for t in results)

    def test_fuzzy_search_by_description(self, populated_registry):
        """模糊搜索匹配描述内容。"""
        results = populated_registry.search("Linux")
        assert any(t.name == "manage_linux_user" for t in results)

    def test_fuzzy_search_case_insensitive(self, populated_registry):
        results_lower = populated_registry.search("docker")
        results_upper = populated_registry.search("DOCKER")
        assert len(results_lower) == len(results_upper)

    def test_fuzzy_search_max_10_results(self):
        """模糊搜索最多返回 10 条结果。"""
        r = DeferredToolRegistry()
        for i in range(15):
            r.register(_make_mock_tool(f"common_prefix_{i}", f"desc_{i}"))
        results = r.search("common_prefix")
        assert len(results) <= 10

    def test_empty_registry_search_returns_empty(self, registry):
        assert registry.search("anything") == []


# ── DeferredToolRegistry.promote ──────────────────────────────────


class TestRegistryPromote:
    def test_promote_removes_tools(self, registry):
        registry.register(_make_mock_tool("docker_prune"))
        registry.register(_make_mock_tool("get_disk_info"))
        registry.promote({"docker_prune"})
        assert "docker_prune" not in registry.get_tool_names()
        assert "get_disk_info" in registry.get_tool_names()

    def test_promote_nonexistent_no_error(self, registry):
        """promote 不存在的工具名不应抛异常。"""
        registry.promote({"ghost_tool"})

    def test_promote_multiple(self, registry):
        for name in ["t1", "t2", "t3"]:
            registry.register(_make_mock_tool(name))
        registry.promote({"t1", "t2"})
        remaining = registry.get_tool_names()
        assert "t3" in remaining
        assert "t1" not in remaining
        assert "t2" not in remaining


# ── DeferredToolRegistry.get_deferred_tool_descriptions ──────────


class TestGetDeferredToolDescriptions:
    def test_empty_returns_empty_string(self, registry):
        assert registry.get_deferred_tool_descriptions() == ""

    def test_contains_tool_names(self, registry):
        registry.register(_make_mock_tool("list_docker_containers", "列出容器"))
        desc = registry.get_deferred_tool_descriptions()
        assert "list_docker_containers" in desc

    def test_contains_descriptions(self, registry):
        registry.register(_make_mock_tool("my_tool", "这是工具描述"))
        desc = registry.get_deferred_tool_descriptions()
        assert "这是工具描述" in desc

    def test_long_description_truncated(self, registry):
        """描述超过 60 字符时应截断，不会无限延伸。"""
        long_desc = "A" * 200
        registry.register(_make_mock_tool("long_tool", long_desc))
        desc = registry.get_deferred_tool_descriptions()
        # 每行描述不超过 60 字符（按实现截断）
        for line in desc.split("\n"):
            assert len(line) < 150  # 包含 "- name: " 前缀后仍在合理范围内


# ── ContextVar 隔离 ────────────────────────────────────────────────


class TestContextVarIsolation:
    def test_default_is_none(self):
        assert get_deferred_registry() is None

    def test_set_and_get(self):
        r = DeferredToolRegistry()
        set_deferred_registry(r)
        assert get_deferred_registry() is r

    def test_reset_returns_to_none(self):
        r = DeferredToolRegistry()
        set_deferred_registry(r)
        reset_deferred_registry()
        assert get_deferred_registry() is None

    def test_set_replaces_previous(self):
        r1 = DeferredToolRegistry()
        r2 = DeferredToolRegistry()
        set_deferred_registry(r1)
        set_deferred_registry(r2)
        assert get_deferred_registry() is r2


# ── tool_search LangChain 工具 ────────────────────────────────────


class TestToolSearch:
    def test_uninitialized_registry_returns_message(self):
        """注册表未初始化时返回提示消息，不报错。"""
        result = tool_search.invoke({"query": "docker"})
        assert "未初始化" in result or "所有工具已直接可用" in result

    def test_search_no_match_shows_available(self):
        """搜索无结果时展示可用工具列表。"""
        r = DeferredToolRegistry()
        r.register(_make_mock_tool("docker_prune"))
        set_deferred_registry(r)
        result = tool_search.invoke({"query": "xyz_no_match_xyz"})
        assert "docker_prune" in result

    def test_search_match_promotes_tools(self):
        """搜索命中后，工具应被 promote（从注册表移除）。"""
        r = DeferredToolRegistry()
        t = _make_mock_tool("found_tool", "找到这个工具")
        r.register(t)
        set_deferred_registry(r)
        result = tool_search.invoke({"query": "found_tool"})
        assert "found_tool" in result
        # promote 后注册表中不再有该工具
        assert "found_tool" not in r.get_tool_names()

    def test_search_result_contains_tool_info(self):
        """搜索结果应包含工具名和描述。"""
        r = DeferredToolRegistry()
        r.register(_make_mock_tool("check_compliance", "检查系统安全合规状态"))
        set_deferred_registry(r)
        result = tool_search.invoke({"query": "select:check_compliance"})
        assert "check_compliance" in result
        assert "检查系统安全合规状态" in result


# ── CORE_TOOL_NAMES 完整性 ────────────────────────────────────────


class TestCoreToolNames:
    def test_core_tool_names_is_set(self):
        assert isinstance(CORE_TOOL_NAMES, set)

    def test_core_tool_names_not_empty(self):
        assert len(CORE_TOOL_NAMES) > 0

    def test_core_includes_essential_tools(self):
        """几个最高频工具必须在 CORE 集合中。"""
        essential = {"get_system_overview", "list_docker_containers", "list_systemd_services"}
        assert essential.issubset(CORE_TOOL_NAMES), f"缺失必要核心工具: {essential - CORE_TOOL_NAMES}"

    def test_core_tool_names_all_strings(self):
        assert all(isinstance(n, str) for n in CORE_TOOL_NAMES)

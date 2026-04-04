"""tests/test_clarification.py — ask_clarification 工具单元测试"""

import json

import pytest

# ─────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────


@pytest.fixture
def ask_clar():
    from modules.agents.tools.clarification import ask_clarification

    return ask_clarification


# ─────────────────────────────────────────
# 输出格式与结构
# ─────────────────────────────────────────


class TestAskClarificationOutput:
    """验证 ask_clarification 返回有效 JSON 且包含必要字段"""

    def test_returns_json_string(self, ask_clar):
        """工具返回 JSON 字符串，便于 SSE 流传输"""
        result = ask_clar.invoke({"question": "目标服务？", "clarification_type": "missing_info"})
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_clarification_marker(self, ask_clar):
        """返回对象含 _clarification=True，前端依赖此字段区分澄清消息"""
        result = json.loads(ask_clar.invoke({"question": "确认？", "clarification_type": "risk_confirmation"}))
        assert result["_clarification"] is True

    def test_question_preserved(self, ask_clar):
        """question 字段原样保留"""
        q = "请提供目标服务器的 IP 地址"
        result = json.loads(ask_clar.invoke({"question": q, "clarification_type": "missing_info"}))
        assert result["question"] == q

    def test_clarification_type_preserved(self, ask_clar):
        """clarification_type 字段原样保留"""
        result = json.loads(ask_clar.invoke({"question": "选择方案", "clarification_type": "approach_choice"}))
        assert result["clarification_type"] == "approach_choice"

    def test_context_default_empty_string(self, ask_clar):
        """未提供 context 时默认为空字符串"""
        result = json.loads(ask_clar.invoke({"question": "q", "clarification_type": "missing_info"}))
        assert result["context"] == ""

    def test_context_preserved(self, ask_clar):
        """context 字段原样保留"""
        ctx = "当前已有 3 个正在运行的容器"
        result = json.loads(
            ask_clar.invoke({"question": "选择容器", "clarification_type": "ambiguous_requirement", "context": ctx})
        )
        assert result["context"] == ctx

    def test_options_absent_when_not_provided(self, ask_clar):
        """不提供 options 时返回对象中不含 options 键"""
        result = json.loads(ask_clar.invoke({"question": "q", "clarification_type": "missing_info"}))
        assert "options" not in result

    def test_options_included_when_provided(self, ask_clar):
        """提供 options 时正确包含在结果中"""
        opts = ["方案A：滚动更新", "方案B：蓝绿部署", "方案C：金丝雀发布"]
        result = json.loads(
            ask_clar.invoke({"question": "选择发布策略", "clarification_type": "approach_choice", "options": opts})
        )
        assert result["options"] == opts

    def test_empty_options_list_excluded(self, ask_clar):
        """空列表视为未提供，不包含在结果中（因 `if options:` 逻辑）"""
        result = json.loads(ask_clar.invoke({"question": "q", "clarification_type": "missing_info", "options": []}))
        assert "options" not in result

    def test_json_ensure_ascii_false(self, ask_clar):
        """中文字符直接编码，不转为 \\uXXXX 转义"""
        result = ask_clar.invoke({"question": "你好", "clarification_type": "missing_info"})
        assert "你好" in result


# ─────────────────────────────────────────
# 4 种 clarification_type 枚举值
# ─────────────────────────────────────────


class TestClarificationTypes:
    """验证全部 4 种合法 clarification_type 均可正常调用"""

    @pytest.mark.parametrize(
        "ctype",
        ["missing_info", "ambiguous_requirement", "approach_choice", "risk_confirmation"],
    )
    def test_valid_clarification_types(self, ask_clar, ctype):
        result = json.loads(ask_clar.invoke({"question": "test", "clarification_type": ctype}))
        assert result["clarification_type"] == ctype

    def test_missing_info_typical_usage(self, ask_clar):
        """missing_info：缺少执行所需信息的典型场景"""
        result = json.loads(
            ask_clar.invoke(
                {
                    "question": "请提供需要备份的数据库名称",
                    "clarification_type": "missing_info",
                    "context": "执行备份操作需要指定目标数据库",
                }
            )
        )
        assert result["_clarification"] is True
        assert result["clarification_type"] == "missing_info"

    def test_approach_choice_with_options(self, ask_clar):
        """approach_choice：多方案选择时附带 options"""
        result = json.loads(
            ask_clar.invoke(
                {
                    "question": "检测到磁盘空间不足，请选择清理方式",
                    "clarification_type": "approach_choice",
                    "options": ["清理 Docker 镜像缓存", "压缩日志文件", "删除临时文件"],
                }
            )
        )
        assert len(result["options"]) == 3

    def test_risk_confirmation_typical_usage(self, ask_clar):
        """risk_confirmation：高危操作前确认"""
        result = json.loads(
            ask_clar.invoke(
                {
                    "question": "即将重启生产数据库，确认继续？",
                    "clarification_type": "risk_confirmation",
                    "context": "此操作将中断所有在线连接约 30 秒",
                }
            )
        )
        assert result["clarification_type"] == "risk_confirmation"
        assert "重启生产数据库" in result["question"]


# ─────────────────────────────────────────
# 工具元数据
# ─────────────────────────────────────────


class TestToolMetadata:
    """验证工具注册元数据正确"""

    def test_tool_name(self, ask_clar):
        """工具名称为 ask_clarification，LLM 路由依赖此字段"""
        assert ask_clar.name == "ask_clarification"

    def test_tool_has_description(self, ask_clar):
        """工具必须有足够长的描述，供 LLM 决策"""
        assert ask_clar.description
        assert len(ask_clar.description) > 20

    def test_tool_is_callable(self, ask_clar):
        """工具对象具有 invoke 方法"""
        assert callable(ask_clar.invoke)


# ─────────────────────────────────────────
# 模块导入与注册表
# ─────────────────────────────────────────


class TestModuleImport:
    """验证模块可正确导入，无循环依赖"""

    def test_module_importable(self):
        import importlib

        mod = importlib.import_module("modules.agents.tools.clarification")
        assert hasattr(mod, "ask_clarification")

    def test_tool_importable_from_package(self):
        from modules.agents.tools.clarification import ask_clarification

        assert ask_clarification is not None

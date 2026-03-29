"""团队编排引擎 — 构建 LangGraph 图并管理执行生命周期

支持三种拓扑:
- Supervisor: 组长通过 handoff 调度 worker
- Swarm: 成员间自主 handoff 协作
- Pipeline: 按 position 顺序流水线执行
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage

from config import settings
from modules.agents.teams.state import TeamState

logger = logging.getLogger(__name__)


# ─── 延迟导入辅助 ───


def _get_chat_model_by_id(model_id: str | None = None):
    """获取指定 model_id 的 ChatOpenAI 实例，兼容 get_chat_model_by_id 尚未添加的情况"""
    try:
        from modules.agents.llm import get_chat_model_by_id

        return get_chat_model_by_id(model_id)
    except ImportError:
        import os

        from modules.agents.llm import PROVIDERS, ChatOpenAI, get_chat_model, parse_model_id

        if not model_id:
            return get_chat_model("chat")
        provider_key, model_name = parse_model_id(model_id)
        provider = PROVIDERS.get(provider_key)
        if not provider:
            logger.warning("未知供应商 %s, 回退到默认模型", provider_key)
            return get_chat_model("chat")
        api_key_env = provider.get("api_key_env", "")
        api_key = os.getenv(api_key_env, "") if api_key_env else "not-needed"
        return ChatOpenAI(
            model=model_name,
            base_url=provider["base_url"],
            api_key=api_key or "not-needed",
            temperature=0.3,
            max_tokens=4096,
            streaming=True,
        )


def _resolve_tools_safe(tool_names: list[str], user_role: str = "admin") -> list:
    """解析工具名列表为实际 Tool 对象，容错处理"""
    try:
        from modules.agents.teams.safety import resolve_tools

        return resolve_tools(tool_names, user_role)
    except ImportError:
        # safety.py 尚未就绪，直接从主工具集解析
        from modules.agents.tools import get_server_tools

        all_tools = {t.name: t for t in get_server_tools(user_role)}
        return [all_tools[n] for n in tool_names if n in all_tools]


def _wrap_tools_safe(tools: list, safety_mode: str, member_name: str) -> list:
    """为工具添加安全层包装，容错处理"""
    try:
        from modules.agents.teams.safety import wrap_tools_for_team

        return wrap_tools_for_team(tools, safety_mode, member_name)
    except ImportError:
        return tools


class TeamEngine:
    """将团队定义编译为 LangGraph 可执行图并管理执行生命周期

    核心职责:
    1. 根据拓扑类型构建对应的 LangGraph 图
    2. 缓存已编译的图，配置变更时自动失效
    3. 执行图并通过 SSE 事件流返回结果
    4. 支持执行超时和取消
    """

    def __init__(self, store):
        """初始化引擎

        Args:
            store: TeamStore 实例，用于数据读写
        """
        from modules.agents.teams.store import TeamStore

        self.store: TeamStore = store
        # team_id → (compiled_graph, build_timestamp)
        self._graph_cache: dict[str, tuple] = {}
        # exec_id → asyncio.Task
        self._active_executions: dict[str, asyncio.Task] = {}

    # ─── 图构建 ───

    async def build_team_graph(self, team_id: str):
        """构建团队图，带缓存（团队配置变更时自动 invalidate）

        Args:
            team_id: 团队 ID

        Returns:
            CompiledStateGraph 实例

        Raises:
            ValueError: 团队不存在或无成员
        """
        team = await self.store.get_team(team_id)
        if not team:
            raise ValueError(f"团队 {team_id} 不存在")

        members = await self.store.get_members(team_id)
        if not members:
            raise ValueError(f"团队 {team_id} 无成员")

        # 缓存检查: team.updated_at 变化时重建
        cache_key = team_id
        if cache_key in self._graph_cache:
            cached_graph, cached_time_str = self._graph_cache[cache_key]
            team_updated = team.get("updated_at", "")
            if cached_time_str and cached_time_str >= team_updated:
                logger.debug("使用缓存的团队图: %s", team_id)
                return cached_graph

        topology = team["topology"]
        logger.info("构建团队图: %s (拓扑=%s, 成员=%d)", team["name"], topology, len(members))

        if topology == "supervisor":
            graph = self._build_supervisor(team, members)
        elif topology == "swarm":
            graph = self._build_swarm(team, members)
        elif topology == "pipeline":
            graph = self._build_pipeline(team, members)
        else:
            raise ValueError(f"未知拓扑类型: {topology}")

        # 使用 team 的 updated_at 作为缓存标记
        self._graph_cache[cache_key] = (graph, team.get("updated_at", ""))
        return graph

    def _build_member_agent(self, member: dict, team: dict):
        """为单个团队成员构建 react agent

        Args:
            member: 成员配置字典
            team: 团队配置字典

        Returns:
            CompiledStateGraph (react agent)
        """
        from langgraph.prebuilt import create_react_agent

        # 1. 解析工具列表
        tools_json = member.get("tools_json", "[]")
        tool_names = json.loads(tools_json) if isinstance(tools_json, str) else tools_json

        raw_tools = _resolve_tools_safe(tool_names)
        safe_tools = _wrap_tools_safe(raw_tools, team.get("safety_mode", "supervised"), member["name"])

        # 2. 选择模型 (成员 > 团队 > 全局默认)
        model_id = member.get("model_id") or team.get("default_model") or settings.agent_default_model
        model = _get_chat_model_by_id(model_id)

        # 3. 构建 react agent
        agent = create_react_agent(
            model=model,
            tools=safe_tools,
            name=member["name"],
            prompt=member.get("system_prompt", ""),
        )

        return agent

    def _build_supervisor(self, team: dict, members: list[dict]):
        """Supervisor 拓扑: leader 通过 handoff tools 调度 workers

        Args:
            team: 团队配置
            members: 成员列表

        Returns:
            CompiledStateGraph
        """
        from langgraph_supervisor import create_supervisor

        # 找到 leader（agent_type == "leader"），否则第一个成员当 leader
        leader = next((m for m in members if m.get("agent_type") == "leader"), members[0])
        workers = [m for m in members if m["id"] != leader["id"]]

        if not workers:
            raise ValueError("Supervisor 拓扑至少需要 1 个 worker 成员")

        # 构建 worker agents
        worker_agents = []
        for w in workers:
            agent = self._build_member_agent(w, team)
            worker_agents.append(agent)

        # Supervisor 模型
        model_id = leader.get("model_id") or team.get("default_model") or settings.agent_default_model
        supervisor_model = _get_chat_model_by_id(model_id)

        # Supervisor 提示词
        prompt = leader.get("system_prompt") or f"你是团队 '{team['name']}' 的组长。根据任务需求分配给合适的成员执行。"

        # create_supervisor 返回 StateGraph，需要 .compile()
        workflow = create_supervisor(
            agents=worker_agents,
            model=supervisor_model,
            prompt=prompt,
            supervisor_name=leader["name"],
            output_mode="full_history",
        )
        return workflow.compile()

    def _build_swarm(self, team: dict, members: list[dict]):
        """Swarm 拓扑: 成员间自主 handoff 协作

        Args:
            team: 团队配置
            members: 成员列表

        Returns:
            CompiledStateGraph
        """
        from langgraph.prebuilt import create_react_agent
        from langgraph_swarm import create_handoff_tool, create_swarm

        agents = []
        for m in members:
            # 解析 handoff 目标
            handoff_targets_raw = m.get("handoff_targets", "[]")
            targets = json.loads(handoff_targets_raw) if isinstance(handoff_targets_raw, str) else handoff_targets_raw

            # 无显式 targets → 可 handoff 给所有其他成员
            if not targets:
                targets = [other["name"] for other in members if other["id"] != m["id"]]

            handoff_tools = [
                create_handoff_tool(
                    agent_name=t,
                    description=f"将任务移交给 {t}",
                )
                for t in targets
            ]

            # 解析工具
            tools_json = m.get("tools_json", "[]")
            tool_names = json.loads(tools_json) if isinstance(tools_json, str) else tools_json
            raw_tools = _resolve_tools_safe(tool_names)
            safe_tools = _wrap_tools_safe(raw_tools, team.get("safety_mode", "supervised"), m["name"])

            # 选择模型
            model_id = m.get("model_id") or team.get("default_model") or settings.agent_default_model
            model = _get_chat_model_by_id(model_id)

            agent = create_react_agent(
                model=model,
                tools=safe_tools + handoff_tools,
                name=m["name"],
                prompt=m.get("system_prompt", ""),
            )
            agents.append(agent)

        # 第一个成员为默认活跃 agent
        default_active = members[0]["name"]
        workflow = create_swarm(agents, default_active_agent=default_active)
        return workflow.compile()

    def _build_pipeline(self, team: dict, members: list[dict]):
        """Pipeline 拓扑: 按 position 顺序依次执行，上游输出注入下游上下文

        Args:
            team: 团队配置
            members: 成员列表

        Returns:
            CompiledStateGraph
        """
        from langgraph.graph import END, START, StateGraph

        sorted_members = sorted(members, key=lambda m: m.get("position", 0))

        graph = StateGraph(TeamState)

        for i, member in enumerate(sorted_members):
            agent = self._build_member_agent(member, team)
            node_name = member["name"]

            # 用闭包捕获当前 agent 和位置，避免 late-binding 问题
            async def pipeline_node(
                state: TeamState,
                *,
                _agent=agent,
                _name=node_name,
                _pos=i,
            ) -> dict:
                """Pipeline 节点: 将上游输出作为上下文注入，执行当前 agent"""
                # 构建上游输出上下文
                context_parts = []
                for prev_name, prev_output in state.get("agent_outputs", {}).items():
                    context_parts.append(f"## {prev_name} 的输出:\n{prev_output}")

                messages = list(state["messages"])
                if context_parts and _pos > 0:
                    context_msg = HumanMessage(content="以下是上游智能体的分析结果:\n\n" + "\n\n".join(context_parts))
                    # 插入到用户指令之后
                    messages.insert(1, context_msg)

                result = await _agent.ainvoke({"messages": messages})

                # 提取最后一条 AI 消息作为本阶段输出
                last_ai = None
                for msg in reversed(result.get("messages", [])):
                    if isinstance(msg, AIMessage) and msg.content:
                        last_ai = msg
                        break
                output_text = last_ai.content if last_ai else ""

                return {
                    "messages": result["messages"],
                    "agent_outputs": {_name: output_text},
                    "current_agent": _name,
                    "step_count": state.get("step_count", 0) + 1,
                }

            graph.add_node(node_name, pipeline_node)

        # 连接边: START → member_0 → member_1 → ... → END
        graph.add_edge(START, sorted_members[0]["name"])
        for i in range(len(sorted_members) - 1):
            graph.add_edge(sorted_members[i]["name"], sorted_members[i + 1]["name"])
        graph.add_edge(sorted_members[-1]["name"], END)

        return graph.compile()

    # ─── 执行管理 ───

    async def execute(self, team_id: str, instruction: str, username: str) -> AsyncGenerator[dict, None]:
        """执行团队任务，yield SSE 事件字典

        Args:
            team_id: 团队 ID
            instruction: 用户指令
            username: 执行用户

        Yields:
            SSE 事件字典 {"event": str, "data": dict}
        """
        team = await self.store.get_team(team_id)
        if not team:
            yield {"event": "team_error", "data": {"error": f"团队 {team_id} 不存在"}}
            return

        if not team.get("enabled"):
            yield {"event": "team_error", "data": {"error": f"团队 '{team['name']}' 已禁用"}}
            return

        try:
            graph = await self.build_team_graph(team_id)
        except ValueError as e:
            yield {"event": "team_error", "data": {"error": str(e)}}
            return

        execution = await self.store.create_execution(team_id, instruction, username, team["topology"])
        exec_id = execution["id"]
        start_time = time.time()

        yield {
            "event": "team_start",
            "data": {
                "execution_id": exec_id,
                "team": team["name"],
                "topology": team["topology"],
            },
        }

        timeout = team.get("timeout_seconds", 300)
        max_steps = team.get("max_steps", 50)
        agent_outputs: dict[str, str] = {}
        step_count = 0
        error_msg = None
        final_status = "success"

        try:
            # 使用 asyncio.wait_for 实现超时
            event_gen = self._stream_events(graph, instruction, exec_id, team, max_steps)

            async def _consume_with_timeout():
                nonlocal step_count, agent_outputs
                async for event in event_gen:
                    step_count += 1
                    yield event

                    # 收集各 agent 输出
                    if event.get("event") == "agent_complete":
                        data = event.get("data", {})
                        agent_outputs[data.get("agent", "")] = data.get("output", "")

            # 带超时的事件消费
            deadline = time.time() + timeout
            async for event in _consume_with_timeout():
                if time.time() > deadline:
                    raise TimeoutError()
                yield event

        except TimeoutError:
            final_status = "timeout"
            error_msg = f"团队执行超时 ({timeout}s)"
            yield {"event": "team_error", "data": {"error": error_msg}}

        except asyncio.CancelledError:
            final_status = "cancelled"
            error_msg = "用户取消执行"

        except Exception as e:
            final_status = "failed"
            error_msg = str(e)
            logger.exception("[Team] 执行失败: %s", e)
            yield {"event": "team_error", "data": {"error": error_msg}}

        duration = time.time() - start_time

        # 汇总结果
        result_text = self._summarize_outputs(agent_outputs, team["topology"])

        try:
            await self.store.complete_execution(
                exec_id, final_status, result_text, agent_outputs, duration, step_count, error_msg
            )
        except Exception as e:
            logger.error("保存执行结果失败: %s", e)

        yield {
            "event": "team_complete",
            "data": {
                "execution_id": exec_id,
                "status": final_status,
                "result": result_text,
                "duration": round(duration, 1),
                "steps": step_count,
            },
        }

    async def _stream_events(
        self, graph, instruction: str, exec_id: str, team: dict, max_steps: int
    ) -> AsyncGenerator[dict, None]:
        """内部事件流生成器，解析 astream_events v2 格式

        Args:
            graph: 已编译的 LangGraph 图
            instruction: 用户指令
            exec_id: 执行记录 ID
            team: 团队配置
            max_steps: 最大步数
        """
        step = 0
        current_agent = ""
        seen_agents = set()

        async for event in graph.astream_events(
            {"messages": [HumanMessage(content=instruction)]},
            version="v2",
        ):
            kind = event.get("event", "")
            name = event.get("name", "")
            tags = event.get("tags", [])

            # 检测活跃 agent 切换 — 通过 on_chain_start 事件
            if kind == "on_chain_start" and name and name != current_agent:
                # 过滤掉内部节点名（如 tools, __start__ 等）
                if name.startswith("_") or name in ("tools", "RunnableSequence", "ChannelWrite"):
                    pass
                else:
                    if current_agent and current_agent in seen_agents:
                        yield {
                            "event": "agent_complete",
                            "data": {"agent": current_agent, "output": ""},
                        }
                    current_agent = name
                    seen_agents.add(name)
                    yield {
                        "event": "agent_start",
                        "data": {"agent": current_agent, "step": step},
                    }
                    try:
                        await self.store.log_message(
                            exec_id, current_agent, None, "status", f"{current_agent} 开始工作"
                        )
                    except Exception as e:
                        logger.debug("记录 agent 状态失败: %s", e)

            # LLM 流式输出
            elif kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    content = chunk.content
                    # content 可能是 string 或 list
                    if isinstance(content, list):
                        text_parts = [
                            c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"
                        ]
                        content = "".join(text_parts)
                    if content:
                        yield {
                            "event": "agent_message",
                            "data": {"agent": current_agent, "content": content},
                        }

            # 工具调用开始
            elif kind == "on_tool_start":
                tool_name = event.get("name", "")
                tool_input = event.get("data", {}).get("input", {})
                # 截断过长的工具输入
                input_str = str(tool_input)[:500] if tool_input else ""
                yield {
                    "event": "agent_tool_call",
                    "data": {
                        "agent": current_agent,
                        "tool": tool_name,
                        "input": input_str,
                    },
                }
                try:
                    await self.store.log_message(
                        exec_id, current_agent, None, "tool_call", f"调用 {tool_name}: {input_str[:200]}"
                    )
                except Exception as e:
                    logger.debug("记录 tool_call 消息失败: %s", e)

            # 工具结果
            elif kind == "on_tool_end":
                output = str(event.get("data", {}).get("output", ""))[:500]
                yield {
                    "event": "agent_tool_result",
                    "data": {
                        "agent": current_agent,
                        "tool": event.get("name", ""),
                        "output": output,
                    },
                }

            step += 1
            if step >= max_steps:
                yield {
                    "event": "team_error",
                    "data": {"error": f"超过最大步数 {max_steps}"},
                }
                break

        # 最后一个 agent 的 complete 事件
        if current_agent and current_agent in seen_agents:
            yield {
                "event": "agent_complete",
                "data": {"agent": current_agent, "output": ""},
            }

    async def cancel_execution(self, exec_id: str) -> bool:
        """取消正在运行的执行

        Args:
            exec_id: 执行 ID

        Returns:
            是否成功取消
        """
        task = self._active_executions.get(exec_id)
        if task and not task.done():
            task.cancel()
            try:
                await self.store.complete_execution(exec_id, "cancelled", None, {}, 0, 0, "用户取消")
            except Exception as e:
                logger.error("更新取消状态失败: %s", e)
            return True
        return False

    def register_execution_task(self, exec_id: str, task: asyncio.Task):
        """注册执行任务以支持取消

        Args:
            exec_id: 执行 ID
            task: asyncio.Task 实例
        """
        self._active_executions[exec_id] = task

    def unregister_execution_task(self, exec_id: str):
        """注销执行任务

        Args:
            exec_id: 执行 ID
        """
        self._active_executions.pop(exec_id, None)

    def invalidate_cache(self, team_id: str):
        """团队配置更新后清除缓存

        Args:
            team_id: 团队 ID
        """
        removed = self._graph_cache.pop(team_id, None)
        if removed:
            logger.info("已清除团队图缓存: %s", team_id)

    def invalidate_all_cache(self):
        """清除所有团队图缓存"""
        count = len(self._graph_cache)
        self._graph_cache.clear()
        if count:
            logger.info("已清除全部 %d 个团队图缓存", count)

    @staticmethod
    def _summarize_outputs(agent_outputs: dict, topology: str) -> str:
        """将各 agent 输出汇总为 Markdown 报告

        Args:
            agent_outputs: {agent_name: output_text}
            topology: 拓扑类型

        Returns:
            Markdown 格式的汇总文本
        """
        if not agent_outputs:
            return "团队未产生输出"

        parts = []
        for name, output in agent_outputs.items():
            if output:
                parts.append(f"## {name}\n\n{output}")
            else:
                parts.append(f"## {name}\n\n*(无输出)*")

        header = f"# 团队执行报告 ({topology})\n\n"
        return header + "\n\n---\n\n".join(parts)


# ─── 模块级单例 ───

_engine_instance: TeamEngine | None = None


def get_team_engine() -> TeamEngine:
    """获取 TeamEngine 单例"""
    global _engine_instance
    if _engine_instance is None:
        from modules.agents.teams.store import TeamStore

        _engine_instance = TeamEngine(store=TeamStore())
    return _engine_instance


def reset_team_engine():
    """重置 TeamEngine 单例（配置变更后调用）"""
    global _engine_instance
    if _engine_instance:
        _engine_instance.invalidate_all_cache()
    _engine_instance = None

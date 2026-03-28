"""团队图共享状态定义"""

from typing import Annotated

from langgraph.graph import MessagesState


def _merge_dicts(a: dict, b: dict) -> dict:
    """合并两个字典，用于 agent_outputs 的 reducer"""
    return {**a, **b}


class TeamState(MessagesState):
    """团队 StateGraph 的共享状态

    继承 MessagesState 以获得 messages 字段和自动消息合并。
    额外字段用于跟踪执行进度和各成员输出。
    """

    team_id: str = ""
    execution_id: str = ""
    current_agent: str = ""
    agent_outputs: Annotated[dict, _merge_dicts] = {}
    step_count: int = 0
    handoff_count: int = 0  # swarm 模式循环检测

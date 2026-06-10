"""
agent/state.py
Defines the shape of state that flows through the LangGraph ReAct graph.
"""

from typing import Annotated, Any
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    # The full message history for this session (auto-merged by add_messages)
    messages: Annotated[list, add_messages]

    # User identity — used to scope long-term memory
    user_id: str

    # Long-term memories injected at the start of each turn
    recalled_memories: list[str]

    # Any structured context the agent wants to carry forward
    context: dict[str, Any]

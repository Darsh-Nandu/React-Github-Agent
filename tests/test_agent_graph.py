"""
tests/test_agent_graph.py

Tests for agent/graph.py (build_system_prompt, build_agent smoke test)
and agent/state.py (AgentState structure).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# build_system_prompt


class TestBuildSystemPrompt:
    def test_base_prompt_returned_when_no_memories(self):
        from agent.graph import build_system_prompt, BASE_SYSTEM_PROMPT

        result = build_system_prompt([])
        assert result == BASE_SYSTEM_PROMPT

    def test_memories_injected_into_prompt(self):
        from agent.graph import build_system_prompt

        memories = ["User is called Bob", "User prefers Python 3.12"]
        result = build_system_prompt(memories)
        assert "User is called Bob" in result
        assert "User prefers Python 3.12" in result
        assert "Relevant memories" in result

    def test_each_memory_on_own_line(self):
        from agent.graph import build_system_prompt

        memories = ["fact A", "fact B", "fact C"]
        result = build_system_prompt(memories)
        for fact in memories:
            assert f"- {fact}" in result

    def test_single_memory(self):
        from agent.graph import build_system_prompt

        result = build_system_prompt(["only one fact"])
        assert "only one fact" in result


# AgentState


class TestAgentState:
    def test_state_fields(self):
        from agent.state import AgentState

        # TypedDict - just verify keys exist
        assert "messages" in AgentState.__annotations__
        assert "user_id" in AgentState.__annotations__
        assert "recalled_memories" in AgentState.__annotations__
        assert "context" in AgentState.__annotations__

    def test_state_instantiation(self):
        from agent.state import AgentState

        state: AgentState = {
            "messages": [],
            "user_id": "user1",
            "recalled_memories": ["a memory"],
            "context": {"key": "value"},
        }
        assert state["user_id"] == "user1"
        assert state["recalled_memories"] == ["a memory"]


# build_agent


class TestBuildAgent:
    @pytest.mark.asyncio
    async def test_build_agent_falls_back_when_mcp_unavailable(self):
        """Agent should build successfully even when MCP server is down."""
        from agent.graph import build_agent

        with (
            patch("agent.graph.MultiServerMCPClient") as MockClient,
            patch("agent.graph.get_github_tools", return_value=[MagicMock()]),
            patch("agent.graph.ChatGroq") as MockLLM,
            patch(
                "agent.graph.create_react_agent", return_value=MagicMock()
            ) as mock_create,
        ):
            # Simulate MCP unavailable
            instance = AsyncMock()
            instance.get_tools.side_effect = ConnectionError("MCP down")
            MockClient.return_value = instance

            agent = await build_agent(mcp_url="http://localhost:9999/sse")

        assert agent is not None
        mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_agent_loads_github_tools(self):
        from agent.graph import build_agent

        fake_github_tools = [MagicMock(), MagicMock()]

        with (
            patch("agent.graph.MultiServerMCPClient") as MockClient,
            patch("agent.graph.get_github_tools", return_value=fake_github_tools),
            patch("agent.graph.ChatGroq"),
            patch(
                "agent.graph.create_react_agent", return_value=MagicMock()
            ) as mock_create,
        ):
            instance = AsyncMock()
            instance.get_tools.side_effect = Exception("mcp down")
            MockClient.return_value = instance

            await build_agent()

        # All tools passed to create_react_agent
        called_tools = (
            mock_create.call_args.kwargs.get("tools") or mock_create.call_args.args[1]
        )
        assert len(called_tools) >= len(fake_github_tools)


# stream_agent / run_agent (smoke)


class TestRunAgent:
    @pytest.mark.asyncio
    async def test_run_agent_returns_string(self):
        from agent.graph import run_agent

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="Final answer")]}
        )

        with (
            patch("agent.graph.recall_memories", return_value=[]),
            patch("agent.graph._maybe_save_memory"),
        ):
            result = await run_agent(
                agent=mock_agent,
                user_message="Hello",
                session_id="sess-1",
                user_id="user-1",
            )

        assert result == "Final answer"

    @pytest.mark.asyncio
    async def test_run_agent_injects_memories(self):
        from agent.graph import run_agent

        mock_agent = MagicMock()
        mock_agent.ainvoke = AsyncMock(
            return_value={"messages": [MagicMock(content="response")]}
        )

        captured = {}

        async def fake_invoke(input_, config):
            captured["messages"] = input_["messages"]
            return {"messages": [MagicMock(content="response")]}

        mock_agent.ainvoke = fake_invoke

        with (
            patch("agent.graph.recall_memories", return_value=["User is Alice"]),
            patch("agent.graph._maybe_save_memory"),
        ):
            await run_agent(
                agent=mock_agent,
                user_message="What is my name?",
                session_id="s1",
                user_id="u1",
            )

        system_msg = captured["messages"][0]
        assert "User is Alice" in system_msg.content


class TestStreamAgent:
    @pytest.mark.asyncio
    async def test_stream_agent_yields_tokens(self):
        from agent.graph import stream_agent
        from langchain_core.messages import AIMessageChunk

        async def fake_astream_events(*args, **kwargs):
            chunk = MagicMock()
            chunk.content = "Hello "
            yield {"event": "on_chat_model_stream", "data": {"chunk": chunk}}
            chunk2 = MagicMock()
            chunk2.content = "world"
            yield {"event": "on_chat_model_stream", "data": {"chunk": chunk2}}

        mock_agent = MagicMock()
        mock_agent.astream_events = fake_astream_events

        with (
            patch("agent.graph.recall_memories", return_value=[]),
            patch("agent.graph._maybe_save_memory"),
        ):
            tokens = []
            async for chunk in stream_agent(
                agent=mock_agent,
                user_message="hi",
                session_id="s1",
                user_id="u1",
            ):
                tokens.append(chunk)

        text = "".join(t for t in tokens if not t.startswith("\n"))
        assert "Hello " in text or "world" in text

    @pytest.mark.asyncio
    async def test_stream_agent_emits_tool_events(self):
        from agent.graph import stream_agent

        async def fake_astream_events(*args, **kwargs):
            yield {"event": "on_tool_start", "name": "list_repos", "data": {}}
            yield {"event": "on_tool_end", "name": "list_repos", "data": {}}

        mock_agent = MagicMock()
        mock_agent.astream_events = fake_astream_events

        with (
            patch("agent.graph.recall_memories", return_value=[]),
            patch("agent.graph._maybe_save_memory"),
        ):
            tokens = []
            async for chunk in stream_agent(
                agent=mock_agent,
                user_message="list my repos",
                session_id="s1",
                user_id="u1",
            ):
                tokens.append(chunk)

        combined = "".join(tokens)
        assert "list_repos" in combined

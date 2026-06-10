"""
agent/graph.py

Builds the LangGraph ReAct agent:
    1. Recalls long-term memories and injects them into the system prompt
    2. Optionally injects a repo-specific context block
    3. Runs the ReAct Think -> Act -> Observe loop
    4. After each turn, extracts facts and saves to long-term memory
"""

import asyncio
import os
from typing import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from agent.memory import recall_memories, save_memory, short_term_memory
from agent.state import AgentState
from github_tools.github_toolkit import get_github_tools

BASE_SYSTEM_PROMPT = """You are a powerful AI assistant with access to:
- Custom tools via an MCP server (code execution, web search, file utilities)
- Full GitHub access (read repos, write files, create commits, manage PRs and issues)
- Memory of past interactions with this user

## How to use your tools
- Always THINK before acting. Reason about what tools to call and in what order.
- Use GitHub tools to read code before editing it, never guess at file contents.
- When writing code to GitHub, always read the existing file first if it exists.
- After completing a multi-step task, summarise what you did clearly.

## Memory
- You will be given relevant memories from past sessions at the start of each message.
- Use them to personalise your responses and avoid asking for info you already know.
- Do not reveal to the user how or where memories are stored.

## GitHub best practices
- Create a new branch before making commits unless the user says otherwise.
- Always include a clear commit message describing the change.
- When opening PRs, write a helpful description of what changed and why.

Be helpful, be safe, and always explain your reasoning.
"""

memory_llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)


# Prompt builders


def build_system_prompt(
    memories: list[str],
    repo_context: str | None = None,
) -> str:
    """Assemble the full system prompt with optional memory and repo context blocks."""
    prompt = BASE_SYSTEM_PROMPT

    if memories:
        memory_block = "\n".join(f"- {m}" for m in memories)
        prompt += f"\n\n## Relevant memories from past sessions\n{memory_block}\n"

    if repo_context:
        prompt += f"\n\n## Active repository context\n{repo_context}\n"

    return prompt


def build_repo_context(repo: str | None, branch: str | None = None) -> str | None:
    """
    Build a short context string describing the active repo and branch.
    This gets injected into the system prompt so the agent knows what it is working on.
    """
    if not repo:
        return None
    parts = [f"The user is currently working in the repository: {repo}"]
    if branch:
        parts.append(f"Active branch: {branch}")
    parts.append(
        "Prefer this repo and branch as the default target when the user does not "
        "specify one explicitly."
    )
    return "\n".join(parts)


# Agent builder


async def build_agent(mcp_url: str | None = None):
    """Build and return the compiled LangGraph agent. Call once at startup and reuse."""
    url = mcp_url or os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")

    try:
        client = MultiServerMCPClient({"agent-tools": {"url": url, "transport": "sse"}})
        mcp_tools = await client.get_tools()
        print(f"[agent] Loaded {len(mcp_tools)} tools from MCP server")
    except Exception as e:
        print(f"[agent] MCP server unavailable ({e}). Starting without MCP tools.")
        mcp_tools = []

    github_tools = get_github_tools()
    print(f"[agent] Loaded {len(github_tools)} GitHub tools")

    llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, streaming=True)

    agent = create_react_agent(
        model=llm,
        tools=mcp_tools + github_tools,
        checkpointer=short_term_memory,
    )
    return agent


# Run helpers


async def run_agent(
    agent,
    user_message: str,
    session_id: str,
    user_id: str,
    active_repo: str | None = None,
    active_branch: str | None = None,
) -> str:
    """Run one turn of the agent and return the final text response."""
    memories = recall_memories(user_id=user_id, query=user_message)
    repo_context = build_repo_context(active_repo, active_branch)
    system_prompt = build_system_prompt(memories, repo_context)
    config = {"configurable": {"thread_id": session_id}}

    result = await agent.ainvoke(
        {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
        },
        config=config,
    )

    final_message = result["messages"][-1]
    response_text = (
        final_message.content
        if isinstance(final_message.content, str)
        else str(final_message.content)
    )

    asyncio.create_task(
        _maybe_save_memory(
            user_id=user_id, user_msg=user_message, agent_msg=response_text
        )
    )
    return response_text


async def stream_agent(
    agent,
    user_message: str,
    session_id: str,
    user_id: str,
    active_repo: str | None = None,
    active_branch: str | None = None,
) -> AsyncIterator[str]:
    """Stream the agent response token by token, yielding SSE-friendly chunks."""
    memories = recall_memories(user_id=user_id, query=user_message)
    repo_context = build_repo_context(active_repo, active_branch)
    system_prompt = build_system_prompt(memories, repo_context)
    config = {"configurable": {"thread_id": session_id}}

    full_response = []

    async for event in agent.astream_events(
        {
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_message),
            ]
        },
        config=config,
        version="v2",
    ):
        kind = event.get("event")

        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                text = chunk.content
                if isinstance(text, str) and text:
                    full_response.append(text)
                    yield text

        elif kind == "on_tool_start":
            tool_name = event.get("name", "tool")
            yield f"\n⚙️ *Using tool: `{tool_name}`*\n"

        elif kind == "on_tool_end":
            tool_name = event.get("name", "tool")
            yield f"✅ *`{tool_name}` done*\n\n"

    if full_response:
        asyncio.create_task(
            _maybe_save_memory(
                user_id=user_id,
                user_msg=user_message,
                agent_msg="".join(full_response),
            )
        )


async def _maybe_save_memory(user_id: str, user_msg: str, agent_msg: str) -> None:
    """
    Extract a memorable fact from the exchange and persist it.
    Runs as a fire-and-forget asyncio Task so it never blocks streaming.
    """
    loop = asyncio.get_event_loop()

    def _invoke():
        return memory_llm.invoke(
            [
                SystemMessage(
                    content="You extract important facts from conversations to remember for the future. Only return the fact itself, nothing else."
                ),
                HumanMessage(content=f"User said: {user_msg}"),
                AIMessage(content=f"Assistant said: {agent_msg}"),
                HumanMessage(
                    content="What is one concise fact worth remembering for future interactions? If nothing important, reply with exactly: None"
                ),
            ]
        ).content

    try:
        memory_text = await loop.run_in_executor(None, _invoke)
        print(f"[memory] Extracted: {memory_text}")
        if memory_text and memory_text.strip().lower() != "none":
            save_memory(user_id=user_id, content=memory_text)
    except Exception as e:
        print(f"[memory] _maybe_save_memory failed: {e}")

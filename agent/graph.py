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
import traceback

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

from agent.memory import recall_memories, save_memory, get_short_term_memory
from agent.state import AgentState
from github_tools.github_toolkit import get_github_tools

BASE_SYSTEM_PROMPT = """You are a powerful AI GitHub Assistant with access to:

* Custom tools via an MCP server (code execution, web search, file utilities, and other integrations)
* Full GitHub capabilities (read repositories, analyze code, write files, create commits, manage branches, pull requests, and issues)
* Memory of past interactions with the user

Your primary role is to help users manage, understand, analyze, maintain, and improve GitHub repositories and software projects. However, you are also a general-purpose AI assistant and should respond naturally to non-technical questions, conversations, learning requests, brainstorming, writing tasks, and other general topics.

## Core Behavior

* Be helpful, accurate, professional, and proactive.
* Adapt your responses to the user's goals and level of expertise.
* For repository-related tasks, act as an experienced software engineer, code reviewer, and project collaborator.
* For non-repository questions, behave like a capable general AI assistant and answer normally.
* Do not force GitHub-related workflows when they are not relevant to the user's request.

## Tool Usage

* Always think before acting.
* Determine which tools are necessary before making tool calls.
* Prefer gathering information before making modifications.
* Use the appropriate tool for the task instead of guessing.
* When a task requires multiple steps, execute them methodically and keep track of progress.
* After completing significant actions, provide a concise summary of what was done.

## GitHub Repository Operations

When working with repositories:

* Read and inspect relevant files before making changes.
* Never assume file contents, project structure, APIs, or dependencies.
* Understand the existing codebase before proposing modifications.
* Follow the project's existing coding style and conventions whenever possible.
* Explain important design decisions and trade-offs when relevant.
* Validate changes when tools are available to do so.

## Code Generation and Modification

* Prefer minimal, targeted changes over unnecessary rewrites.
* Preserve existing functionality unless the user explicitly requests otherwise.
* Consider maintainability, readability, performance, and security.
* When introducing new files or components, ensure they integrate cleanly with the existing codebase.
* Clearly communicate any assumptions made.

## GitHub Best Practices

* Create a new branch before making commits unless the user specifies otherwise.
* Use descriptive and meaningful commit messages.
* Write clear pull request titles and descriptions.
* When creating issues, provide useful context, reproduction steps, and recommendations when applicable.
* Respect repository structure, contribution guidelines, and existing workflows.

## Repository Analysis

You can assist with:

* Understanding project architecture
* Code reviews
* Bug investigation and debugging
* Performance analysis
* Security reviews
* Documentation generation
* Dependency analysis
* Feature planning
* Refactoring recommendations
* Test generation and validation
* Repository onboarding and code explanations

## Memory

* Relevant memories from previous interactions may be provided.
* Use them to personalize responses and avoid asking for information already known.
* Do not reveal internal memory mechanisms, storage systems, or implementation details.

## Communication Style

* Be concise when possible and detailed when necessary.
* Explain technical concepts clearly.
* Ask clarifying questions when requirements are ambiguous.
* If a request is unrelated to GitHub, coding, or repositories, respond as a normal AI assistant without mentioning repository tools unless they are relevant.
* Tailor explanations to the user's level of expertise.

## Safety and Reliability

* Do not claim to have performed actions that were not actually completed.
* Be transparent about uncertainty.
* Verify information whenever possible before making changes.
* Prioritize correctness, security, and user intent.

Your goal is to function as both an expert GitHub engineering assistant and a capable general-purpose AI assistant, using repository tools when helpful and behaving like a normal conversational AI when they are not needed.

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

    checkpointer = get_short_term_memory()

    agent = create_agent(
        model=llm,
        tools=mcp_tools + github_tools,
        checkpointer=checkpointer,
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
    try:
        result = await agent.ainvoke(
            {
                "messages": [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_message),
                ]
            },
            config=config,
        )
    except Exception:
        traceback.print_exc()

        print("=" * 80)

        print("FULL ERROR")
        traceback.print_exc()

        print("TYPE:", type(e))

        print("DIR:", dir(e))

        if hasattr(e, "body"):
            print("BODY:", e.body)

        if hasattr(e, "response"):
            print("RESPONSE:", e.response)

        if hasattr(e, "args"):
            print("ARGS:", e.args)

        print("=" * 80)

        raise

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

    """ 
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
        print("EVENT:", event)
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
    """
    response = await agent.ainvoke(
    {
        "messages": [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
    },
    config=config,
    )

    print(response)

    yield str(response["messages"][-1].content)

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

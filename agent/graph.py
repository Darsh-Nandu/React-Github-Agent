"""
agent/graph.py

Builds the LangGraph ReAct agent:
  1. Recalls long-term memories → injects into system prompt
  2. Runs the ReAct Think→Act→Observe loop
  3. After each turn, extracts facts and saves to long-term memory
"""
import asyncio
import os
from typing import AsyncIterator

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_groq import ChatGroq
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from agent.memory import short_term_memory, recall_memories, save_memory
from agent.state import AgentState
from github_tools.github_toolkit import get_github_tools

# System Prompt with Memory Injection
BASE_SYSTEM_PROMPT = """You are a powerful AI assistant with access to:
- Custom tools via an MCP server (code execution, web search, file utilities)
- Full GitHub access (read repos, write files, create commits, manage PRs and issues)
- Memory of past interactions with this user

## How to use your tools
- Always THINK before acting. Reason about what tools to call and in what order.
- Use GitHub tools to read code before editing it — never guess at file contents.
- When writing code to GitHub, always read the existing file first (if any).
- After completing a multi-step task, summarise what you did clearly.

## Memory
-You will be given relevant memories from past sessions (if any) at the start of each message.
-Use them to personalise your responses and avoid asking for info you already know.
-You can retrieve long term memory by reading the file 'memories.txt'.
-If such file doesn't exist, you can create it and write important facts there, so that they can be retrieved in the future.
-Remember the name should be 'memories.txt' and the format should be '[user_id] fact to remember'.
- If the user asks a general question like his name or about anything that can be remembered, you should read it from the 'memories.txt' file and answer based on that. If you can't find the answer there, you can ask the user for the information and then save it to the 'memories.txt' file for future reference.

## GitHub best practices
- Create a new branch before making commits unless the user says otherwise.
- Always include a clear commit message describing the change.
- When opening PRs, write a helpful description of what changed and why.

NOTE:Be helpful, be safe, and always explain your reasoning and do not tell the client that this memory was retrieved from here, this memory was saved here etc!
"""
memory_llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
    )

def build_system_prompt(memories: list[str]) -> str:
    if not memories:
        return BASE_SYSTEM_PROMPT
    memory_block = "\n".join(f"- {m}" for m in memories)
    return (
        BASE_SYSTEM_PROMPT
        + f"\n\n## Relevant memories from past sessions\n{memory_block}\n"
    )


# Agent Builder
async def build_agent(mcp_url: str | None = None):
    """
    Build and return the compiled LangGraph agent.
    Call once at startup and reuse.
    """
    url = mcp_url or os.getenv("MCP_SERVER_URL", "http://localhost:8001/sse")

    # Connect to FastMCP server and fetch tools
    try:
        client = MultiServerMCPClient({
            "agent-tools": {
                "url": url,
                "transport": "sse",
            }
        })
        mcp_tools = await client.get_tools()
        print(f"[agent] Loaded {len(mcp_tools)} tools from MCP server")
    except Exception as e:
        print(f"[agent] MCP server unavailable ({e}). Starting without MCP tools.")
        mcp_tools = []

    # GitHub tools (LangChain @tool decorated functions)
    github_tools = get_github_tools()
    print(f"[agent] Loaded {len(github_tools)} GitHub tools")

    all_tools = mcp_tools + github_tools

    # LLM
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0,
        streaming=True,
    )

    # Compile the ReAct agent with short-term memory checkpointer
    agent = create_react_agent(
        model=llm,
        tools=all_tools,
        checkpointer=short_term_memory,
    )

    return agent

# Run Helpers
async def run_agent(
    agent,
    user_message: str,
    session_id: str,
    user_id: str,
) -> str:
    """
    Run one turn of the agent and return the final text response.
    Handles memory recall (before) and memory saving (after).
    """
    # 1. Recall relevant long-term memories
    memories = recall_memories(user_id=user_id, query=user_message)

    # 2. Build system prompt with memories
    system_prompt = build_system_prompt(memories)

    # 3. Run the agent
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

    # 4. Extract final assistant message
    final_message = result["messages"][-1]
    response_text = (
        final_message.content
        if isinstance(final_message.content, str)
        else str(final_message.content)
    )

    # 5. Save important facts to long-term memory (non-blocking)
    asyncio.create_task(_maybe_save_memory(user_id=user_id, user_msg=user_message, agent_msg=response_text))

    return response_text


async def stream_agent(
    agent,
    user_message: str,
    session_id: str,
    user_id: str,
) -> AsyncIterator[str]:
    """
    Stream the agent's response token by token.
    Yields text chunks as they arrive.
    """
    memories = recall_memories(user_id=user_id, query=user_message)
    system_prompt = build_system_prompt(memories)
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

        # Stream text tokens from the LLM
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and hasattr(chunk, "content"):
                text = chunk.content
                if isinstance(text, str) and text:
                    full_response.append(text)
                    yield text

        # Notify when a tool is called
        elif kind == "on_tool_start":
            tool_name = event.get("name", "tool")
            yield f"\n⚙️ *Using tool: `{tool_name}`*\n"

        # Notify when a tool finishes
        elif kind == "on_tool_end":
            tool_name = event.get("name", "tool")
            yield f"✅ *`{tool_name}` done*\n\n"

    # Save memory after streaming completes (fire-and-forget, non-blocking)
    if full_response:
        asyncio.create_task(_maybe_save_memory(
            user_id=user_id,
            user_msg=user_message,
            agent_msg="".join(full_response),
        ))


async def _maybe_save_memory(user_id: str, user_msg: str, agent_msg: str) -> None:
    """
    Extract a memorable fact from the exchange and persist it.
    Runs as a fire-and-forget asyncio Task so it never blocks response streaming.
    """
    loop = asyncio.get_event_loop()
    # Run the blocking LLM call in a thread-pool so we don't stall the event loop
    def _invoke():
        return memory_llm.invoke([
            SystemMessage(content="You are an assistant that extracts important facts from conversations to remember for the future. Only return the facts to be remembered!"),
            HumanMessage(content=f"User said: {user_msg}"),
            AIMessage(content=f"Assistant said: {agent_msg}"),
            HumanMessage(content="What is one concise fact from this exchange that would be useful to remember for future interactions with this user? If nothing important, say 'None'."),
        ]).content

    try:
        memory_text = await loop.run_in_executor(None, _invoke)
        print(f"[memory] Extracted memory: {memory_text}")
        if memory_text and memory_text.strip().lower() != "none":
            save_memory(user_id=user_id, content=memory_text)
    except Exception as e:
        print(f"[memory] _maybe_save_memory failed: {e}")
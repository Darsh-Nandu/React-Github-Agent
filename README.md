<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0d1117,50:1a1a2e,100:16213e&height=140&section=header&text=ReAct%20GitHub%20Agent&fontSize=38&fontColor=58a6ff&fontAlignY=65&animation=fadeIn" width="100%"/>

<br/>

<img src="https://img.shields.io/badge/LangGraph-ReAct_Loop-6366f1?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/FastAPI-Backend-009688?style=for-the-badge&logo=fastapi&logoColor=white"/>
<img src="https://img.shields.io/badge/FastMCP-Tool_Server-ff6b35?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Mem0-Dual_Memory-8b5cf6?style=for-the-badge&logo=brain&logoColor=white"/>
<img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/License-MIT-22c55e?style=for-the-badge"/>

<br/><br/>

### An autonomous AI agent that manages GitHub repositories through a full **Think → Act → Observe** loop -
### with live streaming, dual memory, and 25+ tools across code execution, web search, and the full GitHub API.

<br/>

[**Quick Start**](#-quick-start) &nbsp;·&nbsp; [**Architecture**](#-architecture) &nbsp;·&nbsp; [**Tools**](#-tools) &nbsp;·&nbsp; [**Memory**](#-memory-system) &nbsp;·&nbsp; [**API**](#-api-reference)

<br/>

</div>

---

## What It Does

You talk to it. It reasons, picks tools, executes them, observes results, and keeps going until the task is done.

```
You   →  "Review the open PRs in my repo and add a comment summarising the diff on each one"

Agent →  [thinks]  I need to list PRs, then get each diff, then post a comment.
      →  [tool]    list_pull_requests("Darsh-Nandu/my-repo")
      →  [tool]    get_pr_diff("Darsh-Nandu/my-repo", 12)
      →  [tool]    add_issue_comment("Darsh-Nandu/my-repo", 12, "Summary: ...")
      →  [tool]    get_pr_diff("Darsh-Nandu/my-repo", 13)  ...and so on
      →  "Done - added summaries to PR #12 and #13."
```

It remembers your name, your preferred coding style, and your project context - across sessions.

---

## Architecture

```
                    ┌─────────────────────────────────────────────────┐
                    │              ReAct GitHub Agent                  │
                    └─────────────────────────────────────────────────┘

  Browser / API Client
         │
         │  HTTP + SSE (streaming)
         ▼
  ┌─────────────────┐
  │  FastAPI :8000  │   /chat  /chat/stream  /memories  /health
  └────────┬────────┘
           │
           ▼
  ┌──────────────────────────────────────────┐
  │         LangGraph ReAct Agent            │
  │                                          │
  │  ┌──────────────┐   ┌─────────────────┐  │
  │  │ Short-term   │   │   Long-term     │  │
  │  │ Memory       │   │   Memory (Mem0) │  │
  │  │ (MemorySaver │   │ (cross-session) │  │
  │  │  per-session)│   │                 │  │
  │  └──────────────┘   └─────────────────┘  │
  │                                          │
  │          Think → Act → Observe           │
  └──────┬───────────────────┬───────────────┘
         │                   │
         ▼                   ▼
  ┌─────────────┐    ┌───────────────────┐
  │  FastMCP    │    │   GitHub Tools    │
  │  :8001      │    │   (PyGithub)      │
  │             │    │                   │
  │ run_python  │    │  read/write files │
  │ web_search  │    │  branches, PRs    │
  │ fetch_url   │    │  issues, commits  │
  │ lint/format │    │  search, diffs    │
  └─────────────┘    └───────────────────┘
```

The **FastMCP server** and **FastAPI backend** run as separate processes - MCP tools execute in isolation, keeping the agent backend clean.

---

## Quick Start

### Prerequisites
- Python 3.10+
- A [Groq](https://console.groq.com/) API key *(free tier available)*
- A GitHub [Personal Access Token](https://github.com/settings/tokens) with `repo` + `workflow` scopes
- *(Optional)* OpenAI API key - enables semantic search in Mem0

### 1. Clone & Install

```bash
git clone https://github.com/Darsh-Nandu/React-Github-Agent.git
cd React-Github-Agent

python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env and fill in GROQ_API_KEY and GITHUB_TOKEN
```

### 3. Start the MCP Tool Server

```bash
# Terminal 1
python mcp_server/server.py
# → FastMCP running on http://localhost:8001
```

### 4. Start the Agent Backend

```bash
# Terminal 2
python main.py
# → FastAPI running on http://localhost:8000
```

### 5. Open the UI

Navigate to **[http://localhost:8000](http://localhost:8000)**

---

## UI

![ReAct GitHub Agent UI](https://github.com/user-attachments/assets/54d57d93-dd38-4592-8e1a-8388bef65354)

*Dark terminal-style interface with real-time token streaming and visible tool execution (UI was made in assistance with AI) .*

---

## Tools

### 🐙 GitHub Tools - 15 tools via PyGithub

| Tool | Description |
|:---|:---|
| `list_repos` | List all repos for the authenticated user |
| `get_file_tree` | Browse directory structure of any repo |
| `read_github_file` | Read any file from any branch |
| `write_github_file` | Create or update a file with a commit |
| `create_branch` / `list_branches` | Branch management |
| `list_commits` | View recent commit history on any branch |
| `search_code` | Search code across repos (GitHub syntax supported) |
| `list_issues` / `create_issue` | Issue listing and creation |
| `add_issue_comment` / `close_issue` | Issue interaction |
| `list_pull_requests` / `create_pull_request` | Full PR lifecycle |
| `get_pr_diff` | Get the full diff of any pull request |

### ⚙️ MCP Tools - 10 tools via FastMCP

| Tool | Description |
|:---|:---|
| `run_python` | Execute Python in an isolated subprocess (timeout-safe) |
| `format_python_code` | Format code with Black |
| `lint_python_code` | Lint code with Pylint |
| `fetch_url` | Fetch and parse any URL as plain text |
| `web_search` | Search the web via DuckDuckGo (no API key needed) |
| `read_local_file` / `write_local_file` | Local filesystem access |
| `summarize_text` | Extractive summarization of long content |
| `parse_json` | Parse and pretty-print JSON |
| `diff_strings` | Unified diff between two strings |

---

## Memory System

The agent uses a **two-layer memory architecture** to maintain context within and across sessions.

```
User Message
     │
     ├── 1. recall_memories(user_id, query)
     │         └── semantic search in Mem0 → injected into system prompt
     │
     ├── 2. LangGraph ReAct loop
     │         └── MemorySaver checkpointer keeps full message
     │              history for the duration of the session
     │
     └── 3. _maybe_save_memory(user_id, exchange)
               └── LLM extracts key facts → persisted to Mem0
```

| Layer | Store | Scope | Backend |
|:---|:---|:---|:---|
| Short-term | `MemorySaver` | Single session | In-memory (LangGraph) |
| Long-term | `Mem0` | Cross-session | Vector store (or `memories.txt` fallback) |

> **Upgrade path:** swap `MemorySaver` → `SqliteSaver` for short-term persistence across restarts.

---

## API Reference

| Method | Endpoint | Description |
|:---|:---|:---|
| `POST` | `/chat` | Single-turn - waits for full response |
| `POST` | `/chat/stream` | Streaming - SSE token-by-token |
| `GET` | `/memories` | Fetch all long-term memories for a user |
| `DELETE` | `/memories` | Wipe all memories for a user |
| `GET` | `/health` | Health check + agent readiness |
| `GET` | `/` | Serves the UI |

**Request body for `/chat` and `/chat/stream`:**
```json
{
  "message": "List my repos and find any that have open issues",
  "session_id": "optional-uuid-for-continuity",
  "user_id": "default-user"
}
```

---

## Testing

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests (no API keys required - everything is mocked)
pytest

# With coverage report
pytest --cov=agent --cov=github_tools --cov=mcp_server --cov-report=term-missing
```

The suite covers GitHub tools, memory operations, all API endpoints, and the agent graph - 68 tests, no network calls.

---

## Project Structure

```
React-Github-Agent/
│
├── main.py                    # FastAPI app - routes, lifespan, streaming
│
├── agent/
│   ├── graph.py               # LangGraph ReAct agent + async memory loop
│   ├── memory.py              # MemorySaver (short-term) + Mem0 (long-term)
│   └── state.py               # AgentState TypedDict
│
├── github_tools/
│   └── github_toolkit.py      # 15 GitHub tools via PyGithub
│
├── mcp_server/
│   └── server.py              # FastMCP server - 10 utility tools
│
├── static/
│   └── index.html             # Dark terminal UI with SSE streaming
│
├── tests/
│   ├── conftest.py            # Shared fixtures
│   ├── test_github_toolkit.py # GitHub tool unit tests (mocked API)
│   ├── test_memory.py         # Memory module tests (mocked Mem0)
│   ├── test_api.py            # FastAPI endpoint tests
│   └── test_agent_graph.py    # Agent graph + streaming tests
│
├── .github/
│   └── workflows/
│       └── ci.yml             # CI: test matrix (3.10–3.12), lint, security
│
├── .env.example               # Template for environment variables
├── pyproject.toml             # Project metadata + tool config
├── requirements.txt           # Runtime dependencies
├── requirements-dev.txt       # Dev + test dependencies
├── CONTRIBUTING.md            # How to contribute
└── LICENSE                    # MIT
```

---

## Roadmap

```
✅ LangGraph ReAct loop with streaming
✅ 25 tools - GitHub + MCP
✅ Dual memory (MemorySaver + Mem0)
✅ FastAPI backend with SSE streaming
✅ Dark terminal UI
✅ Test suite (68 tests, fully mocked)
✅ CI pipeline (test matrix, lint, security scan)
✅ MIT License, .env.example, CONTRIBUTING guide
⬜ SqliteSaver for short-term memory persistence across restarts
⬜ Real auth / per-user sessions (JWT)
⬜ Streaming Markdown + syntax highlighting in UI
⬜ Collapsible Think/Act/Observe traces in UI
⬜ Repo-specific system prompt injection
⬜ Memory decay + deduplication
⬜ Docker Compose for one-command startup
```

---

## Tech Stack

<div align="center">

| | Tool | Purpose |
|:---:|:---|:---|
| 🔗 | [LangGraph](https://github.com/langchain-ai/langgraph) | ReAct agent loop + short-term memory checkpointing |
| 🦜 | [LangChain](https://github.com/langchain-ai/langchain) | LLM interface, tool binding, message types |
| ⚡ | [Groq](https://groq.com/) · `llama-3.3-70b-versatile` | Fast LLM inference (free tier available) |
| 🛠️ | [FastMCP](https://github.com/jlowin/fastmcp) | MCP tool server over SSE |
| 🐙 | [PyGithub](https://github.com/PyGithub/PyGithub) | GitHub REST API wrapper |
| 🧠 | [Mem0](https://github.com/mem0ai/mem0) | Long-term cross-session memory |
| 🚀 | [FastAPI](https://fastapi.tiangolo.com/) | Async backend + SSE streaming |
| 🛡️ | [Pydantic v2](https://docs.pydantic.dev/) | Request / response validation |

</div>

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:16213e,50:1a1a2e,100:0d1117&height=80&section=footer" width="100%"/>

MIT License &nbsp;·&nbsp; Built by [Darsh Nandu](https://github.com/Darsh-Nandu)

</div>
"""
main.py

FastAPI backend for the ReAct GitHub agent.

Endpoints:
  POST /chat          → single-turn, returns full response
  POST /chat/stream   → streaming response (SSE)
  GET  /memories      → retrieve user's long-term memories
  DELETE /memories    → wipe user's long-term memories
  GET  /health        → health check
  GET  /              → serve the UI (index.html)
"""

import os
import uuid
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from agent.graph import build_agent, run_agent, stream_agent
from agent.memory import get_all_memories, delete_memories

# Lifespan: build agent once at startup
_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    print("[startup] Building agent...")
    _agent = await build_agent()
    print("[startup] Agent ready ✅")
    yield
    print("[shutdown] Agent stopped")


app = FastAPI(title="ReAct GitHub Agent", lifespan=lifespan)

_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# Request and Response Models


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None  # optional; auto-generated if not provided
    user_id: str = "default-user"  # in production, extract from JWT / session


class ChatResponse(BaseModel):
    response: str
    session_id: str


class MemoriesResponse(BaseModel):
    user_id: str
    memories: list[str]


# Routes


@app.get("/health")
async def health():
    return {"status": "ok", "agent_ready": _agent is not None}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Single-turn chat — waits for full response."""
    if _agent is None:
        raise HTTPException(503, "Agent not ready yet")

    session_id = req.session_id or str(uuid.uuid4())
    response = await run_agent(
        agent=_agent,
        user_message=req.message,
        session_id=session_id,
        user_id=req.user_id,
    )
    return ChatResponse(response=response, session_id=session_id)


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat — returns tokens as they arrive (SSE)."""
    if _agent is None:
        raise HTTPException(503, "Agent not ready yet")

    session_id = req.session_id or str(uuid.uuid4())

    async def event_generator() -> AsyncGenerator[dict, None]:
        # Send session_id first
        yield {"event": "session", "data": session_id}

        async for chunk in stream_agent(
            agent=_agent,
            user_message=req.message,
            session_id=session_id,
            user_id=req.user_id,
        ):
            yield {"event": "token", "data": chunk}

        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


@app.get("/memories", response_model=MemoriesResponse)
async def get_memories(user_id: str = "default-user"):
    """Retrieve all long-term memories for a user."""
    memories = get_all_memories(user_id=user_id)
    return MemoriesResponse(user_id=user_id, memories=memories)


@app.delete("/memories")
async def clear_memories(user_id: str = "default-user"):
    """Delete all long-term memories for a user."""
    delete_memories(user_id=user_id)
    return {"status": "cleared", "user_id": user_id}


# Static Files (UI)

static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_ui():
    index = os.path.join(static_dir, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return {"message": "UI not built. Place index.html in ./static/"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

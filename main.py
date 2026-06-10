"""
main.py

FastAPI backend for the ReAct GitHub Agent.

Endpoints:
    POST /auth/register     -> create account, receive JWT
    POST /auth/login        -> login, receive JWT
    POST /chat              -> single-turn, full response
    POST /chat/stream       -> streaming response (SSE)
    GET  /memories          -> retrieve user long-term memories
    DELETE /memories        -> wipe user long-term memories
    DELETE /memories/prune  -> remove stale memories older than decay threshold
    GET  /health            -> health check
    GET  /                  -> serve the UI
"""

import os
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

load_dotenv()

from agent.graph import build_agent, run_agent, stream_agent
from agent.memory import delete_memories, get_all_memories, prune_stale_memories
from auth import (
    TokenData,
    UserLogin,
    UserRegister,
    get_current_user,
    login_user,
    register_user,
)

# Lifespan

_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _agent
    print("[startup] Building agent...")
    _agent = await build_agent()
    print("[startup] Agent ready")
    yield
    print("[shutdown] Agent stopped")


app = FastAPI(title="ReAct GitHub Agent", version="1.0.0", lifespan=lifespan)

_cors_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=True,
)


# Models


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    active_repo: Optional[str] = None
    active_branch: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class MemoriesResponse(BaseModel):
    user_id: str
    memories: list[str]


# Auth routes


@app.post("/auth/register", response_model=dict)
async def auth_register(body: UserRegister):
    """Register a new user and return a JWT."""
    token = register_user(username=body.username, password=body.password)
    return token.model_dump()


@app.post("/auth/login", response_model=dict)
async def auth_login(body: UserLogin):
    """Authenticate and return a JWT."""
    token = login_user(username=body.username, password=body.password)
    return token.model_dump()


# Chat routes


@app.get("/health")
async def health():
    return {"status": "ok", "agent_ready": _agent is not None}


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, current_user: TokenData = Depends(get_current_user)):
    """Single-turn chat, waits for full response."""
    if _agent is None:
        raise HTTPException(503, "Agent not ready yet")
    session_id = req.session_id or str(uuid.uuid4())
    response = await run_agent(
        agent=_agent,
        user_message=req.message,
        session_id=session_id,
        user_id=current_user.user_id,
        active_repo=req.active_repo,
        active_branch=req.active_branch,
    )
    return ChatResponse(response=response, session_id=session_id)


@app.post("/chat/stream")
async def chat_stream(
    req: ChatRequest, current_user: TokenData = Depends(get_current_user)
):
    """Streaming chat, returns tokens as SSE events."""
    if _agent is None:
        raise HTTPException(503, "Agent not ready yet")
    session_id = req.session_id or str(uuid.uuid4())

    async def event_generator() -> AsyncGenerator[dict, None]:
        yield {"event": "session", "data": session_id}
        async for chunk in stream_agent(
            agent=_agent,
            user_message=req.message,
            session_id=session_id,
            user_id=current_user.user_id,
            active_repo=req.active_repo,
            active_branch=req.active_branch,
        ):
            yield {"event": "token", "data": chunk}
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())


# Memory routes


@app.get("/memories", response_model=MemoriesResponse)
async def get_memories(current_user: TokenData = Depends(get_current_user)):
    """Retrieve all long-term memories for the authenticated user."""
    memories = get_all_memories(user_id=current_user.user_id)
    return MemoriesResponse(user_id=current_user.user_id, memories=memories)


@app.delete("/memories")
async def clear_memories(current_user: TokenData = Depends(get_current_user)):
    """Delete all long-term memories for the authenticated user."""
    delete_memories(user_id=current_user.user_id)
    return {"status": "cleared", "user_id": current_user.user_id}


@app.delete("/memories/prune")
async def prune_memories(current_user: TokenData = Depends(get_current_user)):
    """Remove memories older than the configured decay threshold."""
    pruned = prune_stale_memories(user_id=current_user.user_id)
    return {"status": "pruned", "count": pruned, "user_id": current_user.user_id}


# Static UI

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

"""
agent/memory.py

Short-term memory  → LangGraph MemorySaver (per-session, in-memory)
Long-term memory   → Mem0 (cross-session, persists facts about users/projects)

Upgrade path:
  - Replace MemorySaver with SqliteSaver or RedisSaver for persistence
  - Mem0 auto-upgrades to vector store if OPENAI_API_KEY is set
"""

import os
from langgraph.checkpoint.memory import MemorySaver

# Short-term memory
short_term_memory = MemorySaver()


# Long-term memory using Mem0 (if available)
try:
    from mem0 import Memory as Mem0Memory

    _mem0_config: dict = {}

    # If OpenAI key is present, Mem0 will use embeddings for semantic search.
    # Otherwise it falls back to a simple keyword store.
    if os.getenv("OPENAI_API_KEY"):
        _mem0_config = {
            "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
            "embedder": {"provider": "openai", "config": {"model": "text-embedding-3-small"}},
        }

    _mem0 = Mem0Memory.from_config(_mem0_config) if _mem0_config else Mem0Memory()
    MEM0_AVAILABLE = True

except Exception as e:
    print(f"[memory] Mem0 not available ({e}). Long-term memory disabled.")
    _mem0 = None
    MEM0_AVAILABLE = False


def save_memory(user_id: str, content: str) -> None:
    """Persist a fact or summary to long-term memory for this user."""
    if not MEM0_AVAILABLE or not _mem0:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memories.txt")
        with open(path, "a") as f:
            f.write(f"{content}\n")
        return
    try:
        _mem0.add(content, user_id=user_id)
    except Exception as e:
        print(f"[memory] save failed: {e}")


def recall_memories(user_id: str, query: str, top_k: int = 5) -> list[str]:
    """
    Retrieve the most relevant long-term memories for the current query.
    Returns a list of memory strings (empty list if nothing found).
    """
    if not MEM0_AVAILABLE or not _mem0:
        return []
    try:
        results = _mem0.search(query, user_id=user_id, limit=top_k)
        # Mem0 returns list of dicts with a 'memory' key
        return [r.get("memory", str(r)) for r in results if r]
    except Exception as e:
        print(f"[memory] recall failed: {e}")
        return []


def get_all_memories(user_id: str) -> list[str]:
    """Return all stored memories for a user (for display in the UI)."""
    if not MEM0_AVAILABLE or not _mem0:
        return []
    try:
        results = _mem0.get_all(user_id=user_id)
        return [r.get("memory", str(r)) for r in results if r]
    except Exception as e:
        print(f"[memory] get_all failed: {e}")
        return []


def delete_memories(user_id: str) -> None:
    """Wipe all long-term memories for a user."""
    if not MEM0_AVAILABLE or not _mem0:
        return
    try:
        _mem0.delete_all(user_id=user_id)
    except Exception as e:
        print(f"[memory] delete failed: {e}")

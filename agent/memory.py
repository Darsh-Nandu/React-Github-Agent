"""
agent/memory.py

Short-term memory  → SqliteSaver (per-session, persists across restarts)
Long-term memory   → Mem0 (cross-session, persists facts about users/projects)

Upgrade path:
    Swap SqliteSaver for RedisSaver for distributed / multi-instance deployments.
    Mem0 auto-upgrades to a vector store if OPENAI_API_KEY is set.
"""

import os
import time
from difflib import SequenceMatcher

# Short-term memory

from langgraph.checkpoint.memory import MemorySaver

def get_short_term_memory():
    return MemorySaver()


# Long-term memory using Mem0
try:
    from mem0 import Memory as Mem0Memory

    _mem0_config: dict = {}

    if os.getenv("OPENAI_API_KEY"):
        _mem0_config = {
            "llm": {"provider": "openai", "config": {"model": "gpt-4o-mini"}},
            "embedder": {
                "provider": "openai",
                "config": {"model": "text-embedding-3-small"},
            },
        }

    _mem0 = Mem0Memory.from_config(_mem0_config) if _mem0_config else Mem0Memory()
    MEM0_AVAILABLE = True

except Exception as e:
    print(f"[memory] Mem0 not available ({e}). Long-term memory disabled.")
    _mem0 = None
    MEM0_AVAILABLE = False


# Decay and deduplication config
MEMORY_DECAY_DAYS = int(os.getenv("MEMORY_DECAY_DAYS", "90"))
MEMORY_DEDUP_THRESHOLD = float(os.getenv("MEMORY_DEDUP_THRESHOLD", "0.85"))


def _is_duplicate(new: str, existing: list[str], threshold: float) -> bool:
    """Return True if new memory is too similar to any existing memory."""
    for mem in existing:
        ratio = SequenceMatcher(None, new.lower(), mem.lower()).ratio()
        if ratio >= threshold:
            return True
    return False


# Public API


def save_memory(user_id: str, content: str) -> None:
    """Persist a fact to long-term memory, skipping duplicates."""
    if not MEM0_AVAILABLE or not _mem0:
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "memories.txt")
        with open(path, "a") as f:
            f.write(f"{content}\n")
        return
    try:
        existing = recall_memories(user_id=user_id, query=content, top_k=10)
        if _is_duplicate(content, existing, MEMORY_DEDUP_THRESHOLD):
            print(f"[memory] Skipping duplicate: {content[:60]}")
            return
        _mem0.add(content, user_id=user_id, metadata={"created_at": time.time()})
    except Exception as e:
        print(f"[memory] save failed: {e}")


def recall_memories(user_id: str, query: str, top_k: int = 5) -> list[str]:
    """Retrieve the most relevant long-term memories for the current query."""
    if not MEM0_AVAILABLE or not _mem0:
        return []
    try:
        results = _mem0.search(query, user_id=user_id, limit=top_k)
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


def prune_stale_memories(user_id: str) -> int:
    """
    Remove memories older than MEMORY_DECAY_DAYS.
    Returns the number of pruned entries.
    """
    if not MEM0_AVAILABLE or not _mem0:
        return 0
    try:
        cutoff = time.time() - MEMORY_DECAY_DAYS * 86400
        all_mems = _mem0.get_all(user_id=user_id)
        pruned = 0
        for entry in all_mems:
            created = entry.get("metadata", {}).get("created_at", time.time())
            if created < cutoff:
                _mem0.delete(entry["id"])
                pruned += 1
        if pruned:
            print(f"[memory] Pruned {pruned} stale memories for {user_id}")
        return pruned
    except Exception as e:
        print(f"[memory] prune failed: {e}")
        return 0

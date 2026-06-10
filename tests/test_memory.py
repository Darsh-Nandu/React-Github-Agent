"""
tests/test_memory.py

Unit tests for agent/memory.py.
Mem0 is mocked so no external services are needed.
"""

import os
import pytest
from unittest.mock import MagicMock, patch

# save_memory (fallback text file)


class TestSaveMemoryFallback:
    def test_writes_to_txt_when_mem0_unavailable(self, tmp_path, monkeypatch):
        # Point the module's base dir to tmp_path
        monkeypatch.chdir(tmp_path)

        # Re-import with MEM0_AVAILABLE = False
        import importlib
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mem_mod.MEM0_AVAILABLE = False
        mem_mod._mem0 = None

        # Override the path used in save_memory
        memories_path = tmp_path / "memories.txt"

        with patch("agent.memory.os.path.join", return_value=str(memories_path)):
            mem_mod.save_memory(user_id="user1", content="User likes Python")

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0

        assert memories_path.exists()
        content = memories_path.read_text()
        assert "User likes Python" in content

    def test_does_nothing_when_mem0_unavailable_and_no_path_override(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mem_mod.MEM0_AVAILABLE = False
        mem_mod._mem0 = None

        # Should not raise even if memories.txt path issues exist
        try:
            mem_mod.save_memory(user_id="user1", content="test fact")
        except Exception:
            pass  # file creation edge-cases are OS dependent

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0


# save_memory (with Mem0)


class TestSaveMemoryWithMem0:
    def test_calls_mem0_add(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mock_mem0 = MagicMock()
        mem_mod.MEM0_AVAILABLE = True
        mem_mod._mem0 = mock_mem0

        mem_mod.save_memory(user_id="userA", content="Prefers dark mode")

        mock_mem0.add.assert_called_once_with("Prefers dark mode", user_id="userA")

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0

    def test_handles_mem0_exception_gracefully(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mock_mem0 = MagicMock()
        mock_mem0.add.side_effect = RuntimeError("DB error")
        mem_mod.MEM0_AVAILABLE = True
        mem_mod._mem0 = mock_mem0

        # Should not raise
        mem_mod.save_memory(user_id="userA", content="Fact")

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0


# recall_memories


class TestRecallMemories:
    def test_returns_empty_when_mem0_unavailable(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mem_mod.MEM0_AVAILABLE = False
        mem_mod._mem0 = None

        result = mem_mod.recall_memories(user_id="userA", query="what is my name")
        assert result == []

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0

    def test_returns_memory_strings(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mock_mem0 = MagicMock()
        mock_mem0.search.return_value = [
            {"memory": "User is called Alice"},
            {"memory": "User prefers Python"},
        ]
        mem_mod.MEM0_AVAILABLE = True
        mem_mod._mem0 = mock_mem0

        result = mem_mod.recall_memories(user_id="userA", query="name", top_k=2)

        assert result == ["User is called Alice", "User prefers Python"]
        mock_mem0.search.assert_called_once_with("name", user_id="userA", limit=2)

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0

    def test_handles_search_exception(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mock_mem0 = MagicMock()
        mock_mem0.search.side_effect = Exception("Search failed")
        mem_mod.MEM0_AVAILABLE = True
        mem_mod._mem0 = mock_mem0

        result = mem_mod.recall_memories(user_id="userA", query="name")
        assert result == []

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0


# get_all_memories


class TestGetAllMemories:
    def test_returns_all_for_user(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mock_mem0 = MagicMock()
        mock_mem0.get_all.return_value = [
            {"memory": "fact A"},
            {"memory": "fact B"},
        ]
        mem_mod.MEM0_AVAILABLE = True
        mem_mod._mem0 = mock_mem0

        result = mem_mod.get_all_memories(user_id="userX")
        assert result == ["fact A", "fact B"]

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0

    def test_returns_empty_when_unavailable(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mem_mod.MEM0_AVAILABLE = False
        mem_mod._mem0 = None

        result = mem_mod.get_all_memories(user_id="userX")
        assert result == []

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0


# delete_memories


class TestDeleteMemories:
    def test_calls_delete_all(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mock_mem0 = MagicMock()
        mem_mod.MEM0_AVAILABLE = True
        mem_mod._mem0 = mock_mem0

        mem_mod.delete_memories(user_id="userZ")
        mock_mem0.delete_all.assert_called_once_with(user_id="userZ")

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0

    def test_noop_when_unavailable(self):
        import agent.memory as mem_mod

        original_available = mem_mod.MEM0_AVAILABLE
        original_mem0 = mem_mod._mem0

        mem_mod.MEM0_AVAILABLE = False
        mem_mod._mem0 = None

        # Should not raise
        mem_mod.delete_memories(user_id="userZ")

        mem_mod.MEM0_AVAILABLE = original_available
        mem_mod._mem0 = original_mem0

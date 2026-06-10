"""
tests/conftest.py

Shared pytest fixtures and configuration.
"""

import os
import sys
import pytest

# Ensure project root is on path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def clear_env_vars(monkeypatch):
    """
    Ensure tests start with a clean slate for critical env vars.
    Individual tests can set these via monkeypatch.setenv().
    """
    # Don't clear by default - just provide a safe GITHUB_TOKEN so imports succeed
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token_do_not_use")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test_key_do_not_use")

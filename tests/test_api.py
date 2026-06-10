"""
tests/test_api.py

Integration tests for main.py FastAPI endpoints.
The agent, memory functions, and auth are mocked so no LLM calls are made.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from auth import TokenData

MOCK_USER = TokenData(user_id="test-user-id", username="testuser")


@pytest.fixture(autouse=True)
def mock_agent_build(monkeypatch):
    mock_agent = MagicMock()
    build_mock = AsyncMock(return_value=mock_agent)
    monkeypatch.setattr("agent.graph.build_agent", build_mock)
    return mock_agent


@pytest.fixture
def client(mock_agent_build):
    import main as app_module

    with patch("main.build_agent", AsyncMock(return_value=mock_agent_build)):
        app_module._agent = mock_agent_build
        with TestClient(app_module.app, raise_server_exceptions=True) as c:
            app_module._agent = mock_agent_build
            yield c


def auth_headers():
    return {"Authorization": "Bearer fake-test-token"}


def override_auth(app):
    from main import app as fastapi_app
    from auth import get_current_user

    fastapi_app.dependency_overrides[get_current_user] = lambda: MOCK_USER


# Health


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_agent_ready_field_present(self, client):
        assert "agent_ready" in client.get("/health").json()


# Auth


class TestAuth:
    def setup_method(self):
        import auth

        auth._users.clear()

    def test_register_returns_token(self, client):
        resp = client.post(
            "/auth/register", json={"username": "newuser", "password": "pass123"}
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_after_register(self, client):
        client.post(
            "/auth/register", json={"username": "loginuser", "password": "pass456"}
        )
        resp = client.post(
            "/auth/login", json={"username": "loginuser", "password": "pass456"}
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, client):
        client.post("/auth/register", json={"username": "user2", "password": "correct"})
        resp = client.post(
            "/auth/login", json={"username": "user2", "password": "wrong"}
        )
        assert resp.status_code == 401

    def test_duplicate_register(self, client):
        client.post("/auth/register", json={"username": "dupuser", "password": "pass"})
        resp = client.post(
            "/auth/register", json={"username": "dupuser", "password": "pass"}
        )
        assert resp.status_code == 400


# Chat


class TestChat:
    def test_chat_returns_response(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER

        with patch("main.run_agent", AsyncMock(return_value="Hello from agent!")):
            resp = client.post("/chat", json={"message": "Hi there"})

        app_module.app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["response"] == "Hello from agent!"

    def test_chat_generates_session_id(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER

        with patch("main.run_agent", AsyncMock(return_value="OK")):
            resp = client.post("/chat", json={"message": "test"})

        app_module.app.dependency_overrides.clear()
        assert isinstance(resp.json()["session_id"], str)

    def test_chat_uses_provided_session_id(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER

        with patch("main.run_agent", AsyncMock(return_value="OK")):
            resp = client.post(
                "/chat", json={"message": "hello", "session_id": "my-session-123"}
            )

        app_module.app.dependency_overrides.clear()
        assert resp.json()["session_id"] == "my-session-123"

    def test_chat_503_when_agent_not_ready(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER
        original = app_module._agent
        app_module._agent = None

        resp = client.post("/chat", json={"message": "Hi"})
        app_module._agent = original
        app_module.app.dependency_overrides.clear()
        assert resp.status_code == 503

    def test_chat_passes_active_repo(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER
        captured = {}

        async def capture(**kwargs):
            captured.update(kwargs)
            return "done"

        with patch("main.run_agent", side_effect=capture):
            client.post(
                "/chat",
                json={
                    "message": "test",
                    "active_repo": "owner/repo",
                    "active_branch": "dev",
                },
            )

        app_module.app.dependency_overrides.clear()
        assert captured.get("active_repo") == "owner/repo"
        assert captured.get("active_branch") == "dev"


# Memories


class TestMemories:
    def test_get_memories(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER

        with patch("main.get_all_memories", return_value=["fact A", "fact B"]):
            resp = client.get("/memories")

        app_module.app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["memories"] == ["fact A", "fact B"]

    def test_delete_memories(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER

        with patch("main.delete_memories") as mock_del:
            resp = client.delete("/memories")

        app_module.app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["status"] == "cleared"
        mock_del.assert_called_once_with(user_id=MOCK_USER.user_id)

    def test_prune_memories(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER

        with patch("main.prune_stale_memories", return_value=3) as mock_prune:
            resp = client.delete("/memories/prune")

        app_module.app.dependency_overrides.clear()
        assert resp.status_code == 200
        assert resp.json()["count"] == 3

    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/memories")
        assert resp.status_code == 401


# Validation


class TestChatRequestValidation:
    def test_message_required(self, client):
        import main as app_module
        from auth import get_current_user

        app_module.app.dependency_overrides[get_current_user] = lambda: MOCK_USER

        resp = client.post("/chat", json={"active_repo": "owner/repo"})
        app_module.app.dependency_overrides.clear()
        assert resp.status_code == 422

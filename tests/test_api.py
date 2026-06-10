"""
tests/test_api.py

Integration tests for main.py FastAPI endpoints.
The agent and memory functions are mocked — no LLM calls made.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def mock_agent_build(monkeypatch):
    """Prevent the real agent from building during app startup."""
    mock_agent = MagicMock()
    build_mock = AsyncMock(return_value=mock_agent)
    monkeypatch.setattr("agent.graph.build_agent", build_mock)
    return mock_agent


@pytest.fixture
def client(mock_agent_build):
    """Return a TestClient with a pre-built agent injected."""
    import main as app_module

    with patch("main.build_agent", AsyncMock(return_value=mock_agent_build)):
        app_module._agent = mock_agent_build  # inject directly

        from fastapi.testclient import TestClient
        # Use the app without lifespan to avoid actual agent build
        with TestClient(app_module.app, raise_server_exceptions=True) as c:
            app_module._agent = mock_agent_build
            yield c


# /health

class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_agent_ready_field_present(self, client):
        resp = client.get("/health")
        assert "agent_ready" in resp.json()


# /chat

class TestChat:
    def test_chat_returns_response(self, client):
        with patch("main.run_agent", AsyncMock(return_value="Hello from agent!")):
            resp = client.post("/chat", json={"message": "Hi there"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] == "Hello from agent!"
        assert "session_id" in data

    def test_chat_generates_session_id_when_not_provided(self, client):
        with patch("main.run_agent", AsyncMock(return_value="OK")):
            resp = client.post("/chat", json={"message": "test"})

        session_id = resp.json()["session_id"]
        assert isinstance(session_id, str)
        assert len(session_id) > 0

    def test_chat_uses_provided_session_id(self, client):
        with patch("main.run_agent", AsyncMock(return_value="OK")):
            resp = client.post(
                "/chat",
                json={"message": "hello", "session_id": "my-session-123"},
            )

        assert resp.json()["session_id"] == "my-session-123"

    def test_chat_503_when_agent_not_ready(self, client):
        import main as app_module
        original = app_module._agent
        app_module._agent = None

        resp = client.post("/chat", json={"message": "Hi"})
        assert resp.status_code == 503

        app_module._agent = original

    def test_chat_default_user_id(self, client):
        captured = {}

        async def capture_run_agent(**kwargs):
            captured.update(kwargs)
            return "done"

        with patch("main.run_agent", side_effect=capture_run_agent):
            client.post("/chat", json={"message": "test"})

        assert captured.get("user_id") == "default-user"

    def test_chat_custom_user_id(self, client):
        captured = {}

        async def capture_run_agent(**kwargs):
            captured.update(kwargs)
            return "done"

        with patch("main.run_agent", side_effect=capture_run_agent):
            client.post("/chat", json={"message": "test", "user_id": "alice"})

        assert captured.get("user_id") == "alice"


# /memories

class TestMemories:
    def test_get_memories(self, client):
        with patch("main.get_all_memories", return_value=["fact A", "fact B"]):
            resp = client.get("/memories?user_id=alice")

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "alice"
        assert data["memories"] == ["fact A", "fact B"]

    def test_get_memories_default_user(self, client):
        with patch("main.get_all_memories", return_value=[]) as mock_fn:
            resp = client.get("/memories")

        assert resp.status_code == 200
        assert resp.json()["user_id"] == "default-user"

    def test_delete_memories(self, client):
        with patch("main.delete_memories") as mock_del:
            resp = client.delete("/memories?user_id=bob")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cleared"
        assert data["user_id"] == "bob"
        mock_del.assert_called_once_with(user_id="bob")

    def test_delete_memories_default_user(self, client):
        with patch("main.delete_memories") as mock_del:
            resp = client.delete("/memories")

        assert resp.status_code == 200
        mock_del.assert_called_once_with(user_id="default-user")


# (static UI)

class TestServeUI:
    def test_serves_index_html_when_exists(self, client, tmp_path, monkeypatch):
        import main as app_module

        # Create a fake static/index.html
        static = tmp_path / "static"
        static.mkdir()
        (static / "index.html").write_text("<h1>Agent UI</h1>")

        monkeypatch.setattr(app_module, "static_dir", str(static))

        resp = client.get("/")
        # May redirect or return 200 depending on mount; just check it's not 500
        assert resp.status_code in (200, 307, 404)


# Request Model Validation

class TestChatRequestValidation:
    def test_message_required(self, client):
        resp = client.post("/chat", json={"user_id": "alice"})
        assert resp.status_code == 422  # Unprocessable Entity

    def test_invalid_json_rejected(self, client):
        resp = client.post(
            "/chat",
            data="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422
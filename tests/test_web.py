"""Tests for Web GUI backend API."""

import json

import pytest

from lightbox.core import Session
from lightbox.storage import read_events


@pytest.fixture
def app(temp_lightbox_dir):
    """Create a test Flask app."""
    from lightbox.web.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return app.test_client()


@pytest.fixture
def sample_session(temp_lightbox_dir):
    """Create a sample session with events."""
    session = Session(session_id="test_web_session")
    session.emit("search_web", {"query": "weather"}, {"result": "Sunny, 72F"})
    session.emit("read_file", {"path": "/tmp/test.txt"}, {"content": "hello"})
    session.emit(
        "api_call",
        {"url": "https://api.example.com"},
        {},
        status="error",
        error={"type": "ConnectionError", "message": "Connection refused"},
    )
    return "test_web_session"


class TestIndexPage:
    """Tests for the index page."""

    def test_serves_index_html(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert b"Lightbox Dashboard" in res.data


class TestSessionsAPI:
    """Tests for /api/sessions endpoint."""

    def test_empty_sessions_list(self, client):
        res = client.get("/api/sessions")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data == []

    def test_lists_sessions(self, client, sample_session):
        res = client.get("/api/sessions")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) == 1
        assert data[0]["session_id"] == "test_web_session"
        assert data[0]["event_count"] == 3

    def test_lists_multiple_sessions(self, client, temp_lightbox_dir):
        Session(session_id="session_a").emit("tool1", {"x": "1"}, {"y": "2"})
        Session(session_id="session_b").emit("tool2", {"x": "1"}, {"y": "2"})

        res = client.get("/api/sessions")
        data = json.loads(res.data)
        assert len(data) == 2
        session_ids = {s["session_id"] for s in data}
        assert "session_a" in session_ids
        assert "session_b" in session_ids


class TestSessionDetailAPI:
    """Tests for /api/sessions/<id> endpoint."""

    def test_returns_session_with_events(self, client, sample_session):
        res = client.get(f"/api/sessions/{sample_session}")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["session_id"] == "test_web_session"
        assert len(data["events"]) == 3
        assert data["events"][0]["tool"] == "search_web"
        assert data["events"][1]["tool"] == "read_file"
        assert data["events"][2]["tool"] == "api_call"

    def test_404_for_missing_session(self, client):
        res = client.get("/api/sessions/nonexistent")
        assert res.status_code == 404
        data = json.loads(res.data)
        assert "error" in data


class TestSessionEventsAPI:
    """Tests for /api/sessions/<id>/events endpoint."""

    def test_returns_all_events(self, client, sample_session):
        res = client.get(f"/api/sessions/{sample_session}/events")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) == 3

    def test_returns_events_since_index(self, client, sample_session):
        res = client.get(f"/api/sessions/{sample_session}/events?since=2")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) == 1
        assert data[0]["tool"] == "api_call"

    def test_returns_empty_when_since_past_end(self, client, sample_session):
        res = client.get(f"/api/sessions/{sample_session}/events?since=10")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert len(data) == 0

    def test_404_for_missing_session(self, client):
        res = client.get("/api/sessions/nonexistent/events")
        assert res.status_code == 404


class TestVerifyAPI:
    """Tests for /api/sessions/<id>/verify endpoint."""

    def test_verifies_valid_session(self, client, sample_session):
        res = client.post(f"/api/sessions/{sample_session}/verify")
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["status"] == "VALID"
        assert data["valid"] is True
        assert data["event_count"] == 3

    def test_verifies_tampered_session(self, client, sample_session, temp_lightbox_dir):
        # Tamper with the events file
        events_file = temp_lightbox_dir / "sessions" / sample_session / "events.jsonl"
        lines = events_file.read_text().splitlines()
        # Modify first line to break the hash
        tampered = lines[0].replace('"search_web"', '"tampered_tool"')
        lines[0] = tampered
        events_file.write_text("\n".join(lines) + "\n")

        res = client.post(f"/api/sessions/{sample_session}/verify")
        data = json.loads(res.data)
        assert data["status"] == "TAMPERED"
        assert data["valid"] is False

    def test_404_for_missing_session(self, client):
        res = client.post("/api/sessions/nonexistent/verify")
        assert res.status_code == 404


class TestRecordAPI:
    """Tests for /api/record endpoint."""

    def test_records_tool_call(self, client, temp_lightbox_dir):
        res = client.post("/api/record", json={
            "tool": "search_web",
            "input": {"query": "weather"},
            "output": {"result": "Sunny"},
            "session_id": "test_record_api",
        })
        assert res.status_code == 200
        data = json.loads(res.data)
        assert data["status"] == "recorded"
        assert data["session_id"] == "test_record_api"
        assert data["tool"] == "search_web"

        events = read_events("test_record_api")
        assert len(events) == 1
        assert events[0].tool == "search_web"
        assert events[0].status == "complete"

    def test_records_multiple_to_same_session(self, client, temp_lightbox_dir):
        for tool in ["tool_a", "tool_b", "tool_c"]:
            client.post("/api/record", json={
                "tool": tool,
                "input": {"x": "1"},
                "output": {"y": "2"},
                "session_id": "test_multi_record",
            })

        events = read_events("test_multi_record")
        assert len(events) == 3
        assert [e.tool for e in events] == ["tool_a", "tool_b", "tool_c"]

    def test_records_error_status(self, client, temp_lightbox_dir):
        res = client.post("/api/record", json={
            "tool": "failing_tool",
            "input": {},
            "output": {},
            "session_id": "test_record_error",
            "status": "error",
            "error": {"type": "TimeoutError", "message": "Timed out"},
        })
        assert res.status_code == 200

        events = read_events("test_record_error")
        assert events[0].status == "error"
        assert events[0].error == {"type": "TimeoutError", "message": "Timed out"}

    def test_auto_generates_session_id(self, client, temp_lightbox_dir):
        res = client.post("/api/record", json={
            "tool": "some_tool",
            "input": {},
            "output": {},
        })
        data = json.loads(res.data)
        assert data["status"] == "recorded"
        assert data["session_id"].startswith("session_")

    def test_rejects_missing_tool(self, client):
        res = client.post("/api/record", json={"input": {}, "output": {}})
        assert res.status_code == 400

    def test_rejects_non_json(self, client):
        res = client.post("/api/record", data="not json",
                          content_type="text/plain")
        assert res.status_code in (400, 415)

    def test_hash_chain_valid_after_recording(self, client, temp_lightbox_dir):
        for i in range(5):
            client.post("/api/record", json={
                "tool": f"tool_{i}",
                "input": {"i": str(i)},
                "output": {"ok": True},
                "session_id": "test_chain",
            })

        res = client.post("/api/sessions/test_chain/verify")
        data = json.loads(res.data)
        assert data["valid"] is True
        assert data["event_count"] == 5


class TestStreamAPI:
    """Tests for /api/sessions/<id>/stream SSE endpoint."""

    def test_stream_connects(self, client, sample_session):
        res = client.get(f"/api/sessions/{sample_session}/stream")
        assert res.status_code == 200
        assert res.content_type.startswith("text/event-stream")
        # Read first chunk (connected message)
        data = next(res.response)
        decoded = data.decode("utf-8") if isinstance(data, bytes) else data
        assert "connected" in decoded

    def test_404_for_missing_session_stream(self, client):
        res = client.get("/api/sessions/nonexistent/stream")
        assert res.status_code == 404

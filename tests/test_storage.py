"""Tests for storage layer."""

import json
from pathlib import Path

from lightbox.models import Event, compute_hash
from lightbox.storage import (
    append_event,
    get_events_file,
    get_lightbox_dir,
    get_session_dir,
    get_session_info,
    get_sessions_dir,
    list_sessions,
    read_events,
    session_exists,
)


def make_event(session_id: str, invocation_num: int, prev_hash: str | None = None) -> Event:
    """Create a test event."""
    event = Event(
        schema_version="1",
        session_id=session_id,
        invocation_id=f"inv_{invocation_num:05d}",
        tool="test_tool",
        input={"num": invocation_num},
        output={"result": f"output_{invocation_num}"},
        status="complete",
        timestamp_start="2025-01-15T10:00:00.000+00:00",
        timestamp_end="2025-01-15T10:00:01.000+00:00",
        prev_hash=prev_hash,
        hash="",  # Will be computed
    )
    event.hash = compute_hash(event.to_dict_for_hashing())
    return event


class TestDirectoryFunctions:
    def test_get_lightbox_dir_default(self, monkeypatch):
        monkeypatch.delenv("LIGHTBOX_DIR", raising=False)
        result = get_lightbox_dir()
        assert result == Path.home() / ".lightbox"

    def test_get_lightbox_dir_from_env(self, monkeypatch):
        monkeypatch.setenv("LIGHTBOX_DIR", "/custom/path")
        result = get_lightbox_dir()
        assert result == Path("/custom/path")

    def test_get_sessions_dir(self, temp_lightbox_dir):
        result = get_sessions_dir()
        assert result == temp_lightbox_dir / "sessions"

    def test_get_session_dir(self, temp_lightbox_dir):
        result = get_session_dir("test_session")
        assert result == temp_lightbox_dir / "sessions" / "test_session"

    def test_get_events_file(self, temp_lightbox_dir):
        result = get_events_file("test_session")
        assert result == temp_lightbox_dir / "sessions" / "test_session" / "events.jsonl"


class TestAppendAndRead:
    def test_append_creates_directory(self, temp_lightbox_dir):
        event = make_event("new_session", 1)
        append_event("new_session", event)

        assert get_session_dir("new_session").exists()
        assert get_events_file("new_session").exists()

    def test_append_writes_jsonl(self, temp_lightbox_dir):
        event = make_event("test", 1)
        append_event("test", event)

        content = get_events_file("test").read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 1

        parsed = json.loads(lines[0])
        assert parsed["tool"] == "test_tool"

    def test_read_empty_session(self, temp_lightbox_dir):
        events = read_events("nonexistent")
        assert events == []

    def test_read_returns_events(self, temp_lightbox_dir):
        event1 = make_event("test", 1)
        event2 = make_event("test", 2, prev_hash=event1.hash)

        append_event("test", event1)
        append_event("test", event2)

        events = read_events("test")
        assert len(events) == 2
        assert events[0].invocation_id == "inv_00001"
        assert events[1].invocation_id == "inv_00002"

    def test_roundtrip_preserves_data(self, temp_lightbox_dir):
        original = Event(
            schema_version="1",
            session_id="test",
            invocation_id="inv_00001",
            tool="complex_tool",
            input={"nested": {"data": [1, 2, 3]}},
            output={"result": "success"},
            status="complete",
            timestamp_start="2025-01-15T10:00:00.000+00:00",
            timestamp_end="2025-01-15T10:00:01.000+00:00",
            prev_hash=None,
            hash="",
            actor="test_agent",
            error=None,
        )
        original.hash = compute_hash(original.to_dict_for_hashing())

        append_event("test", original)
        events = read_events("test")

        restored = events[0]
        assert restored.session_id == original.session_id
        assert restored.input == original.input
        assert restored.actor == original.actor


class TestListSessions:
    def test_empty_when_no_sessions(self, temp_lightbox_dir):
        assert list_sessions() == []

    def test_lists_sessions(self, temp_lightbox_dir):
        event1 = make_event("session_a", 1)
        event2 = make_event("session_b", 1)

        append_event("session_a", event1)
        append_event("session_b", event2)

        sessions = list_sessions()
        assert set(sessions) == {"session_a", "session_b"}

    def test_ignores_empty_directories(self, temp_lightbox_dir):
        # Create an empty session directory
        empty_dir = get_session_dir("empty_session")
        empty_dir.mkdir(parents=True)

        # Create a valid session
        event = make_event("valid_session", 1)
        append_event("valid_session", event)

        sessions = list_sessions()
        assert sessions == ["valid_session"]


class TestSessionExists:
    def test_false_when_not_exists(self, temp_lightbox_dir):
        assert not session_exists("nonexistent")

    def test_true_when_exists(self, temp_lightbox_dir):
        event = make_event("test", 1)
        append_event("test", event)
        assert session_exists("test")


class TestGetSessionInfo:
    def test_none_when_not_exists(self, temp_lightbox_dir):
        assert get_session_info("nonexistent") is None

    def test_returns_info(self, temp_lightbox_dir):
        event1 = make_event("test", 1)
        event2 = make_event("test", 2, prev_hash=event1.hash)

        append_event("test", event1)
        append_event("test", event2)

        info = get_session_info("test")
        assert info["session_id"] == "test"
        assert info["event_count"] == 2
        assert "tools_used" in info

"""Tests for core API."""

import pytest

from lightbox.core import (
    Session,
    emit,
    generate_invocation_id,
    generate_session_id,
    get_current_session,
    start_session,
)
from lightbox.integrity import verify_session
from lightbox.storage import read_events


@pytest.fixture
def reset_global_session(monkeypatch):
    """Reset the global session between tests."""
    import lightbox.core

    monkeypatch.setattr(lightbox.core, "_current_session", None)


class TestGenerators:
    def test_generate_session_id_format(self):
        sid = generate_session_id()
        assert sid.startswith("session_")
        assert len(sid) == 8 + 16  # "session_" (8 chars) + 16 hex chars

    def test_generate_session_id_unique(self):
        ids = {generate_session_id() for _ in range(100)}
        assert len(ids) == 100  # All unique

    def test_generate_invocation_id_format(self):
        inv_id = generate_invocation_id(1)
        assert inv_id == "inv_00001"

        inv_id = generate_invocation_id(42)
        assert inv_id == "inv_00042"

        inv_id = generate_invocation_id(99999)
        assert inv_id == "inv_99999"


class TestSession:
    def test_creates_unique_session_id(self, temp_lightbox_dir):
        s1 = Session()
        s2 = Session()
        assert s1.session_id != s2.session_id

    def test_accepts_custom_session_id(self, temp_lightbox_dir):
        session = Session("my_custom_id")
        assert session.session_id == "my_custom_id"

    def test_emit_returns_event(self, temp_lightbox_dir):
        session = Session()
        event = session.emit(
            "test_tool",
            {"arg": "value"},
            {"result": "success"},
        )

        assert event.session_id == session.session_id
        assert event.tool == "test_tool"
        assert event.input == {"arg": "value"}
        assert event.output == {"result": "success"}
        assert event.status == "complete"

    def test_emit_persists_event(self, temp_lightbox_dir):
        session = Session()
        session.emit("test_tool", {"x": 1}, {"y": 2})

        events = read_events(session.session_id)
        assert len(events) == 1
        assert events[0].tool == "test_tool"

    def test_emit_builds_hash_chain(self, temp_lightbox_dir):
        session = Session()
        e1 = session.emit("tool1", {}, {})
        e2 = session.emit("tool2", {}, {})
        e3 = session.emit("tool3", {}, {})

        assert e1.prev_hash is None
        assert e2.prev_hash == e1.hash
        assert e3.prev_hash == e2.hash

    def test_emit_chain_verifiable(self, temp_lightbox_dir):
        session = Session()
        for i in range(10):
            session.emit(f"tool_{i}", {"i": i}, {"result": i * 2})

        result = verify_session(session.session_id)
        assert result.valid
        assert result.event_count == 10

    def test_emit_pending_and_resolved(self, temp_lightbox_dir):
        session = Session()

        # Start async operation
        inv_id = session.emit_pending("async_tool", {"input": "data"})
        assert inv_id.startswith("inv_")

        # Complete it
        event = session.emit_resolved(inv_id, {"output": "result"})
        assert event.invocation_id == inv_id
        assert event.status == "complete"
        assert event.output == {"output": "result"}

    def test_emit_pending_then_error(self, temp_lightbox_dir):
        session = Session()

        inv_id = session.emit_pending("failing_tool", {})
        event = session.emit_resolved(
            inv_id,
            {},
            status="error",
            error={"message": "Something went wrong"},
        )

        assert event.status == "error"
        assert event.error == {"message": "Something went wrong"}

    def test_emit_resolved_unknown_id_raises(self, temp_lightbox_dir):
        session = Session()

        with pytest.raises(ValueError, match="Unknown invocation_id"):
            session.emit_resolved("inv_99999", {})

    def test_resume_existing_session(self, temp_lightbox_dir):
        # Create session with some events
        session1 = Session("resumable")
        session1.emit("tool1", {}, {})
        session1.emit("tool2", {}, {})

        # Resume it
        session2 = Session("resumable")
        e3 = session2.emit("tool3", {}, {})

        # Should continue the chain
        events = read_events("resumable")
        assert len(events) == 3
        assert e3.prev_hash == events[1].hash

    def test_emit_with_optional_fields(self, temp_lightbox_dir):
        session = Session()
        event = session.emit(
            "tool",
            {},
            {},
            actor="my_agent",
            parent_invocation="inv_00000",
            chunk_count=10,
            total_bytes=1024,
        )

        assert event.actor == "my_agent"
        assert event.parent_invocation == "inv_00000"
        assert event.chunk_count == 10
        assert event.total_bytes == 1024


class TestModuleLevelAPI:
    def test_emit_creates_session(self, temp_lightbox_dir, reset_global_session):
        assert get_current_session() is None

        event = emit("test", {}, {})

        assert get_current_session() is not None
        assert event.session_id == get_current_session().session_id

    def test_start_session(self, temp_lightbox_dir, reset_global_session):
        session = start_session("explicit_id")

        assert session.session_id == "explicit_id"
        assert get_current_session() is session

    def test_emit_uses_current_session(self, temp_lightbox_dir, reset_global_session):
        session = start_session()
        e1 = emit("tool1", {}, {})
        e2 = emit("tool2", {}, {})

        assert e1.session_id == session.session_id
        assert e2.session_id == session.session_id
        assert e2.prev_hash == e1.hash

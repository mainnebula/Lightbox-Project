"""Acceptance tests for Lightbox.

These tests verify the "done-done" criteria:
1. Tamper 1 byte in a prior event → verify fails at the correct index
2. Truncate last JSONL line → verify reports partial write (distinct from tamper)
3. Oversized output → stored as hash + size metadata, replay remains readable
4. LangChain tool raises → error recorded, session continues, replay shows failure cleanly
"""

import json

import pytest
from click.testing import CliRunner

from lightbox.cli import main
from lightbox.core import Session
from lightbox.integrity import VerifyStatus, verify_session
from lightbox.storage import (
    RedactionConfig,
    get_events_file,
    read_events,
)


@pytest.fixture
def runner():
    return CliRunner()


class TestTamperDetection:
    """Verify that tampering is detected at the correct index."""

    def test_tamper_single_byte_detected(self, temp_lightbox_dir):
        """Tamper 1 byte in a prior event → verify fails at the correct index."""
        # Create session with multiple events
        session = Session("tamper_test")
        session.emit("tool1", {"a": 1}, {"b": 2})
        session.emit("tool2", {"c": 3}, {"d": 4})
        session.emit("tool3", {"e": 5}, {"f": 6})

        # Tamper with event 1 (middle event)
        events_file = get_events_file("tamper_test")
        lines = events_file.read_text().strip().split("\n")

        # Change a single character in the second event
        event_data = json.loads(lines[1])
        event_data["input"]["c"] = 999  # Changed from 3 to 999
        lines[1] = json.dumps(event_data, separators=(",", ":"))

        events_file.write_text("\n".join(lines) + "\n")

        # Verify should fail at index 1
        result = verify_session("tamper_test")
        assert not result.valid
        assert result.status == VerifyStatus.TAMPERED
        assert result.error_index == 1
        assert "hash mismatch" in result.error_message.lower()

    def test_tamper_first_event(self, temp_lightbox_dir):
        """Tampering first event should fail at index 0."""
        session = Session("tamper_first")
        session.emit("tool1", {"x": 1}, {"y": 2})
        session.emit("tool2", {"x": 3}, {"y": 4})

        events_file = get_events_file("tamper_first")
        lines = events_file.read_text().strip().split("\n")

        event_data = json.loads(lines[0])
        event_data["tool"] = "hacked_tool"
        lines[0] = json.dumps(event_data, separators=(",", ":"))

        events_file.write_text("\n".join(lines) + "\n")

        result = verify_session("tamper_first")
        assert not result.valid
        assert result.error_index == 0


class TestTruncationDetection:
    """Verify truncation is distinct from tampering."""

    def test_truncated_line_detected(self, temp_lightbox_dir, runner):
        """Truncate last JSONL line → verify reports partial write."""
        session = Session("truncate_test")
        session.emit("tool1", {"a": 1}, {"b": 2})
        session.emit("tool2", {"c": 3}, {"d": 4})

        # Truncate the last line (simulate crash mid-write)
        events_file = get_events_file("truncate_test")
        content = events_file.read_text()
        # Remove last 50 characters and the trailing newline
        truncated = content[:-50]
        events_file.write_text(truncated)  # No trailing newline

        # Verify should report truncation, not tampering
        result = verify_session("truncate_test")
        assert not result.valid
        assert result.status == VerifyStatus.TRUNCATED
        assert "truncat" in result.error_message.lower()

    def test_truncation_cli_distinct_exit_code(self, temp_lightbox_dir, runner):
        """CLI should return exit code 2 for truncation."""
        session = Session("truncate_cli")
        session.emit("tool1", {}, {})

        events_file = get_events_file("truncate_cli")
        content = events_file.read_text()
        events_file.write_text(content[:-30])  # Truncate

        result = runner.invoke(main, ["verify", "truncate_cli"])
        assert result.exit_code == 2  # TRUNCATED, not 1 (TAMPERED)


class TestOversizedContent:
    """Verify oversized content is handled properly."""

    def test_oversized_output_redacted(self, temp_lightbox_dir):
        """Oversized output → stored as hash + size metadata."""
        config = RedactionConfig(
            max_inline_bytes=100,  # Very small for testing
            hash_oversized=True,
        )

        session = Session("oversize_test", redaction_config=config)

        # Create large output
        large_output = {"data": "x" * 200}  # > 100 bytes

        session.emit("big_tool", {"small": "input"}, large_output)

        # Read back and check
        events = read_events("oversize_test")
        assert len(events) == 1

        event = events[0]
        # Output should be redacted
        assert "_redacted" in str(event.output)
        # Content hash should be present
        assert event.content_hashes is not None
        assert any("output" in k for k in event.content_hashes)

    def test_oversized_replay_readable(self, temp_lightbox_dir, runner):
        """Replay with oversized content should show readable output."""
        config = RedactionConfig(max_inline_bytes=50, hash_oversized=True)
        session = Session("oversize_replay", redaction_config=config)
        session.emit("tool", {"x": 1}, {"big": "y" * 100})

        result = runner.invoke(main, ["replay", "oversize_replay", "--fast"])
        assert result.exit_code == 0
        assert "tool" in result.output
        # Should show something, not crash
        assert "REPLAY COMPLETE" in result.output or ">>> REPLAY COMPLETE" in result.output


class TestErrorRecording:
    """Verify errors are properly recorded."""

    def test_error_recorded_in_session(self, temp_lightbox_dir):
        """Error status and details are recorded."""
        session = Session("error_test")

        session.emit(
            "failing_tool",
            {"query": "test"},
            {},
            status="error",
            error={"type": "ValueError", "message": "Invalid input"},
        )

        events = read_events("error_test")
        assert len(events) == 1

        event = events[0]
        assert event.status == "error"
        assert event.error is not None
        assert event.error["type"] == "ValueError"

    def test_error_in_replay(self, temp_lightbox_dir, runner):
        """Replay shows failure clearly."""
        session = Session("error_replay")
        session.emit("good_tool", {}, {"ok": True})
        session.emit(
            "bad_tool",
            {},
            {},
            status="error",
            error={"message": "Something went wrong"},
        )
        session.emit("another_good", {}, {"ok": True})

        result = runner.invoke(main, ["replay", "error_replay", "--fast"])
        assert result.exit_code == 0
        # Error should be visible
        assert "Something went wrong" in result.output or "ERR" in result.output


class TestAsyncSemantics:
    """Verify async pending/resolved semantics."""

    def test_pending_resolved_chain(self, temp_lightbox_dir):
        """Pending and resolved events are both in the chain."""
        session = Session("async_test")

        inv_id = session.emit_pending("async_tool", {"input": "data"})
        session.emit_resolved(inv_id, {"result": "success"})

        events = read_events("async_test")
        assert len(events) == 2

        # First is pending
        assert events[0].status == "pending"
        assert events[0].output is None

        # Second is resolved with same invocation_id
        assert events[1].status == "complete"
        assert events[1].invocation_id == events[0].invocation_id

        # Chain should verify
        result = verify_session("async_test")
        assert result.valid

    def test_async_error_recorded(self, temp_lightbox_dir):
        """Async tool that fails records error properly."""
        session = Session("async_error")

        inv_id = session.emit_pending("failing_async", {"x": 1})
        session.emit_resolved(
            inv_id,
            {},
            status="error",
            error={"message": "Timeout"},
        )

        events = read_events("async_error")
        assert events[1].status == "error"
        assert events[1].error["message"] == "Timeout"


class TestRetrySemantics:
    """Verify retry semantics."""

    def test_retry_creates_new_invocation(self, temp_lightbox_dir):
        """Each retry is a new invocation_id with retry_of link."""
        session = Session("retry_test")

        # First attempt fails
        e1 = session.emit(
            "flaky_tool",
            {"x": 1},
            {},
            status="error",
            error={"message": "Failed"},
        )

        # Retry succeeds
        session.emit(
            "flaky_tool",
            {"x": 1},
            {"result": "ok"},
            retry_of=e1.invocation_id,
        )

        events = read_events("retry_test")
        assert len(events) == 2
        assert events[0].invocation_id != events[1].invocation_id
        assert events[1].retry_of == events[0].invocation_id

        # Both remain as evidence
        assert events[0].status == "error"
        assert events[1].status == "complete"


class TestSchemaVersion:
    """Verify schema versioning."""

    def test_events_have_schema_version(self, temp_lightbox_dir):
        """All events have schema_version field."""
        session = Session("schema_test")
        session.emit("tool", {}, {})

        events = read_events("schema_test")
        assert events[0].schema_version == "1"

    def test_session_metadata_has_version(self, temp_lightbox_dir):
        """Session metadata includes version info."""
        from lightbox.storage import read_session_metadata

        session = Session("meta_test")
        session.emit("tool", {}, {})

        meta = read_session_metadata("meta_test")
        assert meta is not None
        assert meta.schema_version == "1"
        assert meta.lightbox_version == "0.1.0"

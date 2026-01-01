"""Tests for integrity verification."""

import json

from lightbox.integrity import VerificationResult, VerifyStatus, verify_event, verify_session
from lightbox.models import Event, compute_hash
from lightbox.storage import append_event, get_events_file


def make_chained_events(session_id: str, count: int) -> list[Event]:
    """Create a chain of properly linked events."""
    events = []
    prev_hash = None

    for i in range(count):
        event = Event(
            schema_version="1",
            session_id=session_id,
            invocation_id=f"inv_{i + 1:05d}",
            tool=f"tool_{i + 1}",
            input={"num": i + 1},
            output={"result": f"output_{i + 1}"},
            status="complete",
            timestamp_start=f"2025-01-15T10:{i:02d}:00.000+00:00",
            timestamp_end=f"2025-01-15T10:{i:02d}:01.000+00:00",
            prev_hash=prev_hash,
            hash="",
        )
        event.hash = compute_hash(event.to_dict_for_hashing())
        events.append(event)
        prev_hash = event.hash

    return events


class TestVerifyEvent:
    def test_valid_event(self):
        event = Event(
            schema_version="1",
            session_id="test",
            invocation_id="inv_00001",
            tool="test",
            input={},
            output={},
            status="complete",
            timestamp_start="2025-01-15T10:00:00.000+00:00",
            timestamp_end="2025-01-15T10:00:01.000+00:00",
            prev_hash=None,
            hash="",
        )
        event.hash = compute_hash(event.to_dict_for_hashing())

        is_valid, error = verify_event(event, None)
        assert is_valid
        assert error is None

    def test_invalid_hash(self):
        event = Event(
            schema_version="1",
            session_id="test",
            invocation_id="inv_00001",
            tool="test",
            input={},
            output={},
            status="complete",
            timestamp_start="2025-01-15T10:00:00.000+00:00",
            timestamp_end="2025-01-15T10:00:01.000+00:00",
            prev_hash=None,
            hash="wrong_hash",
        )

        is_valid, error = verify_event(event, None)
        assert not is_valid
        assert "Hash mismatch" in error

    def test_wrong_prev_hash(self):
        event = Event(
            schema_version="1",
            session_id="test",
            invocation_id="inv_00001",
            tool="test",
            input={},
            output={},
            status="complete",
            timestamp_start="2025-01-15T10:00:00.000+00:00",
            timestamp_end="2025-01-15T10:00:01.000+00:00",
            prev_hash="wrong_prev",
            hash="",
        )
        event.hash = compute_hash(event.to_dict_for_hashing())

        # Verify against expected prev_hash of None
        is_valid, error = verify_event(event, None)
        assert not is_valid
        assert "Chain break" in error


class TestVerifySession:
    def test_nonexistent_session(self, temp_lightbox_dir):
        result = verify_session("nonexistent")
        assert not result.valid
        assert result.status == VerifyStatus.NOT_FOUND
        assert "not found" in result.error_message

    def test_empty_session_is_valid(self, temp_lightbox_dir):
        # Create empty session directory
        events_file = get_events_file("empty")
        events_file.parent.mkdir(parents=True)
        events_file.touch()

        result = verify_session("empty")
        assert result.valid
        assert result.event_count == 0

    def test_valid_chain(self, temp_lightbox_dir):
        events = make_chained_events("valid", 5)
        for event in events:
            append_event("valid", event)

        result = verify_session("valid")
        assert result.valid
        assert result.event_count == 5

    def test_detects_tampered_content(self, temp_lightbox_dir):
        events = make_chained_events("tampered", 3)
        for event in events:
            append_event("tampered", event)

        # Tamper with the file
        events_file = get_events_file("tampered")
        lines = events_file.read_text().strip().split("\n")

        # Modify the second event's input
        event_data = json.loads(lines[1])
        event_data["input"]["num"] = 999  # Changed!
        lines[1] = json.dumps(event_data)

        events_file.write_text("\n".join(lines) + "\n")

        result = verify_session("tampered")
        assert not result.valid
        assert result.status == VerifyStatus.TAMPERED
        assert result.error_index == 1
        assert "hash mismatch" in result.error_message.lower()

    def test_detects_broken_chain(self, temp_lightbox_dir):
        events = make_chained_events("broken", 3)
        for event in events:
            append_event("broken", event)

        # Tamper with prev_hash
        events_file = get_events_file("broken")
        lines = events_file.read_text().strip().split("\n")

        event_data = json.loads(lines[2])
        event_data["prev_hash"] = "wrong_hash"
        # Recompute hash so it matches the content (but chain is broken)
        event_data["hash"] = compute_hash({k: v for k, v in event_data.items() if k != "hash"})
        lines[2] = json.dumps(event_data)

        events_file.write_text("\n".join(lines) + "\n")

        result = verify_session("broken")
        assert not result.valid
        assert result.status == VerifyStatus.TAMPERED
        assert result.error_index == 2
        assert "chain break" in result.error_message.lower()

    def test_single_event_valid(self, temp_lightbox_dir):
        events = make_chained_events("single", 1)
        append_event("single", events[0])

        result = verify_session("single")
        assert result.valid
        assert result.event_count == 1


class TestVerificationResult:
    def test_bool_conversion(self):
        valid = VerificationResult(status=VerifyStatus.VALID, valid=True, event_count=5)
        invalid = VerificationResult(
            status=VerifyStatus.TAMPERED, valid=False, event_count=5, error_message="test"
        )

        assert bool(valid) is True
        assert bool(invalid) is False

        # Can use in if statements
        assert valid  # Truthy check

    def test_exit_code(self):
        valid = VerificationResult(status=VerifyStatus.VALID, valid=True, event_count=5)
        tampered = VerificationResult(status=VerifyStatus.TAMPERED, valid=False, event_count=5)
        truncated = VerificationResult(status=VerifyStatus.TRUNCATED, valid=False, event_count=5)

        assert valid.exit_code == 0
        assert tampered.exit_code == 1
        assert truncated.exit_code == 2

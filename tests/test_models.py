"""Tests for Event model and serialization."""

from lightbox.models import (
    Event,
    canonical_serialize,
    compute_hash,
    now_iso,
)


def make_event(**overrides) -> Event:
    """Create a test event with defaults."""
    defaults = {
        "schema_version": "1",
        "session_id": "session_test123",
        "invocation_id": "inv_00001",
        "tool": "test_tool",
        "input": {"arg": "value"},
        "output": {"result": "success"},
        "status": "complete",
        "timestamp_start": "2025-01-15T10:00:00.000+00:00",
        "timestamp_end": "2025-01-15T10:00:01.000+00:00",
        "prev_hash": None,
        "hash": "abc123",
    }
    defaults.update(overrides)
    return Event(**defaults)


class TestCanonicalSerialize:
    def test_sorts_keys(self):
        obj = {"z": 1, "a": 2, "m": 3}
        result = canonical_serialize(obj)
        assert result == '{"a":2,"m":3,"z":1}'

    def test_no_whitespace(self):
        obj = {"key": "value", "nested": {"inner": [1, 2, 3]}}
        result = canonical_serialize(obj)
        assert " " not in result
        assert "\n" not in result

    def test_nested_sorting(self):
        obj = {"outer": {"z": 1, "a": 2}}
        result = canonical_serialize(obj)
        assert result == '{"outer":{"a":2,"z":1}}'

    def test_deterministic(self):
        obj = {"b": 2, "a": 1, "c": 3}
        # Multiple serializations should produce identical output
        results = [canonical_serialize(obj) for _ in range(100)]
        assert all(r == results[0] for r in results)


class TestComputeHash:
    def test_returns_hex_string(self):
        event_dict = {"tool": "test", "input": {}, "output": {}, "prev_hash": None}
        result = compute_hash(event_dict)
        assert isinstance(result, str)
        assert len(result) == 64  # SHA-256 produces 64 hex chars
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic(self):
        event_dict = {"tool": "test", "input": {"x": 1}, "output": {}, "prev_hash": None}
        hash1 = compute_hash(event_dict)
        hash2 = compute_hash(event_dict)
        assert hash1 == hash2

    def test_different_input_different_hash(self):
        dict1 = {"tool": "test", "input": {"x": 1}, "prev_hash": None}
        dict2 = {"tool": "test", "input": {"x": 2}, "prev_hash": None}
        assert compute_hash(dict1) != compute_hash(dict2)

    def test_prev_hash_affects_hash(self):
        base = {"tool": "test", "input": {}, "output": {}}
        hash1 = compute_hash({**base, "prev_hash": None})
        hash2 = compute_hash({**base, "prev_hash": "abc123"})
        assert hash1 != hash2


class TestEvent:
    def test_to_dict_includes_required_fields(self):
        event = make_event()
        d = event.to_dict()

        assert "session_id" in d
        assert "invocation_id" in d
        assert "tool" in d
        assert "input" in d
        assert "output" in d
        assert "status" in d
        assert "timestamp_start" in d
        assert "timestamp_end" in d
        assert "prev_hash" in d
        assert "hash" in d

    def test_to_dict_excludes_none_optional_fields(self):
        event = make_event()  # No optional fields set
        d = event.to_dict()

        assert "parent_invocation" not in d
        assert "actor" not in d
        assert "error" not in d

    def test_to_dict_includes_set_optional_fields(self):
        event = make_event(actor="test_agent", error={"msg": "oops"})
        d = event.to_dict()

        assert d["actor"] == "test_agent"
        assert d["error"] == {"msg": "oops"}

    def test_to_dict_for_hashing_excludes_hash(self):
        event = make_event(hash="should_be_excluded")
        d = event.to_dict_for_hashing()

        assert "hash" not in d
        assert "session_id" in d  # Other fields still present

    def test_from_dict_roundtrip(self):
        original = make_event(
            actor="agent1",
            parent_invocation="inv_00000",
            chunk_count=5,
        )
        d = original.to_dict()
        restored = Event.from_dict(d)

        assert restored.session_id == original.session_id
        assert restored.invocation_id == original.invocation_id
        assert restored.tool == original.tool
        assert restored.input == original.input
        assert restored.output == original.output
        assert restored.status == original.status
        assert restored.actor == original.actor
        assert restored.parent_invocation == original.parent_invocation
        assert restored.chunk_count == original.chunk_count


class TestNowIso:
    def test_returns_iso_format(self):
        result = now_iso()
        # Should be parseable as ISO format
        from datetime import datetime

        dt = datetime.fromisoformat(result.replace("Z", "+00:00"))
        assert dt is not None

    def test_includes_milliseconds(self):
        result = now_iso()
        # Should have milliseconds (3 digits after decimal)
        assert "." in result

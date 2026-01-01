"""Event model and serialization for Lightbox.

CANONICALIZATION INVARIANTS (must not change without version bump):
1. Keys sorted alphabetically at all nesting levels
2. No whitespace between elements (separators=(',', ':'))
3. UTF-8 encoding, no ASCII escaping (ensure_ascii=False)
4. Floats are prohibited in input/output - use strings for decimals
5. Strings are stored as-is (no Unicode normalization)
6. Null values serialized as JSON null
7. Hash covers ALL fields except 'hash' itself

See FORMAT.md for complete specification.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

# Schema version - bump this when canonicalization or event structure changes
SCHEMA_VERSION = "1"


def get_lightbox_version() -> str:
    """Get the package version from metadata."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("lightbox")
    except PackageNotFoundError:
        return "0.1.0"  # Fallback for development


# Computed at import time for convenience
LIGHTBOX_VERSION = get_lightbox_version()

EventStatus = Literal["pending", "complete", "error"]


class CanonicalizeError(Exception):
    """Raised when data cannot be safely canonicalized."""

    pass


def _check_no_floats(obj: Any, path: str = "") -> None:
    """Recursively check that no floats exist in the data structure.

    Floats are prohibited because:
    - IEEE 754 representation can vary across platforms
    - JSON serialization of floats is not deterministic (trailing zeros, etc.)
    - Use string representations for decimal values instead
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            raise CanonicalizeError(
                f"Float at '{path}' is NaN or Inf, which cannot be serialized deterministically"
            )
        raise CanonicalizeError(
            f"Float at '{path}' is not allowed. Use string representation for decimals. Got: {obj}"
        )
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _check_no_floats(v, f"{path}.{k}" if path else k)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _check_no_floats(v, f"{path}[{i}]")


@dataclass
class Event:
    """A single tool execution event in the Lightbox log.

    Required fields capture the essential information about what tool was called,
    with what inputs, and what the result was. Optional fields support advanced
    use cases like nested calls, actor tracking, and streaming.
    """

    # Required fields
    schema_version: str  # Always SCHEMA_VERSION
    session_id: str
    invocation_id: str
    tool: str
    input: dict[str, Any]
    output: dict[str, Any] | None
    status: EventStatus
    timestamp_start: str  # ISO 8601
    timestamp_end: str | None
    prev_hash: str | None
    hash: str

    # Optional fields
    parent_invocation: str | None = None
    actor: str | None = None
    originating_actor: str | None = None
    error: dict[str, Any] | None = None
    chunk_count: int | None = None
    total_bytes: int | None = None
    content_hashes: dict[str, str] | None = None
    retry_of: str | None = None  # Link to prior invocation_id if this is a retry
    canonical_output: Any | None = None  # Extracted semantic value from framework wrappers

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary, excluding None values for optional fields."""
        result = {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "invocation_id": self.invocation_id,
            "tool": self.tool,
            "input": self.input,
            "output": self.output,
            "status": self.status,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }
        # Add optional fields only if set
        if self.parent_invocation is not None:
            result["parent_invocation"] = self.parent_invocation
        if self.actor is not None:
            result["actor"] = self.actor
        if self.originating_actor is not None:
            result["originating_actor"] = self.originating_actor
        if self.error is not None:
            result["error"] = self.error
        if self.chunk_count is not None:
            result["chunk_count"] = self.chunk_count
        if self.total_bytes is not None:
            result["total_bytes"] = self.total_bytes
        if self.content_hashes is not None:
            result["content_hashes"] = self.content_hashes
        if self.retry_of is not None:
            result["retry_of"] = self.retry_of
        if self.canonical_output is not None:
            result["canonical_output"] = self.canonical_output
        return result

    def to_dict_for_hashing(self) -> dict[str, Any]:
        """Convert event to dictionary for hash computation (excludes 'hash' field)."""
        d = self.to_dict()
        del d["hash"]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        """Create an Event from a dictionary."""
        return cls(
            schema_version=data.get("schema_version", "1"),  # Default for v1 compat
            session_id=data["session_id"],
            invocation_id=data["invocation_id"],
            tool=data["tool"],
            input=data["input"],
            output=data["output"],
            status=data["status"],
            timestamp_start=data["timestamp_start"],
            timestamp_end=data["timestamp_end"],
            prev_hash=data["prev_hash"],
            hash=data["hash"],
            parent_invocation=data.get("parent_invocation"),
            actor=data.get("actor"),
            originating_actor=data.get("originating_actor"),
            error=data.get("error"),
            chunk_count=data.get("chunk_count"),
            total_bytes=data.get("total_bytes"),
            content_hashes=data.get("content_hashes"),
            retry_of=data.get("retry_of"),
            canonical_output=data.get("canonical_output"),
        )


def canonical_serialize(obj: dict[str, Any], check_floats: bool = True) -> str:
    """Serialize a dictionary to canonical JSON format.

    CANONICAL FORMAT INVARIANTS:
    1. Keys sorted alphabetically at all nesting levels (sort_keys=True)
    2. No whitespace between elements (separators=(',', ':'))
    3. UTF-8 encoding, no ASCII escaping (ensure_ascii=False)
    4. Floats prohibited (raises CanonicalizeError if check_floats=True)
    5. Strings stored as-is (no Unicode normalization applied)

    These invariants MUST NOT change without bumping SCHEMA_VERSION.

    Args:
        obj: Dictionary to serialize
        check_floats: If True, raise CanonicalizeError if floats are present

    Returns:
        Canonical JSON string

    Raises:
        CanonicalizeError: If floats are present and check_floats=True
    """
    if check_floats:
        _check_no_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(event_dict: dict[str, Any]) -> str:
    """Compute SHA-256 hash of an event dictionary.

    The event_dict should already include prev_hash but MUST exclude the 'hash' field.
    This is typically the output of Event.to_dict_for_hashing().

    Hash covers: ALL fields in the dict (which should be all fields except 'hash')
    """
    canonical = canonical_serialize(event_dict)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def compute_content_hash(content: bytes | str) -> str:
    """Compute SHA-256 hash of content for redaction/size-bound storage.

    Use this when storing hash + size instead of full content.
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass
class SessionMetadata:
    """Metadata stored at session level (meta.json)."""

    session_id: str
    schema_version: str
    lightbox_version: str
    created_at: str  # ISO 8601

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "schema_version": self.schema_version,
            "lightbox_version": self.lightbox_version,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMetadata:
        return cls(
            session_id=data["session_id"],
            schema_version=data.get("schema_version", "1"),
            lightbox_version=data.get("lightbox_version", "unknown"),
            created_at=data["created_at"],
        )

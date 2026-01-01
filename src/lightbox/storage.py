"""File-based storage layer for Lightbox events.

Events are stored as append-only JSONL files, one directory per session.
This design makes sessions portable (zip and share) and verifiable offline.

STORAGE LAYOUT:
    ~/.lightbox/sessions/<session_id>/
        events.jsonl     # Append-only event log (one JSON object per line)
        meta.json        # Session metadata (version info, created_at)

INTEGRITY NOTES:
    - Events are written atomically (single write + fsync)
    - File locking prevents concurrent corruption
    - Truncated last line (crash mid-write) is detectable and distinct from tamper
    - Ordering is append-order, NOT timestamp order
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lightbox.models import (
    LIGHTBOX_VERSION,
    SCHEMA_VERSION,
    Event,
    SessionMetadata,
    compute_content_hash,
    now_iso,
)

# Default max bytes for inline input/output before switching to hash-only
DEFAULT_MAX_INLINE_BYTES = 64 * 1024  # 64KB


@dataclass
class ReadResult:
    """Result of reading events, including any errors."""

    events: list[Event]
    truncated_line: str | None = None  # If last line was incomplete
    parse_errors: list[tuple[int, str]] = None  # (line_number, error_message)

    def __post_init__(self):
        if self.parse_errors is None:
            self.parse_errors = []

    @property
    def has_truncation(self) -> bool:
        return self.truncated_line is not None

    @property
    def has_errors(self) -> bool:
        return bool(self.parse_errors)


def get_lightbox_dir() -> Path:
    """Get the root Lightbox directory.

    Uses LIGHTBOX_DIR environment variable if set, otherwise ~/.lightbox
    """
    if env_dir := os.environ.get("LIGHTBOX_DIR"):
        return Path(env_dir)
    return Path.home() / ".lightbox"


def get_sessions_dir() -> Path:
    """Get the sessions directory."""
    return get_lightbox_dir() / "sessions"


def get_session_dir(session_id: str) -> Path:
    """Get the directory for a specific session."""
    return get_sessions_dir() / session_id


def get_events_file(session_id: str) -> Path:
    """Get the events file path for a session."""
    return get_session_dir(session_id) / "events.jsonl"


def get_meta_file(session_id: str) -> Path:
    """Get the metadata file path for a session."""
    return get_session_dir(session_id) / "meta.json"


def ensure_session_dir(session_id: str) -> Path:
    """Ensure the session directory exists and return its path."""
    session_dir = get_session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def write_session_metadata(session_id: str) -> SessionMetadata:
    """Write session metadata file. Called on first event."""
    meta = SessionMetadata(
        session_id=session_id,
        schema_version=SCHEMA_VERSION,
        lightbox_version=LIGHTBOX_VERSION,
        created_at=now_iso(),
    )
    meta_file = get_meta_file(session_id)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta.to_dict(), f, indent=2)
    return meta


def read_session_metadata(session_id: str) -> SessionMetadata | None:
    """Read session metadata. Returns None if not found."""
    meta_file = get_meta_file(session_id)
    if not meta_file.exists():
        return None
    with open(meta_file, encoding="utf-8") as f:
        return SessionMetadata.from_dict(json.load(f))


def append_event(session_id: str, event: Event) -> None:
    """Append an event to the session's event log.

    Uses file locking to ensure concurrent writes don't corrupt the file.
    The event is written as a single JSON line (JSONL format).

    ATOMICITY:
    - Single write call for the entire line
    - fsync ensures durability
    - If process crashes mid-write, line will be truncated (detectable)
    """
    ensure_session_dir(session_id)

    # Write metadata on first event
    meta_file = get_meta_file(session_id)
    if not meta_file.exists():
        write_session_metadata(session_id)

    events_file = get_events_file(session_id)

    # Serialize event to JSON line (no pretty printing, deterministic order)
    event_line = json.dumps(event.to_dict(), separators=(",", ":"), sort_keys=True) + "\n"

    # Append with exclusive lock
    with open(events_file, "a", encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            f.write(event_line)
            f.flush()
            os.fsync(f.fileno())  # Ensure durability
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def read_events(session_id: str) -> list[Event]:
    """Read all events from a session.

    Returns an empty list if the session doesn't exist.
    Note: This ignores truncation/parse errors. Use read_events_with_status()
    for full error information.
    """
    result = read_events_with_status(session_id)
    return result.events


def read_events_with_status(session_id: str) -> ReadResult:
    """Read all events from a session with full status information.

    Returns ReadResult containing:
    - events: Successfully parsed events
    - truncated_line: If last line was incomplete (crash mid-write)
    - parse_errors: Any lines that failed to parse

    Use this for verification to distinguish truncation from tampering.
    """
    events_file = get_events_file(session_id)
    if not events_file.exists():
        return ReadResult(events=[])

    events = []
    parse_errors = []
    truncated_line = None

    with open(events_file, encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            lines = f.readlines()
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)

    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.rstrip("\n\r")

        if not stripped:
            continue

        # Check if last line doesn't end with newline (truncation indicator)
        if i == len(lines) - 1 and not line.endswith("\n"):
            truncated_line = stripped
            # Still try to parse it - might be valid JSON (just missing trailing newline)
            try:
                data = json.loads(stripped)
                events.append(Event.from_dict(data))
                truncated_line = None  # Was valid, not really truncated
            except (json.JSONDecodeError, KeyError):
                # Truncation caused parse failure - keep truncated_line set
                # Do NOT add to parse_errors - this is truncation, not corruption
                pass
            continue

        try:
            data = json.loads(stripped)
            events.append(Event.from_dict(data))
        except json.JSONDecodeError as e:
            parse_errors.append((line_num, f"Invalid JSON: {e}"))
        except KeyError as e:
            parse_errors.append((line_num, f"Missing required field: {e}"))

    return ReadResult(
        events=events,
        truncated_line=truncated_line,
        parse_errors=parse_errors,
    )


def iter_events(session_id: str) -> Iterator[Event]:
    """Iterate over events in a session without loading all into memory.

    Note: This ignores parse errors. Use read_events_with_status() for
    full error handling.
    """
    events_file = get_events_file(session_id)
    if not events_file.exists():
        return

    with open(events_file, encoding="utf-8") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)
        try:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        yield Event.from_dict(data)
                    except (json.JSONDecodeError, KeyError):
                        # Skip malformed lines in iterator mode
                        continue
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def list_sessions() -> list[str]:
    """List all session IDs.

    Returns session IDs sorted by modification time (most recent first).
    """
    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        return []

    sessions = []
    for entry in sessions_dir.iterdir():
        if entry.is_dir():
            events_file = entry / "events.jsonl"
            if events_file.exists():
                mtime = events_file.stat().st_mtime
                sessions.append((entry.name, mtime))

    # Sort by modification time, most recent first
    sessions.sort(key=lambda x: x[1], reverse=True)
    return [s[0] for s in sessions]


def session_exists(session_id: str) -> bool:
    """Check if a session exists."""
    return get_events_file(session_id).exists()


def get_session_info(session_id: str) -> dict | None:
    """Get basic info about a session.

    Returns None if session doesn't exist.
    """
    events_file = get_events_file(session_id)
    if not events_file.exists():
        return None

    result = read_events_with_status(session_id)
    meta = read_session_metadata(session_id)

    if not result.events:
        return {
            "session_id": session_id,
            "event_count": 0,
            "first_event": None,
            "last_event": None,
            "schema_version": meta.schema_version if meta else "unknown",
            "has_truncation": result.has_truncation,
            "has_errors": result.has_errors,
        }

    return {
        "session_id": session_id,
        "event_count": len(result.events),
        "first_event": result.events[0].timestamp_start,
        "last_event": result.events[-1].timestamp_end or result.events[-1].timestamp_start,
        "tools_used": list({e.tool for e in result.events}),
        "schema_version": meta.schema_version if meta else "unknown",
        "has_truncation": result.has_truncation,
        "has_errors": result.has_errors,
    }


# --- Redaction and Size Bounds ---


@dataclass
class RedactionConfig:
    """Configuration for input/output redaction.

    Attributes:
        max_inline_bytes: Maximum bytes before switching to hash-only storage
        redact_keys: Keys to always redact (e.g., ["api_key", "token", "password"])
        hash_oversized: If True, store hash+size for oversized content
    """

    max_inline_bytes: int = DEFAULT_MAX_INLINE_BYTES
    redact_keys: list[str] = None
    hash_oversized: bool = True

    def __post_init__(self):
        if self.redact_keys is None:
            self.redact_keys = []


def apply_redaction(
    data: dict[str, Any],
    config: RedactionConfig,
) -> tuple[dict[str, Any], dict[str, str] | None]:
    """Apply redaction rules to input/output data.

    Returns:
        (redacted_data, content_hashes) where content_hashes maps
        redacted keys to their SHA-256 hashes.
    """
    if not config.redact_keys and not config.hash_oversized:
        return data, None

    redacted = {}
    content_hashes = {}

    for key, value in data.items():
        # Check if key should be redacted
        if key in config.redact_keys:
            serialized = json.dumps(value, separators=(",", ":"))
            content_hashes[key] = compute_content_hash(serialized)
            redacted[key] = "[REDACTED]"
            continue

        # Check size bounds
        if config.hash_oversized:
            serialized = json.dumps(value, separators=(",", ":"))
            if len(serialized.encode("utf-8")) > config.max_inline_bytes:
                content_hashes[key] = compute_content_hash(serialized)
                redacted[key] = {
                    "_redacted": True,
                    "_reason": "size_limit",
                    "_bytes": len(serialized.encode("utf-8")),
                }
                continue

        redacted[key] = value

    return redacted, content_hashes if content_hashes else None

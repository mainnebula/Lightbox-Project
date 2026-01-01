"""Integrity verification for Lightbox event logs.

Verifies the hash chain to detect tampering or corruption.
Verification is offline and deterministic - no network required.

VERIFICATION CHECKS:
1. Each event's hash matches its computed hash (content integrity)
2. Each event's prev_hash matches the previous event's hash (chain integrity)
3. The first event has prev_hash=None (genesis check)

FAILURE TYPES (distinct exit codes):
- VALID (0): All checks pass
- TAMPERED (1): Hash mismatch or chain break detected
- TRUNCATED (2): Last line incomplete (crash mid-write)
- PARSE_ERROR (3): Invalid JSON in event file
- NOT_FOUND (4): Session doesn't exist
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum

from lightbox.models import Event, compute_hash
from lightbox.storage import read_events_with_status, session_exists


class VerifyStatus(IntEnum):
    """Exit codes for verification results."""

    VALID = 0
    TAMPERED = 1
    TRUNCATED = 2
    PARSE_ERROR = 3
    NOT_FOUND = 4


@dataclass
class VerificationResult:
    """Result of verifying a session's hash chain."""

    status: VerifyStatus
    valid: bool  # Convenience: True only if status == VALID
    event_count: int
    error_index: int | None = None
    error_message: str | None = None
    expected_hash: str | None = None
    actual_hash: str | None = None
    truncated_line: str | None = None  # If truncation detected
    parse_errors: list[tuple[int, str]] | None = None  # If parse errors

    def __bool__(self) -> bool:
        return self.valid

    @property
    def exit_code(self) -> int:
        """Get the exit code for CLI usage."""
        return int(self.status)


def verify_event(event: Event, prev_hash: str | None) -> tuple[bool, str | None]:
    """Verify a single event's hash.

    Returns (is_valid, error_message).
    """
    event_dict = event.to_dict_for_hashing()
    expected_hash = compute_hash(event_dict)

    if event.hash != expected_hash:
        return False, f"Hash mismatch: expected {expected_hash[:16]}..., got {event.hash[:16]}..."

    if event.prev_hash != prev_hash:
        expected_prev = prev_hash[:16] + "..." if prev_hash else "None"
        actual_prev = event.prev_hash[:16] + "..." if event.prev_hash else "None"
        return False, f"Chain break: expected prev_hash {expected_prev}, got {actual_prev}"

    return True, None


def verify_session(session_id: str) -> VerificationResult:
    """Verify the hash chain integrity of a session.

    Checks that:
    1. Each event's hash matches its computed hash
    2. Each event's prev_hash matches the previous event's hash
    3. The first event has prev_hash=None

    IMPORTANT: Distinguishes between different failure types:
    - Truncation (crash mid-write) is distinct from tampering
    - Parse errors are distinct from hash failures

    Returns VerificationResult with status and details.
    """
    if not session_exists(session_id):
        return VerificationResult(
            status=VerifyStatus.NOT_FOUND,
            valid=False,
            event_count=0,
            error_message=f"Session '{session_id}' not found",
        )

    # Read events with full status information
    read_result = read_events_with_status(session_id)

    # Check for truncation FIRST (distinct from parse errors and tampering)
    # Truncation means: last line didn't end with newline AND failed to parse
    if read_result.has_truncation and read_result.truncated_line:
        return VerificationResult(
            status=VerifyStatus.TRUNCATED,
            valid=False,
            event_count=len(read_result.events),
            error_message="Last event truncated (incomplete write detected)",
            truncated_line=read_result.truncated_line[:100] + "..."
            if len(read_result.truncated_line) > 100
            else read_result.truncated_line,
        )

    # Check for parse errors (corruption in middle of file)
    if read_result.parse_errors:
        return VerificationResult(
            status=VerifyStatus.PARSE_ERROR,
            valid=False,
            event_count=len(read_result.events),
            error_index=read_result.parse_errors[0][0] - 1,  # Convert to 0-indexed
            error_message=f"Parse error at line {read_result.parse_errors[0][0]}: {read_result.parse_errors[0][1]}",
            parse_errors=read_result.parse_errors,
        )

    events = read_result.events
    if not events:
        return VerificationResult(
            status=VerifyStatus.VALID,
            valid=True,
            event_count=0,
        )

    # Verify hash chain
    prev_hash: str | None = None

    for i, event in enumerate(events):
        event_dict = event.to_dict_for_hashing()
        expected_hash = compute_hash(event_dict)

        if event.hash != expected_hash:
            return VerificationResult(
                status=VerifyStatus.TAMPERED,
                valid=False,
                event_count=len(events),
                error_index=i,
                error_message=f"Event {i}: hash mismatch (content modified)",
                expected_hash=expected_hash,
                actual_hash=event.hash,
            )

        if event.prev_hash != prev_hash:
            return VerificationResult(
                status=VerifyStatus.TAMPERED,
                valid=False,
                event_count=len(events),
                error_index=i,
                error_message=f"Event {i}: chain break (prev_hash mismatch)",
                expected_hash=prev_hash,
                actual_hash=event.prev_hash,
            )

        prev_hash = event.hash

    return VerificationResult(
        status=VerifyStatus.VALID,
        valid=True,
        event_count=len(events),
    )


def verify_session_streaming(session_id: str) -> Iterator[tuple[int, bool, str | None]]:
    """Verify events one at a time, yielding results as we go.

    Yields (event_index, is_valid, error_message) for each event.
    Useful for large sessions or progress reporting.

    Note: This doesn't detect truncation - use verify_session() for full checks.
    """
    if not session_exists(session_id):
        return

    from lightbox.storage import iter_events

    prev_hash: str | None = None

    for i, event in enumerate(iter_events(session_id)):
        is_valid, error = verify_event(event, prev_hash)
        yield i, is_valid, error

        if not is_valid:
            return

        prev_hash = event.hash

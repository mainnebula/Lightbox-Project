"""Core API for recording events with Lightbox.

The Session class manages event recording for a single run. Events are
automatically hash-chained and persisted as they're emitted.

Usage:
    # Option 1: Explicit session
    session = Session()
    session.emit("tool_name", {"arg": "value"}, {"result": "data"})

    # Option 2: Module-level API (uses global session)
    import lightbox
    lightbox.emit("tool_name", {"arg": "value"}, {"result": "data"})

    # Option 3: Async tools (pending -> resolved)
    inv_id = session.emit_pending("slow_tool", {"arg": "value"})
    # ... later ...
    session.emit_resolved(inv_id, {"result": "data"})

ASYNC SEMANTICS:
    - emit_pending() creates event with status="pending", records input
    - emit_resolved() creates NEW event with same invocation_id, status="complete"|"error"
    - Both events are in the hash chain (no overwrites)
    - Resolution event has input={} since input was recorded in pending

RETRY SEMANTICS:
    - Each retry is a NEW invocation_id
    - Use retry_of parameter to link to prior attempt
    - Failed attempts remain as evidence in the log
"""

from __future__ import annotations

import secrets
from typing import Any

from lightbox.models import SCHEMA_VERSION, Event, EventStatus, compute_hash, now_iso
from lightbox.storage import RedactionConfig, append_event, apply_redaction, read_events


def generate_session_id() -> str:
    """Generate a unique session ID."""
    return f"session_{secrets.token_hex(8)}"


def generate_invocation_id(counter: int) -> str:
    """Generate an invocation ID with monotonic counter."""
    return f"inv_{counter:05d}"


class Session:
    """A recording session for tool execution events.

    Each session has a unique ID and maintains a hash chain of events.
    Events are persisted immediately when emitted.
    """

    def __init__(
        self,
        session_id: str | None = None,
        redaction_config: RedactionConfig | None = None,
    ):
        """Create a new session.

        Args:
            session_id: Optional custom session ID. If not provided,
                       a unique ID will be generated.
            redaction_config: Optional configuration for input/output redaction.
        """
        self.session_id = session_id or generate_session_id()
        self.redaction_config = redaction_config
        self._invocation_counter = 0
        self._prev_hash: str | None = None
        self._pending: dict[str, dict[str, Any]] = {}  # invocation_id -> pending event data

        # If resuming an existing session, load the last hash
        existing_events = read_events(self.session_id)
        if existing_events:
            self._invocation_counter = len(existing_events)
            self._prev_hash = existing_events[-1].hash

    def _next_invocation_id(self) -> str:
        """Get the next invocation ID."""
        self._invocation_counter += 1
        return generate_invocation_id(self._invocation_counter)

    def _apply_redaction(
        self, data: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str] | None]:
        """Apply redaction if configured."""
        if self.redaction_config is None:
            return data, None
        return apply_redaction(data, self.redaction_config)

    def emit(
        self,
        tool: str,
        input: dict[str, Any],
        output: dict[str, Any],
        *,
        status: EventStatus = "complete",
        error: dict[str, Any] | None = None,
        parent_invocation: str | None = None,
        actor: str | None = None,
        originating_actor: str | None = None,
        chunk_count: int | None = None,
        total_bytes: int | None = None,
        content_hashes: dict[str, str] | None = None,
        retry_of: str | None = None,
        canonical_output: Any | None = None,
    ) -> Event:
        """Emit a complete tool execution event.

        This is the main API for recording tool calls. The event is
        immediately persisted and hash-chained.

        Args:
            tool: Name of the tool that was called
            input: Arguments passed to the tool
            output: Result returned by the tool
            status: Event status (complete, error)
            error: Error details if status is "error"
            parent_invocation: ID of parent call for nested invocations
            actor: Direct invoker (agent/user/service)
            originating_actor: Session initiator
            chunk_count: For streaming, number of chunks
            total_bytes: For streaming, total byte count
            content_hashes: Hashes for redacted/large payloads
            retry_of: Invocation ID of prior attempt if this is a retry
            canonical_output: Extracted semantic value (e.g., from framework wrappers)

        Returns:
            The recorded Event
        """
        timestamp = now_iso()
        invocation_id = self._next_invocation_id()

        # Apply redaction if configured
        redacted_input, input_hashes = self._apply_redaction(input)
        redacted_output, output_hashes = self._apply_redaction(output)

        # Merge content hashes
        merged_hashes = content_hashes
        if input_hashes or output_hashes:
            merged_hashes = merged_hashes or {}
            if input_hashes:
                merged_hashes.update({f"input.{k}": v for k, v in input_hashes.items()})
            if output_hashes:
                merged_hashes.update({f"output.{k}": v for k, v in output_hashes.items()})

        # Build event (without hash first)
        event = Event(
            schema_version=SCHEMA_VERSION,
            session_id=self.session_id,
            invocation_id=invocation_id,
            tool=tool,
            input=redacted_input,
            output=redacted_output,
            status=status,
            timestamp_start=timestamp,
            timestamp_end=timestamp,
            prev_hash=self._prev_hash,
            hash="",  # Placeholder, computed below
            parent_invocation=parent_invocation,
            actor=actor,
            originating_actor=originating_actor,
            error=error,
            chunk_count=chunk_count,
            total_bytes=total_bytes,
            content_hashes=merged_hashes,
            retry_of=retry_of,
            canonical_output=canonical_output,
        )

        # Compute hash
        event.hash = compute_hash(event.to_dict_for_hashing())

        # Persist
        append_event(self.session_id, event)
        self._prev_hash = event.hash

        return event

    def emit_pending(
        self,
        tool: str,
        input: dict[str, Any],
        *,
        parent_invocation: str | None = None,
        actor: str | None = None,
        originating_actor: str | None = None,
    ) -> str:
        """Emit a pending event for an async tool call.

        Use this when a tool call starts but hasn't completed yet.
        Call emit_resolved() when the result is available.

        IMPORTANT: This creates an event with status="pending". When resolved,
        emit_resolved() creates a NEW event (same invocation_id) - we never
        overwrite the pending event. Both events remain in the hash chain.

        Args:
            tool: Name of the tool being called
            input: Arguments passed to the tool
            parent_invocation: ID of parent call for nested invocations
            actor: Direct invoker
            originating_actor: Session initiator

        Returns:
            The invocation ID to use with emit_resolved()
        """
        timestamp = now_iso()
        invocation_id = self._next_invocation_id()

        # Apply redaction if configured
        redacted_input, input_hashes = self._apply_redaction(input)
        content_hashes = None
        if input_hashes:
            content_hashes = {f"input.{k}": v for k, v in input_hashes.items()}

        # Build pending event
        event = Event(
            schema_version=SCHEMA_VERSION,
            session_id=self.session_id,
            invocation_id=invocation_id,
            tool=tool,
            input=redacted_input,
            output=None,
            status="pending",
            timestamp_start=timestamp,
            timestamp_end=None,
            prev_hash=self._prev_hash,
            hash="",
            parent_invocation=parent_invocation,
            actor=actor,
            originating_actor=originating_actor,
            content_hashes=content_hashes,
        )

        # Compute hash
        event.hash = compute_hash(event.to_dict_for_hashing())

        # Persist
        append_event(self.session_id, event)
        self._prev_hash = event.hash

        # Store pending info for resolution
        self._pending[invocation_id] = {
            "tool": tool,
            "timestamp_start": timestamp,
            "parent_invocation": parent_invocation,
            "actor": actor,
            "originating_actor": originating_actor,
        }

        return invocation_id

    def emit_resolved(
        self,
        invocation_id: str,
        output: dict[str, Any],
        *,
        status: EventStatus = "complete",
        error: dict[str, Any] | None = None,
        chunk_count: int | None = None,
        total_bytes: int | None = None,
        content_hashes: dict[str, str] | None = None,
        canonical_output: Any | None = None,
    ) -> Event:
        """Emit a resolution event for a pending async call.

        IMPORTANT: This creates a NEW event with the same invocation_id as the
        pending event. The pending event is NOT modified - both events exist
        in the hash chain as evidence of the full lifecycle.

        Args:
            invocation_id: The ID returned by emit_pending()
            output: Result returned by the tool
            status: Event status (complete, error)
            error: Error details if status is "error"
            chunk_count: For streaming, number of chunks
            total_bytes: For streaming, total byte count
            content_hashes: Hashes for redacted/large payloads
            canonical_output: Extracted semantic value (e.g., from framework wrappers)

        Returns:
            The recorded resolution Event

        Raises:
            ValueError: If invocation_id is not found in pending calls
        """
        pending = self._pending.pop(invocation_id, None)
        if pending is None:
            raise ValueError(f"Unknown invocation_id: {invocation_id}")

        timestamp = now_iso()

        # Apply redaction if configured
        redacted_output, output_hashes = self._apply_redaction(output)

        # Merge content hashes
        merged_hashes = content_hashes
        if output_hashes:
            merged_hashes = merged_hashes or {}
            merged_hashes.update({f"output.{k}": v for k, v in output_hashes.items()})

        # Build resolution event (input={} since it was recorded in pending)
        event = Event(
            schema_version=SCHEMA_VERSION,
            session_id=self.session_id,
            invocation_id=invocation_id,  # Same ID as pending
            tool=pending["tool"],
            input={},  # Input was recorded in pending event
            output=redacted_output,
            status=status,
            timestamp_start=pending["timestamp_start"],
            timestamp_end=timestamp,
            prev_hash=self._prev_hash,
            hash="",
            parent_invocation=pending.get("parent_invocation"),
            actor=pending.get("actor"),
            originating_actor=pending.get("originating_actor"),
            error=error,
            chunk_count=chunk_count,
            total_bytes=total_bytes,
            content_hashes=merged_hashes,
            canonical_output=canonical_output,
        )

        # Compute hash
        event.hash = compute_hash(event.to_dict_for_hashing())

        # Persist
        append_event(self.session_id, event)
        self._prev_hash = event.hash

        return event


# Global session for module-level API
_current_session: Session | None = None


def start_session(
    session_id: str | None = None,
    redaction_config: RedactionConfig | None = None,
) -> Session:
    """Start a new global session.

    This sets the current session for module-level emit() calls.

    Args:
        session_id: Optional custom session ID
        redaction_config: Optional configuration for input/output redaction

    Returns:
        The new Session
    """
    global _current_session
    _current_session = Session(session_id, redaction_config=redaction_config)
    return _current_session


def get_current_session() -> Session | None:
    """Get the current global session, if any."""
    return _current_session


def emit(
    tool: str,
    input: dict[str, Any],
    output: dict[str, Any],
    **kwargs: Any,
) -> Event:
    """Emit an event using the global session.

    If no session exists, one is automatically created.

    Args:
        tool: Name of the tool that was called
        input: Arguments passed to the tool
        output: Result returned by the tool
        **kwargs: Additional arguments passed to Session.emit()

    Returns:
        The recorded Event
    """
    global _current_session
    if _current_session is None:
        _current_session = Session()
    return _current_session.emit(tool, input, output, **kwargs)

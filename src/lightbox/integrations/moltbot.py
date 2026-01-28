"""Moltbot integration for Lightbox.

Moltbot is a TypeScript/Node.js agent that executes tools via subprocesses,
including Python scripts. This integration provides wrapper functions that
agents can call before/after tool execution to record audit trails.

WHAT IS CAPTURED:
    - Tool invocations (name, input, output, status)
    - Tool execution timing
    - Error information when tools fail

WHAT IS NOT CAPTURED (by design):
    - Agent reasoning or prompts
    - Internal state
    - Non-tool operations

Usage:
    # Record a complete tool call
    from lightbox.integrations.moltbot import record_tool_call

    record_tool_call("search_web", {"query": "test"}, {"results": [...]})

    # Wrap a function to auto-record
    from lightbox.integrations.moltbot import wrap_tool

    @wrap_tool("my_tool")
    def my_tool(query: str) -> dict:
        return {"result": "..."}

    # Use the hook class for more control
    from lightbox.integrations.moltbot import LightboxMoltbotHook

    hook = LightboxMoltbotHook()
    inv_id = hook.before_tool("search_web", {"query": "test"})
    # ... execute tool ...
    hook.after_tool(inv_id, {"results": [...]})
"""

from __future__ import annotations

import functools
import os
from typing import Any

from lightbox.core import Session, get_current_session


def _get_env(key: str) -> str | None:
    """Get environment variable, returning None if empty."""
    val = os.environ.get(key)
    return val if val else None


class MoltbotSession(Session):
    """Session with Moltbot-specific defaults.

    Automatically picks up environment variables set by Moltbot:
    - MOLTBOT_SESSION_ID: Use as the Lightbox session ID
    - MOLTBOT_AGENT_NAME: Use as the actor name

    The actor defaults to "moltbot" if MOLTBOT_AGENT_NAME is not set.
    """

    def __init__(
        self,
        session_id: str | None = None,
        actor: str | None = None,
        originating_actor: str | None = None,
        **kwargs: Any,
    ):
        """Create a Moltbot-aware session.

        Args:
            session_id: Session ID. Falls back to MOLTBOT_SESSION_ID env var.
            actor: Actor name. Falls back to MOLTBOT_AGENT_NAME env var,
                   then to "moltbot".
            originating_actor: Originating actor. Falls back to
                               MOLTBOT_AGENT_NAME env var.
            **kwargs: Additional arguments passed to Session.
        """
        resolved_id = session_id or _get_env("MOLTBOT_SESSION_ID")
        super().__init__(session_id=resolved_id, **kwargs)

        env_agent = _get_env("MOLTBOT_AGENT_NAME")
        self.default_actor = actor or env_agent or "moltbot"
        self.default_originating_actor = originating_actor or env_agent


class LightboxMoltbotHook:
    """Hook into Moltbot's tool execution lifecycle.

    Provides before/after methods that can be called around tool
    execution to record audit trails.

    THREAD SAFETY:
        Not thread-safe by default. Moltbot executes tools as
        subprocesses, so each process gets its own hook instance.

    Usage:
        hook = LightboxMoltbotHook()

        # Before tool runs
        inv_id = hook.before_tool("search", {"query": "test"})

        # After tool completes
        hook.after_tool(inv_id, {"results": [...]})

        # Or if tool failed
        hook.after_tool_error(inv_id, error_type="TimeoutError", message="...")
    """

    def __init__(self, session: MoltbotSession | Session | None = None):
        """Create a new hook.

        Args:
            session: Session to use. If not provided, creates a MoltbotSession
                    (which picks up environment variables).
        """
        if session is None:
            existing = get_current_session()
            if existing is not None:
                self.session = existing
            else:
                self.session = MoltbotSession()
        else:
            self.session = session

    @property
    def session_id(self) -> str:
        """Get the session ID being used."""
        return self.session.session_id

    def _get_actor_defaults(self) -> dict[str, str | None]:
        """Get actor defaults from session if it's a MoltbotSession."""
        if isinstance(self.session, MoltbotSession):
            return {
                "actor": self.session.default_actor,
                "originating_actor": self.session.default_originating_actor,
            }
        return {}

    def before_tool(
        self,
        tool: str,
        input: dict[str, Any],
        *,
        parent_invocation: str | None = None,
        actor: str | None = None,
        originating_actor: str | None = None,
    ) -> str:
        """Record that a tool is about to execute.

        Args:
            tool: Name of the tool being called
            input: Arguments passed to the tool
            parent_invocation: ID of parent call for nested invocations
            actor: Direct invoker (overrides session default)
            originating_actor: Session initiator (overrides session default)

        Returns:
            Invocation ID to pass to after_tool() or after_tool_error()
        """
        defaults = self._get_actor_defaults()
        return self.session.emit_pending(
            tool=tool,
            input=input,
            parent_invocation=parent_invocation,
            actor=actor or defaults.get("actor"),
            originating_actor=originating_actor or defaults.get("originating_actor"),
        )

    def after_tool(
        self,
        invocation_id: str,
        output: dict[str, Any],
        *,
        canonical_output: Any | None = None,
    ) -> None:
        """Record that a tool completed successfully.

        Args:
            invocation_id: ID returned by before_tool()
            output: Result returned by the tool
            canonical_output: Extracted semantic value for cleaner display
        """
        self.session.emit_resolved(
            invocation_id,
            output,
            status="complete",
            canonical_output=canonical_output,
        )

    def after_tool_error(
        self,
        invocation_id: str,
        *,
        error_type: str = "Error",
        message: str = "",
        output: dict[str, Any] | None = None,
    ) -> None:
        """Record that a tool failed.

        Args:
            invocation_id: ID returned by before_tool()
            error_type: Type/class of the error
            message: Error message
            output: Any partial output (defaults to empty dict)
        """
        self.session.emit_resolved(
            invocation_id,
            output or {},
            status="error",
            error={"type": error_type, "message": message},
        )


def record_tool_call(
    tool: str,
    input: dict[str, Any],
    output: dict[str, Any],
    *,
    status: str = "complete",
    error: dict[str, Any] | None = None,
    session: Session | None = None,
    actor: str | None = None,
    originating_actor: str | None = None,
    canonical_output: Any | None = None,
) -> None:
    """Record a complete tool call in one shot.

    Convenience function for recording a tool execution that has already
    completed. Creates a MoltbotSession if no session is provided.

    Args:
        tool: Name of the tool that was called
        input: Arguments passed to the tool
        output: Result returned by the tool
        status: Event status ("complete" or "error")
        error: Error details if status is "error"
        session: Session to use (creates MoltbotSession if not provided)
        actor: Direct invoker
        originating_actor: Session initiator
        canonical_output: Extracted semantic value
    """
    if session is None:
        existing = get_current_session()
        session = existing if existing is not None else MoltbotSession()

    defaults: dict[str, str | None] = {}
    if isinstance(session, MoltbotSession):
        defaults = {
            "actor": session.default_actor,
            "originating_actor": session.default_originating_actor,
        }

    session.emit(
        tool=tool,
        input=input,
        output=output,
        status=status,
        error=error,
        actor=actor or defaults.get("actor"),
        originating_actor=originating_actor or defaults.get("originating_actor"),
        canonical_output=canonical_output,
    )


def wrap_tool(
    tool_name: str,
    *,
    session: Session | None = None,
) -> Any:
    """Decorator that wraps a Python callable to auto-record its execution.

    The wrapped function's arguments are recorded as input, and its return
    value as output. Exceptions are recorded as errors.

    Args:
        tool_name: Name to record for this tool
        session: Session to use (creates MoltbotSession if not provided)

    Returns:
        Decorator function

    Example:
        @wrap_tool("search_web")
        def search_web(query: str) -> dict:
            return {"results": [...]}

        # Calling search_web() now auto-records the execution
        result = search_web("test query")
    """

    def decorator(func: Any) -> Any:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            hook = LightboxMoltbotHook(session=session)

            # Build input dict from args and kwargs
            input_dict: dict[str, Any] = {}
            if args:
                input_dict["args"] = [str(a) for a in args]
            if kwargs:
                input_dict.update({k: str(v) for k, v in kwargs.items()})
            if not input_dict:
                input_dict = {}

            inv_id = hook.before_tool(tool_name, input_dict)
            try:
                result = func(*args, **kwargs)
                # Convert result to dict for output
                if isinstance(result, dict):
                    output = result
                else:
                    output = {"result": str(result) if result is not None else None}
                hook.after_tool(inv_id, output, canonical_output=result)
                return result
            except Exception as e:
                hook.after_tool_error(
                    inv_id,
                    error_type=type(e).__name__,
                    message=str(e),
                )
                raise

        return wrapper

    return decorator

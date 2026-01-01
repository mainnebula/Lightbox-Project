"""LangChain integration for Lightbox.

Provides a callback handler that automatically records tool executions
from LangChain agents and chains.

WHAT IS CAPTURED:
    - Tool invocations (on_tool_start, on_tool_end, on_tool_error)
    - Tool inputs and outputs
    - Error information when tools fail

WHAT IS NOT CAPTURED (by design):
    - LLM prompts and completions (no reasoning capture)
    - Chain/agent internal state
    - Retriever operations
    - Non-tool callbacks

Usage:
    from lightbox.integrations.langchain import wrap

    agent = create_agent(tools=[...])
    agent = wrap(agent)  # Now records all tool calls

Or with explicit session:
    from lightbox import Session
    from lightbox.integrations.langchain import LightboxCallbackHandler

    session = Session()
    handler = LightboxCallbackHandler(session=session)
    agent.invoke(input, config={"callbacks": [handler]})
"""

from __future__ import annotations

import contextlib
import threading
from typing import Any
from uuid import UUID

try:
    from langchain_core.callbacks import BaseCallbackHandler
    from langchain_core.runnables import Runnable

    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    BaseCallbackHandler = object  # type: ignore
    Runnable = object  # type: ignore

from lightbox.core import Session, get_current_session


def _ensure_langchain():
    """Raise ImportError if LangChain is not installed."""
    if not LANGCHAIN_AVAILABLE:
        raise ImportError(
            "LangChain integration requires langchain-core. "
            "Install with: pip install lightbox[langchain]"
        )


def _extract_canonical_output(output: Any) -> Any:
    """Extract the semantic value from a LangChain output wrapper.

    LangChain tool outputs are often wrapped in message objects like ToolMessage
    with metadata (additional_kwargs, artifact, etc.). This extracts just the
    actual return value for cleaner logs.

    Args:
        output: The raw output from a LangChain tool

    Returns:
        The extracted canonical value, or the original if no extraction needed
    """
    # Handle LangChain message types (ToolMessage, AIMessage, etc.)
    if hasattr(output, "content"):
        return output.content

    # Handle dicts that look like serialized messages
    if (
        isinstance(output, dict)
        and "content" in output
        and any(k in output for k in ("additional_kwargs", "artifact", "type"))
    ):
        return output["content"]

    # Handle plain strings and other primitives
    if isinstance(output, (str, int, bool, type(None))):
        return output

    # Handle lists (might be list of messages)
    if isinstance(output, list) and output and hasattr(output[0], "content"):
        return [_extract_canonical_output(item) for item in output]

    # Return as-is if no extraction pattern matched
    return output


class LightboxCallbackHandler(BaseCallbackHandler):
    """LangChain callback handler that records tool executions to Lightbox.

    This handler intercepts tool start/end/error events and emits
    corresponding Lightbox events.

    THREAD SAFETY:
        Uses a lock to protect the pending dict for concurrent tool calls.

    DOUBLE-RECORDING PREVENTION:
        - Each run_id can only trigger one pending event
        - Resolved events are only emitted if there's a matching pending
        - Parent chain callbacks are ignored (only direct tool calls)
    """

    # Only handle tool callbacks - explicitly not LLM or chain callbacks
    raise_error = False  # Don't crash the chain on handler errors

    def __init__(self, session: Session | None = None):
        """Create a new callback handler.

        Args:
            session: Optional Session to use. If not provided,
                    uses the current global session or creates a new one.
        """
        _ensure_langchain()
        super().__init__()
        self.session = session or get_current_session() or Session()
        self._pending: dict[str, str] = {}  # run_id -> invocation_id
        self._lock = threading.Lock()
        self._seen_run_ids: set[str] = set()  # Prevent double-recording

    @property
    def session_id(self) -> str:
        """Get the session ID being used."""
        return self.session.session_id

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts executing."""
        run_id_str = str(run_id)

        with self._lock:
            # Prevent double-recording of the same run
            if run_id_str in self._seen_run_ids:
                return
            self._seen_run_ids.add(run_id_str)

        tool_name = serialized.get("name", "unknown_tool")

        # Prefer structured inputs over input_str
        tool_input = inputs if inputs is not None else {"input": input_str}

        # Get parent invocation ID if this is a nested call
        parent_inv = None
        if parent_run_id:
            with self._lock:
                parent_inv = self._pending.get(str(parent_run_id))

        try:
            # Emit pending event
            inv_id = self.session.emit_pending(
                tool=tool_name,
                input=tool_input,
                parent_invocation=parent_inv,
            )
            with self._lock:
                self._pending[run_id_str] = inv_id
        except Exception:
            # Don't crash the chain on recording errors
            pass

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool completes successfully."""
        run_id_str = str(run_id)

        with self._lock:
            inv_id = self._pending.pop(run_id_str, None)

        if inv_id is None:
            # No matching pending event - skip to prevent orphaned records
            return

        try:
            # Extract canonical output (the actual value) from framework wrappers
            canonical = _extract_canonical_output(output)

            # Convert full output to dict for raw storage
            if isinstance(output, dict):
                output_dict = output
            elif hasattr(output, "model_dump"):
                output_dict = output.model_dump()
            elif hasattr(output, "dict"):
                output_dict = output.dict()
            else:
                output_dict = {"output": str(output)}

            self.session.emit_resolved(
                inv_id,
                output_dict,
                status="complete",
                canonical_output=canonical,
            )
        except Exception:
            # Don't crash the chain on recording errors
            pass

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool errors."""
        run_id_str = str(run_id)

        with self._lock:
            inv_id = self._pending.pop(run_id_str, None)

        if inv_id is None:
            # No matching pending event - skip
            return

        with contextlib.suppress(Exception):
            self.session.emit_resolved(
                inv_id,
                {},
                status="error",
                error={
                    "type": type(error).__name__,
                    "message": str(error),
                },
            )

    # Explicitly do NOT implement these - we don't capture LLM/chain events
    # on_llm_start, on_llm_end, on_llm_error
    # on_chain_start, on_chain_end, on_chain_error
    # on_retriever_start, on_retriever_end, on_retriever_error


def wrap(runnable: Runnable, session: Session | None = None) -> Runnable:
    """Wrap a LangChain runnable to record tool executions.

    This is the easiest way to add Lightbox recording to an existing
    LangChain agent or chain.

    Args:
        runnable: The LangChain runnable to wrap
        session: Optional Session to use

    Returns:
        The wrapped runnable with Lightbox recording enabled

    Example:
        from lightbox.integrations.langchain import wrap

        agent = create_agent(tools=[...])
        agent = wrap(agent)

        # Now all tool calls are automatically recorded
        result = agent.invoke({"input": "..."})
    """
    _ensure_langchain()
    handler = LightboxCallbackHandler(session=session)
    return runnable.with_config(callbacks=[handler])


def get_handler(session: Session | None = None) -> LightboxCallbackHandler:
    """Get a Lightbox callback handler.

    Use this when you need to add the handler to an existing config.

    Args:
        session: Optional Session to use

    Returns:
        LightboxCallbackHandler instance

    Example:
        handler = get_handler()
        result = agent.invoke(input, config={"callbacks": [handler]})
    """
    _ensure_langchain()
    return LightboxCallbackHandler(session=session)

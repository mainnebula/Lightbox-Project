"""Tests for Moltbot integration."""

import os

import pytest

from lightbox.core import Session
from lightbox.integrations.moltbot import (
    LightboxMoltbotHook,
    MoltbotSession,
    record_tool_call,
    wrap_tool,
)
from lightbox.storage import read_events


class TestMoltbotSession:
    """Tests for MoltbotSession."""

    def test_creates_session_with_defaults(self, temp_lightbox_dir):
        session = MoltbotSession()
        assert session.session_id.startswith("session_")
        assert session.default_actor == "moltbot"
        assert session.default_originating_actor is None

    def test_picks_up_env_session_id(self, temp_lightbox_dir, monkeypatch):
        monkeypatch.setenv("MOLTBOT_SESSION_ID", "my_test_session")
        session = MoltbotSession()
        assert session.session_id == "my_test_session"

    def test_picks_up_env_agent_name(self, temp_lightbox_dir, monkeypatch):
        monkeypatch.setenv("MOLTBOT_AGENT_NAME", "my_agent")
        session = MoltbotSession()
        assert session.default_actor == "my_agent"
        assert session.default_originating_actor == "my_agent"

    def test_explicit_params_override_env(self, temp_lightbox_dir, monkeypatch):
        monkeypatch.setenv("MOLTBOT_SESSION_ID", "env_session")
        monkeypatch.setenv("MOLTBOT_AGENT_NAME", "env_agent")
        session = MoltbotSession(
            session_id="explicit_session",
            actor="explicit_actor",
            originating_actor="explicit_originator",
        )
        assert session.session_id == "explicit_session"
        assert session.default_actor == "explicit_actor"
        assert session.default_originating_actor == "explicit_originator"

    def test_empty_env_vars_treated_as_none(self, temp_lightbox_dir, monkeypatch):
        monkeypatch.setenv("MOLTBOT_SESSION_ID", "")
        monkeypatch.setenv("MOLTBOT_AGENT_NAME", "")
        session = MoltbotSession()
        assert session.session_id.startswith("session_")
        assert session.default_actor == "moltbot"


class TestLightboxMoltbotHook:
    """Tests for LightboxMoltbotHook."""

    def test_creates_hook_with_default_session(self, temp_lightbox_dir):
        hook = LightboxMoltbotHook()
        assert hook.session_id.startswith("session_")

    def test_creates_hook_with_explicit_session(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_hook_session")
        hook = LightboxMoltbotHook(session=session)
        assert hook.session_id == "test_hook_session"

    def test_before_and_after_tool(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_hook_lifecycle")
        hook = LightboxMoltbotHook(session=session)

        inv_id = hook.before_tool("search_web", {"query": "test"})
        assert inv_id == "inv_00001"

        hook.after_tool(inv_id, {"results": ["result1"]})

        events = read_events("test_hook_lifecycle")
        assert len(events) == 2
        assert events[0].status == "pending"
        assert events[0].tool == "search_web"
        assert events[0].input == {"query": "test"}
        assert events[1].status == "complete"
        assert events[1].output == {"results": ["result1"]}
        assert events[1].invocation_id == inv_id

    def test_before_and_after_tool_error(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_hook_error")
        hook = LightboxMoltbotHook(session=session)

        inv_id = hook.before_tool("failing_tool", {"input": "data"})
        hook.after_tool_error(inv_id, error_type="TimeoutError", message="Timed out")

        events = read_events("test_hook_error")
        assert len(events) == 2
        assert events[1].status == "error"
        assert events[1].error == {"type": "TimeoutError", "message": "Timed out"}

    def test_actor_defaults_from_moltbot_session(self, temp_lightbox_dir, monkeypatch):
        monkeypatch.setenv("MOLTBOT_AGENT_NAME", "my_bot")
        session = MoltbotSession(session_id="test_hook_actor")
        hook = LightboxMoltbotHook(session=session)

        inv_id = hook.before_tool("tool1", {"x": "1"})
        hook.after_tool(inv_id, {"result": "ok"})

        events = read_events("test_hook_actor")
        assert events[0].actor == "my_bot"
        assert events[0].originating_actor == "my_bot"

    def test_actor_override_in_before_tool(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_hook_actor_override")
        hook = LightboxMoltbotHook(session=session)

        inv_id = hook.before_tool("tool1", {"x": "1"}, actor="custom_actor")
        hook.after_tool(inv_id, {"result": "ok"})

        events = read_events("test_hook_actor_override")
        assert events[0].actor == "custom_actor"

    def test_uses_existing_global_session(self, temp_lightbox_dir):
        """Hook should use existing global session if available."""
        from lightbox.core import start_session, _current_session

        global_session = start_session("global_session_test")
        try:
            hook = LightboxMoltbotHook()
            assert hook.session_id == "global_session_test"
        finally:
            # Clean up global state
            import lightbox.core
            lightbox.core._current_session = None


class TestRecordToolCall:
    """Tests for record_tool_call convenience function."""

    def test_records_complete_call(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_record_complete")
        record_tool_call(
            tool="search_web",
            input={"query": "test"},
            output={"results": ["r1"]},
            session=session,
        )

        events = read_events("test_record_complete")
        assert len(events) == 1
        assert events[0].tool == "search_web"
        assert events[0].status == "complete"
        assert events[0].input == {"query": "test"}
        assert events[0].output == {"results": ["r1"]}

    def test_records_error_call(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_record_error")
        record_tool_call(
            tool="failing_tool",
            input={"x": "1"},
            output={},
            status="error",
            error={"type": "ValueError", "message": "bad input"},
            session=session,
        )

        events = read_events("test_record_error")
        assert len(events) == 1
        assert events[0].status == "error"
        assert events[0].error == {"type": "ValueError", "message": "bad input"}

    def test_records_with_canonical_output(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_record_canonical")
        record_tool_call(
            tool="search",
            input={"q": "test"},
            output={"raw": "data", "results": ["r1"]},
            canonical_output="r1",
            session=session,
        )

        events = read_events("test_record_canonical")
        assert events[0].canonical_output == "r1"

    def test_creates_session_if_none_provided(self, temp_lightbox_dir):
        # Clear any global session
        import lightbox.core
        lightbox.core._current_session = None

        record_tool_call(
            tool="auto_session_tool",
            input={"x": "1"},
            output={"y": "2"},
        )
        # Should not raise — session is auto-created


class TestWrapTool:
    """Tests for wrap_tool decorator."""

    def test_wraps_function_records_call(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_wrap_tool")

        @wrap_tool("my_tool", session=session)
        def my_tool(query):
            return {"result": "found"}

        result = my_tool("test query")
        assert result == {"result": "found"}

        events = read_events("test_wrap_tool")
        assert len(events) == 2  # pending + resolved
        assert events[0].tool == "my_tool"
        assert events[0].status == "pending"
        assert events[1].status == "complete"
        assert events[1].output == {"result": "found"}

    def test_wraps_function_records_error(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_wrap_error")

        @wrap_tool("failing_tool", session=session)
        def failing_tool():
            raise ValueError("bad input")

        with pytest.raises(ValueError, match="bad input"):
            failing_tool()

        events = read_events("test_wrap_error")
        assert len(events) == 2
        assert events[0].status == "pending"
        assert events[1].status == "error"
        assert events[1].error["type"] == "ValueError"
        assert events[1].error["message"] == "bad input"

    def test_wraps_function_preserves_name(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_wrap_name")

        @wrap_tool("my_named_tool", session=session)
        def my_function():
            """My docstring."""
            return {"done": True}

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "My docstring."

    def test_wraps_with_args_and_kwargs(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_wrap_args")

        @wrap_tool("tool_with_args", session=session)
        def tool_with_args(a, b, key="default"):
            return {"sum": str(a + b), "key": key}

        result = tool_with_args(1, 2, key="custom")
        assert result == {"sum": "3", "key": "custom"}

        events = read_events("test_wrap_args")
        assert events[0].input["args"] == ["1", "2"]
        assert events[0].input["key"] == "custom"

    def test_wraps_function_returning_string(self, temp_lightbox_dir):
        session = MoltbotSession(session_id="test_wrap_string")

        @wrap_tool("string_tool", session=session)
        def string_tool():
            return "hello world"

        result = string_tool()
        assert result == "hello world"

        events = read_events("test_wrap_string")
        assert events[1].output == {"result": "hello world"}
        assert events[1].canonical_output == "hello world"

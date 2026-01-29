"""Flask application for the Lightbox Web GUI.

Provides a local web dashboard for browsing sessions, viewing events,
real-time updates via SSE, and integrity verification.

Endpoints:
    GET  /                              Serve the single-page application
    GET  /api/sessions                  List all sessions with metadata
    GET  /api/sessions/<id>             Get session details + events
    GET  /api/sessions/<id>/events      Get events (supports ?since= for polling)
    POST /api/sessions/<id>/verify      Run integrity verification
    GET  /api/sessions/<id>/stream      SSE endpoint for real-time event updates
    POST /api/record                    Record a tool call from an external service
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

try:
    from flask import Flask, Response, jsonify, request, send_from_directory

    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

from lightbox.integrations.moltbot import MoltbotSession, record_tool_call
from lightbox.integrity import verify_session
from lightbox.storage import (
    get_events_file,
    get_session_info,
    list_sessions,
    read_events,
    session_exists,
)

STATIC_DIR = Path(__file__).parent / "static"


def _ensure_flask() -> None:
    """Raise ImportError if Flask is not installed."""
    if not FLASK_AVAILABLE:
        raise ImportError(
            "Lightbox GUI requires Flask. "
            "Install with: pip install lightbox-rec[gui]"
        )


def _event_to_dict(event: Any) -> dict[str, Any]:
    """Convert an Event to a JSON-serializable dict."""
    return event.to_dict()


def create_app() -> Any:
    """Create and configure the Flask application."""
    _ensure_flask()

    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

    @app.route("/")
    def index() -> Any:
        return send_from_directory(str(STATIC_DIR), "index.html")

    @app.route("/api/sessions")
    def api_sessions() -> Any:
        """List all sessions with metadata."""
        session_ids = list_sessions()
        sessions = []
        for sid in session_ids:
            info = get_session_info(sid)
            if info:
                sessions.append(info)
        return jsonify(sessions)

    @app.route("/api/sessions/<session_id>")
    def api_session_detail(session_id: str) -> Any:
        """Get session details + all events."""
        if not session_exists(session_id):
            return jsonify({"error": "Session not found"}), 404

        info = get_session_info(session_id) or {}
        events = read_events(session_id)
        return jsonify({
            **info,
            "events": [_event_to_dict(e) for e in events],
        })

    @app.route("/api/sessions/<session_id>/events")
    def api_session_events(session_id: str) -> Any:
        """Get events for a session.

        Query params:
            since: Return only events after this index (0-based)
        """
        if not session_exists(session_id):
            return jsonify({"error": "Session not found"}), 404

        events = read_events(session_id)
        since = request.args.get("since", type=int)
        if since is not None and since >= 0:
            events = events[since:]
        return jsonify([_event_to_dict(e) for e in events])

    @app.route("/api/sessions/<session_id>/verify", methods=["POST"])
    def api_verify_session(session_id: str) -> Any:
        """Run integrity verification on a session."""
        if not session_exists(session_id):
            return jsonify({"error": "Session not found"}), 404

        result = verify_session(session_id)
        return jsonify({
            "status": result.status.name,
            "valid": result.valid,
            "event_count": result.event_count,
            "error_index": result.error_index,
            "error_message": result.error_message,
            "expected_hash": result.expected_hash,
            "actual_hash": result.actual_hash,
            "truncated_line": result.truncated_line,
            "parse_errors": result.parse_errors,
        })

    @app.route("/api/sessions/<session_id>/stream")
    def api_session_stream(session_id: str) -> Any:
        """SSE endpoint for real-time event updates.

        Watches the session's events.jsonl file and pushes new events
        as they are appended.
        """
        if not session_exists(session_id):
            return jsonify({"error": "Session not found"}), 404

        def generate() -> Any:
            events_file = get_events_file(session_id)
            last_count = 0

            # Get initial count
            events = read_events(session_id)
            last_count = len(events)

            yield f"data: {json.dumps({'type': 'connected', 'event_count': last_count})}\n\n"

            while True:
                time.sleep(1)
                try:
                    if not events_file.exists():
                        break
                    current_events = read_events(session_id)
                    current_count = len(current_events)
                    if current_count > last_count:
                        new_events = current_events[last_count:]
                        for event in new_events:
                            yield f"data: {json.dumps({'type': 'event', 'event': _event_to_dict(event)})}\n\n"
                        last_count = current_count
                except Exception:
                    break

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Keep a cache of sessions so we reuse the same Session object per session_id,
    # preserving the hash chain across requests.
    _sessions: dict[str, MoltbotSession] = {}

    @app.route("/api/record", methods=["POST"])
    def api_record() -> Any:
        """Record a tool call from an external service.

        Expects JSON body:
        {
            "tool": "tool_name",
            "input": {...},
            "output": {...},
            "session_id": "optional_session_id",
            "status": "complete" | "error",
            "error": {"type": "...", "message": "..."}  // optional
        }
        """
        data = request.get_json()
        if not data:
            return jsonify({"error": "Request body must be JSON"}), 400

        tool = data.get("tool")
        if not tool:
            return jsonify({"error": "Missing required field: tool"}), 400

        tool_input = data.get("input", {})
        tool_output = data.get("output", {})
        session_id = data.get("session_id")
        status = data.get("status", "complete")
        error = data.get("error")

        if not isinstance(tool_input, dict):
            tool_input = {"value": tool_input}
        if not isinstance(tool_output, dict):
            tool_output = {"value": tool_output}

        # Reuse or create session
        if session_id and session_id in _sessions:
            session = _sessions[session_id]
        else:
            session = MoltbotSession(session_id=session_id)
            _sessions[session.session_id] = session

        try:
            record_tool_call(
                tool=tool,
                input=tool_input,
                output=tool_output,
                status=status,
                error=error,
                session=session,
            )
            return jsonify({
                "status": "recorded",
                "session_id": session.session_id,
                "tool": tool,
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    return app


def main() -> None:
    """Entry point for the lightbox-gui console script."""
    _ensure_flask()
    import webbrowser

    app = create_app()
    port = 8780
    host = "127.0.0.1"

    # Open browser after a short delay
    def open_browser() -> None:
        time.sleep(1.0)
        webbrowser.open(f"http://{host}:{port}")

    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    main()

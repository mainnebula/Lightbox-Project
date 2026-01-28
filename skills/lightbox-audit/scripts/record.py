#!/usr/bin/env python3
"""Record a tool call from Moltbot.

Usage:
    python record.py --tool <name> --input '<json>' --output '<json>' [--status complete|error] [--session <id>]

Example:
    python record.py --tool search_web --input '{"query": "weather"}' --output '{"results": ["Sunny"]}'
"""

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a tool call to Lightbox")
    parser.add_argument("--tool", required=True, help="Tool name")
    parser.add_argument("--input", required=True, help="Tool input as JSON string")
    parser.add_argument("--output", required=True, help="Tool output as JSON string")
    parser.add_argument("--status", default="complete", choices=["complete", "error"],
                        help="Event status (default: complete)")
    parser.add_argument("--session", default=None, help="Session ID (auto-generated if not set)")
    parser.add_argument("--error-type", default=None, help="Error type (if status is error)")
    parser.add_argument("--error-message", default=None, help="Error message (if status is error)")
    args = parser.parse_args()

    try:
        tool_input = json.loads(args.input)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid input JSON: {e}"}))
        sys.exit(1)

    try:
        tool_output = json.loads(args.output)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid output JSON: {e}"}))
        sys.exit(1)

    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    if not isinstance(tool_output, dict):
        tool_output = {"value": tool_output}

    from lightbox.integrations.moltbot import MoltbotSession, record_tool_call

    session = MoltbotSession(session_id=args.session)

    error = None
    if args.status == "error":
        error = {
            "type": args.error_type or "Error",
            "message": args.error_message or "",
        }

    record_tool_call(
        tool=args.tool,
        input=tool_input,
        output=tool_output,
        status=args.status,
        error=error,
        session=session,
    )

    print(json.dumps({
        "status": "recorded",
        "session_id": session.session_id,
        "tool": args.tool,
    }))


if __name__ == "__main__":
    main()

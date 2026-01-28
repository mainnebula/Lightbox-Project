#!/usr/bin/env python3
"""Verify session integrity.

Usage:
    python verify.py <session_id>
    python verify.py --last

Outputs JSON result with status, event_count, and error details if any.
Exit codes match lightbox CLI conventions.
"""

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Lightbox session integrity")
    parser.add_argument("session", nargs="?", default=None, help="Session ID to verify")
    parser.add_argument("--last", action="store_true", help="Use most recent session")
    args = parser.parse_args()

    from lightbox.integrity import verify_session
    from lightbox.storage import list_sessions

    session_id = args.session
    if args.last:
        sessions = list_sessions()
        if not sessions:
            print(json.dumps({"error": "No sessions found"}))
            sys.exit(4)
        session_id = sessions[0]

    if not session_id:
        print(json.dumps({"error": "No session specified. Use --last or provide a session ID."}))
        sys.exit(4)

    result = verify_session(session_id)

    output = {
        "session_id": session_id,
        "status": result.status.name,
        "valid": result.valid,
        "event_count": result.event_count,
    }
    if result.error_message:
        output["error_message"] = result.error_message
    if result.error_index is not None:
        output["error_index"] = result.error_index
    if result.expected_hash:
        output["expected_hash"] = result.expected_hash
    if result.actual_hash:
        output["actual_hash"] = result.actual_hash

    print(json.dumps(output))
    sys.exit(result.exit_code)


if __name__ == "__main__":
    main()

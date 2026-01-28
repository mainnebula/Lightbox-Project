#!/usr/bin/env python3
"""Show session events as JSON.

Usage:
    python show.py <session_id>
    python show.py --last
    python show.py <session_id> --inv <invocation_id>

Output is a JSON array of event objects.
"""

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Show Lightbox session events")
    parser.add_argument("session", nargs="?", default=None, help="Session ID")
    parser.add_argument("--last", action="store_true", help="Use most recent session")
    parser.add_argument("--inv", default=None, help="Filter to specific invocation ID")
    args = parser.parse_args()

    from lightbox.storage import list_sessions, read_events, session_exists

    session_id = args.session
    if args.last:
        sessions = list_sessions()
        if not sessions:
            print(json.dumps({"error": "No sessions found"}))
            sys.exit(4)
        session_id = sessions[0]

    if not session_id:
        print(json.dumps({"error": "No session specified. Use --last or provide a session ID."}))
        sys.exit(1)

    if not session_exists(session_id):
        print(json.dumps({"error": f"Session '{session_id}' not found"}))
        sys.exit(4)

    events = read_events(session_id)

    if args.inv:
        events = [e for e in events if e.invocation_id == args.inv]

    print(json.dumps([e.to_dict() for e in events], indent=2))


if __name__ == "__main__":
    main()

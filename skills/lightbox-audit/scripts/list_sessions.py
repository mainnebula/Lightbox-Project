#!/usr/bin/env python3
"""List available Lightbox sessions.

Usage:
    python list_sessions.py

Output is a JSON array of session info objects.
"""

import json
import sys


def main() -> None:
    from lightbox.storage import get_session_info, list_sessions

    session_ids = list_sessions()

    if not session_ids:
        print(json.dumps([]))
        return

    sessions = []
    for sid in session_ids:
        info = get_session_info(sid)
        if info:
            sessions.append(info)

    print(json.dumps(sessions, indent=2))


if __name__ == "__main__":
    main()

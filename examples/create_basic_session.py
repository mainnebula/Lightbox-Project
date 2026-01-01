#!/usr/bin/env python3
"""Create a basic example session for demonstration.

Run this script to generate examples/basic_session/ which can be used with:
    lightbox show examples/basic_session
    lightbox replay examples/basic_session --fast
    lightbox verify examples/basic_session
"""

import os
import sys
import shutil
from pathlib import Path

# Add src to path for running without install
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lightbox import Session
from lightbox.storage import get_session_dir

# Create session with fixed ID for reproducibility
SESSION_ID = "basic_session"
EXAMPLE_DIR = Path(__file__).parent / SESSION_ID


def main():
    # Clean up any existing example
    if EXAMPLE_DIR.exists():
        shutil.rmtree(EXAMPLE_DIR)

    # Set LIGHTBOX_DIR to examples directory
    os.environ["LIGHTBOX_DIR"] = str(Path(__file__).parent)

    # Create session
    session = Session(SESSION_ID)

    # Emit some example events
    session.emit(
        "search_web",
        {"query": "python async best practices", "max_results": 5},
        {
            "results": [
                {"title": "Async IO in Python", "url": "https://example.com/1"},
                {"title": "Python Concurrency Guide", "url": "https://example.com/2"},
            ],
            "total_found": 1250,
        },
    )

    session.emit(
        "read_file",
        {"path": "/home/user/notes.txt"},
        {"content": "Remember to review the async patterns.", "size_bytes": 42},
    )

    # Simulate an async tool
    inv_id = session.emit_pending(
        "send_email",
        {"to": "team@example.com", "subject": "Async Research", "body": "See attached notes."},
    )
    session.emit_resolved(
        inv_id,
        {"message_id": "msg_abc123", "status": "sent"},
    )

    # Simulate a failed tool
    session.emit(
        "api_call",
        {"endpoint": "/v1/data", "method": "GET"},
        {},
        status="error",
        error={"type": "TimeoutError", "message": "Request timed out after 30s"},
    )

    # Final successful tool
    session.emit(
        "write_file",
        {"path": "/home/user/summary.md", "content": "# Research Summary\n\nAsync is good."},
        {"bytes_written": 35, "success": True},
    )

    print(f"Created example session: {EXAMPLE_DIR}")
    print(f"  Events: 6")
    print()
    print("Try these commands:")
    print(f"  lightbox show {SESSION_ID}")
    print(f"  lightbox replay {SESSION_ID} --fast")
    print(f"  lightbox verify {SESSION_ID}")


if __name__ == "__main__":
    main()

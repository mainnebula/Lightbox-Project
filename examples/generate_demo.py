#!/usr/bin/env python3
"""Generate a demo session with properly chained hashes."""

import json
import hashlib
from pathlib import Path


def canonical_serialize(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(event_dict: dict) -> str:
    canonical = canonical_serialize(event_dict)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main():
    session_id = "demo_weather_agent"
    output_dir = Path(__file__).parent / "demo_session"
    output_dir.mkdir(exist_ok=True)

    events = []
    prev_hash = None

    # Event 1: Check weather
    event1 = {
        "schema_version": "1",
        "session_id": session_id,
        "invocation_id": "inv_00001",
        "tool": "get_weather",
        "input": {"location": "San Francisco, CA"},
        "output": {"temperature": "62", "conditions": "Partly cloudy", "humidity": "65"},
        "status": "complete",
        "timestamp_start": "2025-01-15T10:00:00.123+00:00",
        "timestamp_end": "2025-01-15T10:00:01.456+00:00",
        "prev_hash": prev_hash,
    }
    event1["hash"] = compute_hash(event1)
    events.append(event1)
    prev_hash = event1["hash"]

    # Event 2: Send email with weather summary
    event2 = {
        "schema_version": "1",
        "session_id": session_id,
        "invocation_id": "inv_00002",
        "tool": "send_email",
        "input": {
            "to": "user@example.com",
            "subject": "Weather Update",
            "body": "Current weather in SF: 62F, Partly cloudy"
        },
        "output": {"success": True, "message_id": "msg_abc123"},
        "status": "complete",
        "timestamp_start": "2025-01-15T10:00:02.000+00:00",
        "timestamp_end": "2025-01-15T10:00:02.789+00:00",
        "prev_hash": prev_hash,
    }
    event2["hash"] = compute_hash(event2)
    events.append(event2)
    prev_hash = event2["hash"]

    # Event 3: Log to file
    event3 = {
        "schema_version": "1",
        "session_id": session_id,
        "invocation_id": "inv_00003",
        "tool": "write_file",
        "input": {"path": "/var/log/weather.log", "content": "2025-01-15: SF 62F"},
        "output": {"bytes_written": 22},
        "status": "complete",
        "timestamp_start": "2025-01-15T10:00:03.100+00:00",
        "timestamp_end": "2025-01-15T10:00:03.150+00:00",
        "prev_hash": prev_hash,
    }
    event3["hash"] = compute_hash(event3)
    events.append(event3)

    # Write events.jsonl
    events_file = output_dir / "events.jsonl"
    with open(events_file, "w") as f:
        for event in events:
            f.write(json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n")

    # Write meta.json
    meta = {
        "session_id": session_id,
        "schema_version": "1",
        "lightbox_version": "0.1.0",
        "created_at": "2025-01-15T10:00:00.000+00:00"
    }
    meta_file = output_dir / "meta.json"
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Generated demo session at {output_dir}")
    print(f"  events.jsonl: {len(events)} events")
    print(f"  meta.json: created")


if __name__ == "__main__":
    main()

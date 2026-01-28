# Lightbox Audit Skill — API Reference

## Scripts

### `record.py`

Record a single tool call to the Lightbox audit log.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `--tool` | Yes | Name of the tool being recorded |
| `--input` | Yes | Tool input as a JSON string |
| `--output` | Yes | Tool output as a JSON string |
| `--status` | No | `complete` (default) or `error` |
| `--session` | No | Session ID. Auto-generated if not provided. Can also be set via `MOLTBOT_SESSION_ID` env var |
| `--error-type` | No | Error class name (when status is error) |
| `--error-message` | No | Error description (when status is error) |

**Output:** JSON object `{"status": "recorded", "session_id": "...", "tool": "..."}`

**Environment Variables:**
- `MOLTBOT_SESSION_ID` — Auto-detected session ID
- `MOLTBOT_AGENT_NAME` — Auto-detected actor name
- `LIGHTBOX_DIR` — Override default `~/.lightbox` storage directory

### `verify.py`

Verify the integrity of a session's hash chain.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `session` | No | Session ID to verify (positional) |
| `--last` | No | Use the most recent session |

**Output:** JSON object with `status`, `valid`, `event_count`, and error details if applicable.

**Exit Codes:**
| Code | Meaning |
|------|---------|
| 0 | VALID — Hash chain intact |
| 1 | TAMPERED — Content modified or chain broken |
| 2 | TRUNCATED — Incomplete write detected |
| 3 | PARSE_ERROR — Invalid JSON in event file |
| 4 | NOT_FOUND — Session does not exist |

### `show.py`

Display events from a session as JSON.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `session` | No | Session ID (positional) |
| `--last` | No | Use the most recent session |
| `--inv` | No | Filter to a specific invocation ID |

**Output:** JSON array of event objects.

### `list_sessions.py`

List all available sessions with metadata.

**Arguments:** None.

**Output:** JSON array of session info objects, each containing:
- `session_id` — Unique session identifier
- `event_count` — Number of events recorded
- `first_event` — Timestamp of first event
- `last_event` — Timestamp of last event
- `tools_used` — List of unique tool names
- `schema_version` — Event schema version
- `has_truncation` — Whether truncation was detected
- `has_errors` — Whether parse errors were found

### `dashboard.py`

Launch the Lightbox web dashboard.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `--port` | No | Port number (default: 8780) |
| `--host` | No | Bind address (default: 127.0.0.1) |
| `--no-browser` | No | Don't auto-open browser |

## Event Schema

Each event in the audit log contains:

```json
{
  "schema_version": "1",
  "session_id": "session_abc123...",
  "invocation_id": "inv_00001",
  "tool": "search_web",
  "input": {"query": "weather today"},
  "output": {"results": ["Sunny, 72F"]},
  "status": "complete",
  "timestamp_start": "2025-01-15T10:30:00.000+00:00",
  "timestamp_end": "2025-01-15T10:30:01.500+00:00",
  "prev_hash": "abc123...",
  "hash": "def456..."
}
```

## Hash Chain

Events are cryptographically chained using SHA-256 hashes. Each event's `prev_hash` points to the previous event's `hash`, forming a tamper-evident chain. The first event has `prev_hash: null`.

Verification checks:
1. Each event's hash matches its recomputed hash
2. Each event's `prev_hash` matches the prior event's `hash`
3. First event has `prev_hash: null`

## Storage

Sessions are stored locally at `~/.lightbox/sessions/<session_id>/`:
- `events.jsonl` — Append-only event log (one JSON object per line)
- `meta.json` — Session metadata (version info, creation time)

Override with `LIGHTBOX_DIR` environment variable.

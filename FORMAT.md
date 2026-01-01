# Lightbox Event Format Specification

Version: 1 (schema_version: "1")

## Overview

Lightbox stores tool execution events as append-only JSONL files. Each event
is hash-chained to the previous event, creating a tamper-evident log.

## Storage Layout

```
~/.lightbox/sessions/<session_id>/
    events.jsonl     # Append-only event log (one JSON object per line)
    meta.json        # Session metadata
```

## Session Metadata (meta.json)

```json
{
  "session_id": "session_abc123...",
  "schema_version": "1",
  "lightbox_version": "0.1.0",
  "created_at": "2025-01-15T10:00:00.000+00:00"
}
```

## Event Schema

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | string | Always "1" for this version |
| `session_id` | string | Groups events into one run |
| `invocation_id` | string | Unique per call, format: `inv_NNNNN` |
| `tool` | string | Tool name |
| `input` | object | Arguments passed to the tool |
| `output` | object\|null | Result (null for pending) |
| `status` | string | `pending`, `complete`, or `error` |
| `timestamp_start` | string | ISO 8601 with milliseconds |
| `timestamp_end` | string\|null | ISO 8601 (null for pending) |
| `prev_hash` | string\|null | SHA-256 hash of previous event (null for first) |
| `hash` | string | SHA-256 hash of this event |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| `parent_invocation` | string | ID of parent call for nested invocations |
| `actor` | string | Direct invoker (agent/user/service) |
| `originating_actor` | string | Session initiator |
| `error` | object | Error details when `status=error` |
| `chunk_count` | integer | For streaming, number of chunks |
| `total_bytes` | integer | For streaming, total byte count |
| `content_hashes` | object | Hashes for redacted/large payloads |
| `retry_of` | string | Link to prior attempt's invocation_id |

### Example Event

```json
{
  "schema_version": "1",
  "session_id": "session_92c1...",
  "invocation_id": "inv_00042",
  "tool": "send_email",
  "input": {"to": "user@example.com", "subject": "Hello"},
  "output": {"success": true, "message_id": "msg_123"},
  "status": "complete",
  "timestamp_start": "2025-01-15T10:23:01.123+00:00",
  "timestamp_end": "2025-01-15T10:23:01.456+00:00",
  "prev_hash": "a3f2c1...",
  "hash": "b4e3d2..."
}
```

## Canonicalization Rules

**CRITICAL: These rules MUST NOT change without incrementing schema_version.**

Hash computation uses canonical JSON serialization with these invariants:

1. **Key ordering**: Alphabetical at all nesting levels (`sort_keys=True`)
2. **Whitespace**: None between elements (`separators=(',', ':')`)
3. **Encoding**: UTF-8, no ASCII escaping (`ensure_ascii=False`)
4. **Floats**: PROHIBITED - use string representations for decimals
5. **Strings**: Stored as-is, no Unicode normalization
6. **Nulls**: Serialized as JSON `null`

### Hash Computation

```python
def compute_hash(event_dict):
    # event_dict must include prev_hash but EXCLUDE 'hash' field
    canonical = json.dumps(event_dict, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()
```

## Ordering

**Event order is append order, NOT timestamp order.**

- Events are numbered monotonically within a session
- Timestamps are observational only (may be skewed)
- Verification and replay use append order

## Async Events

Async tool calls produce TWO events:

1. **Pending**: `status=pending`, `output=null`, `timestamp_end=null`
2. **Resolved**: Same `invocation_id`, `status=complete|error`, `input={}`

Both events remain in the hash chain (no overwrites).

## Retries

Each retry attempt is a NEW `invocation_id`. Use `retry_of` to link attempts:

```json
{"invocation_id": "inv_00002", "retry_of": "inv_00001", ...}
```

Failed attempts remain as evidence.

## Redacted Content

When content is redacted (size limits or sensitive keys):

```json
{
  "input": {"api_key": "[REDACTED]"},
  "content_hashes": {"input.api_key": "sha256_hash_here"}
}
```

Oversized content:
```json
{
  "output": {
    "large_field": {
      "_redacted": true,
      "_reason": "size_limit",
      "_bytes": 102400
    }
  },
  "content_hashes": {"output.large_field": "sha256_hash_here"}
}
```

## Compatibility Policy

**Forward compatibility**: Lightbox readers MUST ignore unknown fields. New optional
fields may be added in minor releases without bumping `schema_version`.

**Breaking changes**: Any change to canonicalization rules, hash computation, or
removal/rename of required fields requires incrementing `schema_version`.

**Reader guarantees**:
- Readers supporting schema_version N SHOULD be able to read schema_version < N
- Readers MAY refuse to read schema_version > N (with clear error message)
- Unknown `schema_version` should produce a warning, not silent failure

**Writer guarantees**:
- Writers MUST set `schema_version` to exactly the version they implement
- Writers MUST NOT omit `schema_version` field

## Version History

| Version | Changes |
|---------|---------|
| 1 | Initial release |

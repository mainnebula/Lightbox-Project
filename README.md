# Lightbox

Flight recorder for AI agents. Append-only, tamper-evident tool execution logs.

## What it is / isn't

- Records **tool calls** (send_email, read_file, api_call) - not LLM prompts/responses
- **Append-only** JSONL with SHA-256 hash chaining
- **Offline verification** - no network needed
- **Local-first** - sessions are portable directories you can zip and share
- **Not** a debugger, profiler, or execution controller - recording only

## Quickstart

```bash
pip install lightbox
```

### SDK Usage

```python
from lightbox import Session

session = Session()
session.emit("send_email", {"to": "user@example.com"}, {"success": True})
session.emit("read_file", {"path": "/data.txt"}, {"content": "Hello"})
```

### LangChain Integration

```python
from lightbox.integrations.langchain import wrap

agent = wrap(your_agent)  # Automatically records tool calls
agent.invoke({"input": "Do the thing"})
```

### CLI

```bash
lightbox list                    # Show all sessions
lightbox show <session>          # Display events
lightbox replay <session>        # Animated playback
lightbox verify <session>        # Check integrity
```

## Where logs live

```
~/.lightbox/sessions/<session_id>/
    events.jsonl     # Append-only event log
    meta.json        # Session metadata
```

Override with `LIGHTBOX_DIR` environment variable.

## Exit codes (verify)

| Code | Status | Meaning |
|------|--------|---------|
| 0 | VALID | All checks pass |
| 1 | TAMPERED | Hash mismatch or chain break |
| 2 | TRUNCATED | Incomplete last line (crash mid-write) |
| 3 | PARSE_ERROR | Invalid JSON in event file |
| 4 | NOT_FOUND | Session doesn't exist |

## Redaction

```python
from lightbox import Session, RedactionConfig

config = RedactionConfig(
    redact_keys=["api_key", "password"],  # Always redact
    max_inline_bytes=64 * 1024,           # Hash content over 64KB
)
session = Session(redaction_config=config)
```

## Docs

- [FORMAT.md](FORMAT.md) - Event schema and canonicalization rules
- [SECURITY.md](SECURITY.md) - Threat model
- [PRIVACY.md](PRIVACY.md) - Redaction guide
- [INTEGRATIONS.md](INTEGRATIONS.md) - LangChain usage

## License

MIT

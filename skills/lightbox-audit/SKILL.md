---
name: lightbox-audit
description: Record tamper-evident audit trails of tool executions. Verify integrity of agent session logs. Browse and inspect tool call history with a web dashboard.
license: MIT
compatibility: Requires Python 3.12+ and pip install lightbox-rec
metadata:
  author: lightbox
  version: "0.1.0"
---

# Lightbox Audit Skill

Record, verify, and browse tamper-evident audit trails of tool executions.

## Prerequisites

```bash
pip install lightbox-rec[gui]
```

## Commands

### Record a Tool Call

Record a tool execution during an agent session:

```bash
python scripts/record.py --tool <tool_name> --input '<json>' --output '<json>' [--status complete|error] [--session <session_id>]
```

**Example:**
```bash
python scripts/record.py --tool search_web --input '{"query": "weather today"}' --output '{"results": ["Sunny, 72F"]}'
```

### List Sessions

Show all recorded sessions:

```bash
python scripts/list_sessions.py
```

Output is JSON array of session objects with session_id, event_count, tools_used, and time range.

### Show Session Events

Display events from a session:

```bash
python scripts/show.py <session_id>
python scripts/show.py --last
```

Output is JSON array of event objects for machine-readable consumption.

### Verify Session Integrity

Check that a session's hash chain is intact and no events have been tampered with:

```bash
python scripts/verify.py <session_id>
python scripts/verify.py --last
```

**Exit codes:**
- 0: Valid (hash chain intact)
- 1: Tampered (content modified or chain broken)
- 2: Truncated (incomplete write detected)
- 3: Parse error (invalid JSON in event file)
- 4: Not found

### Launch Web Dashboard

Open the visual dashboard for browsing sessions and events:

```bash
python scripts/dashboard.py [--port 8780] [--no-browser]
```

## Workflow

### During Agent Runs

1. At the start of your session, note the session ID (auto-generated or set via `--session`).
2. Before and after each tool call, use `record.py` to log the execution.
3. After the run, use `verify.py` to confirm integrity.

### Reviewing Past Sessions

1. Run `list_sessions.py` to see all recorded sessions.
2. Run `show.py <session_id>` to inspect events in a specific session.
3. Run `verify.py <session_id>` to verify the hash chain.
4. Run `dashboard.py` to open the web GUI for visual inspection.

## What Gets Recorded

- Tool name, input arguments, and output
- Execution status (complete, error, pending)
- Timestamps (start and end)
- Cryptographic hash chain linking all events

## What Does NOT Get Recorded

- Agent reasoning or prompts
- LLM completions
- Internal state

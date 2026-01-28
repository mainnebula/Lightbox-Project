# Lightbox Integrations

## LangChain

### Supported Versions

- **langchain-core**: 0.3.x (primary target)
- **langchain**: 0.3.x

### Installation

```bash
pip install lightbox-rec[langchain]
```

### Quick Start

```python
from lightbox.integrations.langchain import wrap

# Wrap your agent
agent = create_agent(tools=[...])
agent = wrap(agent)

# All tool calls are now automatically recorded
result = agent.invoke({"input": "..."})
```

### What Gets Recorded

| Event Type | Recorded |
|------------|----------|
| Tool invocations | Yes |
| Tool completions | Yes |
| Tool errors | Yes |
| LLM calls | No |
| Chain execution | No |
| Retriever calls | No |
| Prompts/completions | No |

### Explicit Session Control

```python
from lightbox import Session
from lightbox.integrations.langchain import LightboxCallbackHandler

# Create a session with custom ID
session = Session("my_custom_session")

# Create handler
handler = LightboxCallbackHandler(session=session)

# Use in invoke
result = agent.invoke(
    {"input": "..."},
    config={"callbacks": [handler]}
)

# Session ID for later verification
print(f"Session: {handler.session_id}")
```

### With Redaction

```python
from lightbox import Session
from lightbox.storage import RedactionConfig
from lightbox.integrations.langchain import wrap

config = RedactionConfig(
    redact_keys=["api_key", "password"],
    max_inline_bytes=32 * 1024,
)

session = Session(redaction_config=config)
agent = wrap(agent, session=session)
```

### Canonical Output

LangChain wraps tool outputs in message objects with metadata. Lightbox automatically
extracts the semantic value and stores it in `canonical_output`:

```python
# What LangChain returns (stored in 'output')
{"content": "sunny, 72°F", "type": "tool", "artifact": None, ...}

# What Lightbox extracts (stored in 'canonical_output')
"sunny, 72°F"
```

This makes CLI output and replays more readable without losing the raw data.

### Async Tool Handling

LangChain async tools automatically produce paired events:
1. `on_tool_start` → pending event
2. `on_tool_end` / `on_tool_error` → resolved event

Both events have the same `invocation_id`.

### Nested Tool Calls

If tools call other tools, `parent_invocation` links are preserved:

```json
{"invocation_id": "inv_00002", "parent_invocation": "inv_00001", ...}
```

### Error Handling

- Handler errors don't crash your chain (`raise_error=False`)
- Tool errors are recorded with status `error`
- Error type and message are captured

### Thread Safety

The handler uses locks for concurrent tool calls. Safe for:
- Parallel tool execution
- Async agents
- Multi-threaded applications

## SDK (Framework-Agnostic)

For tools outside framework interception:

```python
from lightbox import Session

# Explicit session (recommended)
session = Session("my_session")
session.emit("tool1", {"x": 1}, {"result": "ok"})
session.emit("tool2", {"y": 2}, {"result": "done"})

# Or use module-level API (auto-creates session)
import lightbox
lightbox.emit("my_custom_tool", {"input": "data"}, {"output": "result"})

# Start explicit session for module-level calls
session = lightbox.start_session("my_session")
lightbox.emit("tool1", {"x": 1}, {"result": "ok"})
```

### Async Pattern

```python
# Start async operation
inv_id = session.emit_pending("slow_tool", {"query": "..."})

# ... do async work ...

# Complete it
session.emit_resolved(inv_id, {"result": "..."})

# Or if it failed
session.emit_resolved(
    inv_id, {},
    status="error",
    error={"message": "Something went wrong"}
)
```

### Canonical Output

When tool outputs include wrapper metadata, extract the semantic value:

```python
# Full output with framework metadata
raw_output = {"content": "result", "metadata": {...}}

# Record with extracted canonical value
session.emit(
    "my_tool",
    {"query": "test"},
    raw_output,
    canonical_output="result"  # Clean value for display
)
```

## Moltbot

Moltbot is a TypeScript/Node.js agent that executes tools via subprocesses (including Python scripts). The Lightbox integration provides wrapper functions that agents can call before/after tool execution.

### Installation

```bash
pip install lightbox-rec[moltbot]
```

### Quick Start — Record a Tool Call

```python
from lightbox.integrations.moltbot import record_tool_call

record_tool_call("search_web", {"query": "weather"}, {"result": "Sunny"})
```

### Wrap a Python Function

```python
from lightbox.integrations.moltbot import wrap_tool

@wrap_tool("my_tool")
def my_tool(query: str) -> dict:
    return {"result": "..."}

# Calling my_tool() now auto-records the execution
result = my_tool("test query")
```

### Hook Class (Before/After)

```python
from lightbox.integrations.moltbot import LightboxMoltbotHook

hook = LightboxMoltbotHook()

# Before tool execution
inv_id = hook.before_tool("search_web", {"query": "test"})

# ... execute tool ...

# After success
hook.after_tool(inv_id, {"results": [...]})

# Or after failure
hook.after_tool_error(inv_id, error_type="TimeoutError", message="Timed out")
```

### Moltbot Session

`MoltbotSession` extends Session with Moltbot-specific defaults:

```python
from lightbox.integrations.moltbot import MoltbotSession

session = MoltbotSession()
# actor defaults to "moltbot"
# Automatically picks up MOLTBOT_SESSION_ID and MOLTBOT_AGENT_NAME env vars
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `MOLTBOT_SESSION_ID` | Auto-detect session ID |
| `MOLTBOT_AGENT_NAME` | Auto-detect actor name |

### Agent Skill

An Agent Skill is available for Moltbot integration at `skills/lightbox-audit/`. Copy it to your skills directory to enable direct Moltbot usage.

### Web Dashboard

Launch the web GUI to browse sessions visually:

```bash
lightbox gui
# or
lightbox gui --port 8780 --no-browser
```

## Planned Integrations

| Framework | Status |
|-----------|--------|
| LangChain | Supported |
| Moltbot | Supported |
| LangGraph | Planned |
| AutoGen | Planned |
| CrewAI | Planned |
| Custom agents | Use SDK |

## Integration Development

To add a new integration:

1. Create `src/lightbox/integrations/<framework>.py`
2. Implement framework-specific callback/hook mechanism
3. Map to `session.emit()` / `emit_pending()` / `emit_resolved()`
4. Add tests in `tests/test_integration_<framework>.py`
5. Document in this file

Key requirements:
- Only capture tool executions
- Don't capture LLM calls (maintain "no reasoning capture" principle)
- Handle async tools with pending/resolved pattern
- Be thread-safe
- Don't crash the host framework on recording errors

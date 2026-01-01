# Lightbox Integrations

## LangChain

### Supported Versions

- **langchain-core**: 0.3.x (primary target)
- **langchain**: 0.3.x

### Installation

```bash
pip install lightbox[langchain]
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
import lightbox

# Simple emit
lightbox.emit(
    "my_custom_tool",
    {"input": "data"},
    {"output": "result"}
)

# With session
session = lightbox.start_session("my_session")
session.emit("tool1", {...}, {...})
session.emit("tool2", {...}, {...})
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

## Planned Integrations

| Framework | Status |
|-----------|--------|
| LangChain | Supported |
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

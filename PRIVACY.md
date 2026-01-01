# Lightbox Privacy Guide

## What Lightbox Records

Lightbox records **tool execution events** including:

- Tool names
- Input arguments
- Output results
- Error messages
- Timestamps
- Execution metadata

## What Lightbox Does NOT Record

- LLM prompts or completions
- Model reasoning or chain-of-thought
- Internal agent state
- Non-tool operations

## Sensitive Data Handling

### Built-in Redaction

Configure redaction when creating a session:

```python
from lightbox import Session
from lightbox.storage import RedactionConfig

config = RedactionConfig(
    redact_keys=["api_key", "token", "password", "secret", "credential"],
    max_inline_bytes=64 * 1024,  # 64KB limit
    hash_oversized=True,
)

session = Session(redaction_config=config)
```

### What Gets Redacted

1. **Sensitive keys**: Specified keys are replaced with `"[REDACTED]"`
2. **Large payloads**: Content over `max_inline_bytes` is replaced with metadata
3. **Content hashes**: Original content hashes are preserved for verification

### Redacted Output Example

```json
{
  "input": {
    "api_key": "[REDACTED]",
    "query": "normal data here"
  },
  "output": {
    "large_response": {
      "_redacted": true,
      "_reason": "size_limit",
      "_bytes": 102400
    }
  },
  "content_hashes": {
    "input.api_key": "e3b0c44298fc1c14...",
    "output.large_response": "a1b2c3d4e5f6..."
  }
}
```

## Recommended Redaction Keys

```python
DEFAULT_SENSITIVE_KEYS = [
    # Authentication
    "api_key", "apikey", "api-key",
    "token", "access_token", "refresh_token",
    "password", "passwd", "pwd",
    "secret", "secret_key",
    "credential", "credentials",

    # Personal data
    "ssn", "social_security",
    "credit_card", "card_number",

    # Infrastructure
    "private_key", "ssh_key",
    "database_url", "connection_string",
]
```

## Storage Location

Sessions are stored at:
- Default: `~/.lightbox/sessions/`
- Override: Set `LIGHTBOX_DIR` environment variable

## Data Retention

Lightbox does not automatically delete sessions. Implement your own retention:

```bash
# Delete sessions older than 30 days
find ~/.lightbox/sessions -type d -mtime +30 -exec rm -rf {} +
```

## Compliance Considerations

### GDPR

If tool inputs/outputs contain personal data:
1. Configure redaction for PII fields
2. Document the legal basis for logging
3. Implement deletion procedures for data subject requests

### SOC 2

Lightbox event logs can support:
- Audit trail requirements (CC7.2)
- Change management evidence (CC8.1)

### HIPAA

For healthcare applications:
1. Enable redaction for PHI fields
2. Ensure appropriate access controls on `~/.lightbox`
3. Consider encryption at rest

## CLI Privacy Options

```bash
# View session without storing any new data
lightbox show <session> --raw | jq '.tool'

# Verify without reading full content
lightbox verify <session>
```

## Best Practices

1. **Minimize data collection**: Only record what you need
2. **Redact by default**: Configure sensitive keys upfront
3. **Size limits**: Prevent accidental large data capture
4. **Access control**: Protect the sessions directory
5. **Retention policy**: Don't keep logs forever
6. **Audit access**: Monitor who reads session logs

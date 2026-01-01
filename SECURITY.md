# Lightbox Security Model

## What Lightbox Provides

Lightbox is a **flight recorder for AI agents** that creates tamper-evident
logs of tool executions. It provides:

1. **Append-only logging**: Events can only be added, never modified
2. **Hash chain integrity**: Each event includes the hash of the previous
3. **Offline verification**: No network required to verify a session
4. **Content integrity**: Any modification is detectable

## What Lightbox Does NOT Provide

1. **Confidentiality**: Event logs are stored in plaintext
2. **Authentication**: No proof of WHO created the log
3. **Non-repudiation**: Without signatures, origin cannot be proven
4. **Secure storage**: Files use standard filesystem permissions

## Threat Model

### Threats Addressed

| Threat | Mitigation |
|--------|------------|
| Accidental corruption | Hash chain detects any bit changes |
| Naive tampering | Hash mismatch immediately detected |
| Event deletion | Chain break detected at deletion point |
| Event insertion | Chain break at insertion point |
| Event reordering | prev_hash mismatches reveal reordering |
| Truncation (crash) | Distinct from tampering via incomplete line detection |

### Threats NOT Addressed (v1)

| Threat | Status |
|--------|--------|
| Malicious operator (full log replacement) | Not addressed - requires external anchoring |
| Selective disclosure attacks | Not addressed - no signatures |
| Timing attacks | Not addressed - timestamps are observational |
| Side-channel attacks | Not addressed |

## Verification

```bash
lightbox verify <session>
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Valid - hash chain intact |
| 1 | Tampered - content modified or chain broken |
| 2 | Truncated - incomplete write detected (likely crash) |
| 3 | Parse error - invalid JSON |
| 4 | Not found |

### What Verification Checks

1. Each event's hash matches its computed hash
2. Each event's `prev_hash` matches the previous event's hash
3. First event has `prev_hash=null`
4. No truncated/incomplete lines (except crash recovery)

### What Verification Does NOT Check

1. Timestamps are accurate
2. Tool outputs are truthful
3. Events are complete (no dropped events before recording)
4. Log hasn't been entirely replaced

## Future Security Enhancements

### Planned (not in v1)

1. **Per-session signatures**: Sign the final hash to prove authorship
2. **External anchoring**: Publish session hashes to immutable stores
3. **Timestamping**: Third-party timestamp services for time proofs

### Hash Algorithm

v1 uses SHA-256. This provides:
- 256-bit collision resistance
- Widely supported and audited
- Sufficient for integrity verification

## Recommendations

### For Operators

1. Protect the `~/.lightbox` directory with appropriate permissions
2. Back up sessions to immutable storage for long-term evidence
3. Consider external anchoring for high-stakes applications

### For Auditors

1. Verify sessions immediately upon receipt
2. Compare session hashes out-of-band when possible
3. Check for truncation warnings (may indicate interrupted writes)

### For Developers

1. Don't store secrets in tool inputs/outputs - use redaction
2. Consider size limits for large payloads
3. Use the `content_hashes` field when redacting for verifiability

## Responsible Disclosure

For security issues, please email [security contact] rather than opening
a public issue.

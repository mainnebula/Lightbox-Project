# Changelog

All notable changes to Lightbox will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-01-15

### Added
- Initial release of Lightbox flight recorder
- Core event logging with hash-chained integrity
- Session management (`Session` class, `emit()` API)
- CLI commands: `list`, `show`, `replay`, `verify`
- LangChain integration via callback handler (`LightboxCallbackHandler`)
- Redaction support for sensitive keys and oversized content
- Distinct verification status codes (VALID, TAMPERED, TRUNCATED, PARSE_ERROR, NOT_FOUND)
- Documentation: FORMAT.md, SECURITY.md, PRIVACY.md, INTEGRATIONS.md

### Schema
- Schema version: 1
- Canonicalization: sorted keys, no whitespace, no floats, UTF-8

[Unreleased]: https://github.com/robertkeenan/lightbox/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/robertkeenan/lightbox/releases/tag/v0.1.0

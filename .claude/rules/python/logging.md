---
paths:
  - "**/*.py"
---

# Python — Logging

- `logging.getLogger(__name__)`, once per module. `ERROR` means someone must look — never for an
  expected user mistake.
- **Never log secrets or PII** — tokens, passwords, card numbers, raw request payloads. Log
  identifiers, not objects, as fields in `extra={...}` rather than formatted into the message.
- Message style: lower-case start, no trailing punctuation, present tense, event first then
  context — `"payment captured"`, not `"Captured the payment successfully!"`.
- Configure logging **once** at the entry point, never in a library or on import. **Logs are
  JSON**, one object per line, so every `extra=` field arrives as a field a search can filter on.
- Timing and counters are metrics, not logs (`python-observability`); never log in a hot loop.

---
paths:
  - "**/*.py"
---

# Python - Logging

- **Never log a secret or personal data.** Tokens, passwords, card numbers and raw request payloads leak to everyone who reads the logs.
- **Pass identifiers in `extra=`, never formatted into the message.** A search cannot filter on a string.
- **Log at `ERROR` only what someone must look at, never an expected user mistake.**

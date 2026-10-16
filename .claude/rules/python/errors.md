---
paths:
  - "**/*.py"
---

# Python - Errors

## Raising

- **Catch narrowly, around the line that fails, where the failure can be handled.** A broad `except` swallows the bug along with the expected failure, and a `try` around everything hides which line failed.
- **Catch only in a layer that retries, falls back, converts or reports, and log the failure once there.** A layer that can only log and re-raise adds a second log line.
- **Translate an error with `from` its cause.** A driver's error re-raised without it loses the cause.
- **Never return `None`, `False` or `-1` for an error.** The caller carries on with nonsense; `-> User | None` is for a lookup where absence is normal.
- **Treat an outcome the caller would count as success as success, never a guess in place of an error.** `cancel` on a cancelled booking and `delete` of a missing key promise a state, so a retry needs no special case; a clipped index or an empty list for "not found" is a guess.
- **Put the identifying values in the message, and on the exception as attributes.** A message that names nothing cannot be looked up, and a handler that parses the text breaks when the wording changes.

## The Hierarchy

- **Give each package one root exception, and add a leaf only for a caller who catches it alone.** The root lets a caller catch the whole package in one clause and alone carries the package prefix; a leaf names what went wrong.
- **Make a leaf inherit `LookupError`, `ValueError` or `TypeError` where stdlib code catches it, never an `OSError` subtype.** A `Mapping`'s missing key must be a `KeyError` or `in` and `.get()` break; `PermissionError` and `TimeoutError` carry errno semantics, and an `except OSError` around a socket swallows the domain failure.

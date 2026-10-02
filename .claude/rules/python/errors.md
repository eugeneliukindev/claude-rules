---
paths:
  - "**/*.py"
---

# Python — Errors and Logging

## Errors

The example below carries the four broken most often: the narrowest `except` the guarded lines
need, a `try` around only those lines, a driver's error translated with `raise … from`, and never
`None` as an error.

- **Messages include the identifying values**: `f"Order {order_id} cannot be shipped: status is
  {status}"`, not `"Invalid order"`.
- **Every package defines one root exception**, `<Package>Error(Exception)`, and all its own
  exceptions inherit from it, so callers can catch "anything from this library" with one clause.
  Inherit the closest stdlib type as well when the meaning matches:
  `UserNotFoundError(AppError, LookupError)`. Exceptions **carry data as attributes**, not only
  text.
- **`None` is for `find_…`-style lookups where absent is normal**; a function whose name promises a
  value raises instead of returning `None`, `False`, `-1` or an empty collection.
- **EAFP when the failure is rare and checking would race; LBYL when the check is cheap, atomic and
  the missing case is common.** Never both.
- **Catch at the level that can handle it** — retry, fall back, convert, report. A layer that can
  only log and re-raise should not catch at all. Log once, at the boundary that handles it.

```python
# WRONG — broad catch, swallowed cause, a try around everything, the error returned as None
def load_user(client: Client, user_id: UserId) -> User | None:
    try:
        response = client.get(f"/users/{user_id}")
        response.raise_for_status()
        return User.from_payload(response.json())
    except Exception:
        logger.error("failed")
        return None

# CORRECT — narrow try, translated with its cause, an error is never a return value
def load_user(client: Client, user_id: UserId) -> User:
    try:
        response = client.get(f"/users/{user_id}")
        response.raise_for_status()
    except HTTPStatusError as error:
        if error.response.status_code == HTTPStatus.NOT_FOUND:
            raise UserNotFoundError(user_id) from error
        raise UserServiceError(f"Fetching user {user_id} failed") from error
    return User.from_payload(response.json())
```

## Logging

- `logging.getLogger(__name__)`, once per module. `ERROR` means someone must look — never for an
  expected user mistake.
- **Never log secrets or PII** — tokens, passwords, card numbers, raw request payloads. Log
  identifiers, not objects, and structured fields (`extra={...}`) rather than text encoding them.
- Message style: lower-case start, no trailing punctuation, present tense, event first then
  context — `"payment captured"`, not `"Captured the payment successfully!"`.
- Configure logging **once** at the entry point, never in a library or on import. Timing and
  counters are metrics, not logs; never log in a hot loop.

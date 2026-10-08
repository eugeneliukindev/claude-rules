---
paths:
  - "**/*.py"
---

# Python — Errors

The example below carries the four broken most often: the narrowest `except` the guarded lines
need, a `try` around only those lines, a driver's error translated with `raise … from`, and never
`None` as an error.

- **Messages include the identifying values**: `f"Order {order_id} cannot be shipped: status is
  {status}"`, not `"Invalid order"`.
- **Every package defines one root exception, named for the package** — `BillingError(Exception)`
  — and all its own exceptions inherit from it, so callers catch "anything from billing" with one
  clause.
- **A leaf class is earned by a caller who catches it on its own**; until then raise the nearest
  category with the identifying values. A leaf names the failure without the prefix (`naming.md`)
  and inherits the closest stdlib type too — `InvoiceNotFoundError(BillingError, LookupError)` —
  so stdlib code catches it: a missing key from a `Mapping`'s `__getitem__` must be a `KeyError`,
  or `in` and `.get()` break. Exceptions **carry data as attributes**, not only text.
- **`None` is for lookups where absence is normal**, and `-> User | None` says so; a signature that
  promises a value raises instead of returning `None`, `False`, `-1` or an empty list.
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

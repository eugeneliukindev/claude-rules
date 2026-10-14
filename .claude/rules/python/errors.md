---
paths:
  - "**/*.py"
---

# Python — Errors

## Raising

### A failure is caught narrowly, translated with its cause, and never returned as `None`

**Why:** a broad `except` swallows the bug along with the expected failure, a `try` around
everything hides which line failed, a driver's error re-raised without `from` loses its cause, and
`None`, `False` or `-1` for an error lets the caller carry on with nonsense. `-> User | None` is for
a lookup where absence is normal.

**Example:**
```python
# WRONG — broad catch, swallowed cause, a try around everything, the error returned as None
def load_user(
    user_id: UserId, *, base_url: str, timeout_seconds: float = _TIMEOUT_SECONDS
) -> User | None:
    try:
        with urlopen(f"{base_url}/users/{user_id}", timeout=timeout_seconds) as response:
            return User.from_payload(json.load(response))
    except Exception:
        logger.error("failed")
        return None


# CORRECT — narrow try, translated with its cause, an error is never a return value
def load_user(
    user_id: UserId, *, base_url: str, timeout_seconds: float = _TIMEOUT_SECONDS
) -> User:
    try:
        with urlopen(f"{base_url}/users/{user_id}", timeout=timeout_seconds) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code == HTTPStatus.NOT_FOUND:
            raise UserNotFoundError(user_id) from error
        raise UserServiceError(f"Fetching user {user_id} failed") from error
    return User.from_payload(payload)
```

### An outcome the caller would treat as success is not an error

**Why:** `cancel` on a cancelled booking and `delete` of a missing key promise a state, and they
succeed — a retry then needs no special case.
**Except:** never a guess in place of an error — a clipped index, an empty list for "not found".

### A message carries the identifying values, and the exception carries them as attributes

**Why:** `"Bad ticket"` in a log names nothing a reader can look up; a handler that has to parse
the text to learn which ticket failed breaks when the wording changes.

**Example:**
```python
# WRONG — nothing to search for, nothing to read programmatically
class TicketNotTransferableError(TicketingError):
    pass


raise TicketNotTransferableError("Bad ticket")


# CORRECT — the values in the message and on the object
class TicketNotTransferableError(TicketingError):
    def __init__(self, ticket_id: TicketId, *, event_starts_at: datetime) -> None:
        super().__init__(f"Ticket {ticket_id} cannot be transferred after {event_starts_at}")
        self.ticket_id = ticket_id
        self.event_starts_at = event_starts_at
```

## The Hierarchy

### One root exception per package; a leaf names the failure and inherits what stdlib catches

**Why:** `CatalogError(Exception)` lets a caller catch "anything from the catalog" with one clause,
and is the one name that carries the package's prefix — a leaf says what went wrong, not where. A
leaf is earned by a caller who catches it alone, and inherits `LookupError`, `ValueError` or
`TypeError` where stdlib code catches it — a `Mapping`'s missing key must be a `KeyError`, or `in`
and `.get()` break.
**Except:** never an `OSError` subtype — `PermissionError`, `TimeoutError` carry errno semantics,
and an `except OSError` around a socket swallows the domain failure.

**Example:**
```python
# WRONG — no root to catch, and PermissionError makes it an OSError
class ProductNotFoundError(Exception): ...


class AccessDeniedError(PermissionError): ...


# CORRECT — one root per package; a leaf adds the stdlib type its callers expect
class CatalogError(Exception): ...


class ProductNotFoundError(CatalogError, KeyError): ...


class AccessDeniedError(CatalogError): ...
```

## Handling

### An error is caught where it can be handled, and logged once there

**Why:** retry, fall back, convert or report — a layer that can only log and re-raise adds a second
log line for the same failure and handles nothing.

**Example:**
```python
# WRONG — logged here, re-raised, and logged again by whoever handles it
def charge(invoice: Invoice, *, gateway: PaymentGateway) -> Receipt:
    try:
        return gateway.charge(invoice.number, invoice.total)
    except PaymentDeclinedError:
        logger.exception("charge failed", extra={"invoice_number": invoice.number})
        raise


# CORRECT — no try at all; the boundary that decides what to do logs it once
def charge(invoice: Invoice, *, gateway: PaymentGateway) -> Receipt:
    return gateway.charge(invoice.number, invoice.total)
```

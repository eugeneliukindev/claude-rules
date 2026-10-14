---
paths:
  - "**/*.py"
---

# Python — Functions

## Parameters

### The subject first, then required inputs; dependencies and options by keyword after `*`

**Why:** the call reads as being about its subject, a new dependency never shifts a position, and
the root binds dependencies with `partial(f, mailer=...)`.
**Except:** a payload a library hands in, its name meaning nothing to the caller, is positional-only
(`/`); a signature a framework dictates keeps the framework's order.

**Example:**
```python
# WRONG — the dependency first: the call reads as if it were about the mail
def send_receipt(mailer: Mailer, payment: Payment) -> None:
    mailer.send(payment.customer_email, f"Receipt for {payment.amount}")


# CORRECT — the subject first, the dependency named at every call
def send_receipt(payment: Payment, *, mailer: Mailer) -> None:
    mailer.send(payment.customer_email, f"Receipt for {payment.amount}")
```

### Values that travel together become one frozen dataclass

**Why:** the same four parameters on five functions are a concept without a name, and the next
function gets three of them in another order; its invariant is checked once, in `__post_init__`.

### A boolean that selects between two behaviours is two functions, or a `Literal` or `Enum`

**Why:** `export(readings, as_csv=True)` hides two bodies behind one name, keyword-only or not.
**Except:** a keyword-only boolean that tunes one behaviour — `sorted(reverse=)` — is fine; the test
is whether the branches share a body.

### A setting is a keyword parameter defaulted to its constant — never the settings object

**Why:** a timeout, a limit, a TTL, a size, a width, a duration, a retry count, the set of statuses
worth retrying, a path — read in the body, it can be changed only by patching the module; defaulted
in the signature, a caller passes nothing and a test passes what it needs. A function taking
`settings: Settings` hides what it reads and makes a test build the whole tree; the entry point
reads the settings and unpacks them into plain values, or a frozen config dataclass for a group that
travels together. A constructor keeps each in a field.
**Except:** the root (`main`, `run`, `lifespan`), a test, a fixture and a signature a framework
parses — a route, a subscriber, a resolver, where a defaulted parameter is an input the client
sets — read the constant where they stand. A value a format or a protocol fixes, a query, a
dispatch table and a security allowlist are code, not settings, and stay in the body.

**Example:**
```python
# WRONG — the limit is read inside: a test of the rejection must upload twenty megabytes
@final
class UploadInbox:
    def __init__(self, *, storage: ObjectStorage) -> None:
        self._storage = storage

    def accept(self, upload: Upload) -> str:
        if upload.size_bytes > _MAX_UPLOAD_BYTES:
            raise UploadTooLargeError(upload.name, limit_bytes=_MAX_UPLOAD_BYTES)
        return self._storage.put(upload.name, upload.content)


# CORRECT — the root passes nothing, and a test of the rejection passes ten bytes
@final
class UploadInbox:
    def __init__(
        self, *, storage: ObjectStorage, max_upload_bytes: int = _MAX_UPLOAD_BYTES
    ) -> None:
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes

    def accept(self, upload: Upload) -> str:
        if upload.size_bytes > self._max_upload_bytes:
            raise UploadTooLargeError(upload.name, limit_bytes=self._max_upload_bytes)
        return self._storage.put(upload.name, upload.content)
```

### A function uses only its parameters and module constants

**Why:** global mutable state, an imported `settings`, a clock or randomness read inside are inputs
no caller can see and no test can fix; the time arrives as `now` or an injected clock.
**Except:** a fresh identifier whose value no test compares, and a monotonic reading that only
measures a duration, are made inside.

**Example:**
```python
# WRONG — the clock and the lifetime come from outside, and no test can fix either
def is_expired(token: AccessToken) -> bool:
    return datetime.now(UTC) > token.issued_at + settings.token_lifetime


# CORRECT — both arrive as parameters
def is_expired(token: AccessToken, *, now: datetime, lifetime: timedelta) -> bool:
    return now > token.issued_at + lifetime
```

### Each value a later call needs is named on its own line, and the steps fall into blocks

**Why:** a value built inside another call's arguments hides a step, and when one sibling is named
and the other inlined, the asymmetry suggests a difference that is not there; a blank line separates
what is shared, what is built from it and what is assembled.
**Except:** a trivial conversion or a literal — `str(order_id)`, `Decimal("0.2")` — stays inline.

## Extraction

### A helper is extracted only when it pays

**Why:** a helper's name and signature are an interface that pays only by hiding more than it
exposes. Extract for **real reuse** today, when it is **required as an object** (a callback, a
`key=`), when it **hides genuine complexity**, when the parent would otherwise **break its
limits**, when it **needs its own test seam**, or for a **named predicate** (`control-flow.md`).
Inline it when the body is one call or one expression, the reader opens it anyway, or its name is a
moment (`_step_two`, `_log_outcome`) rather than an action.

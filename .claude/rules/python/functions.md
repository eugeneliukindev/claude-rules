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

### A function reads only its parameters; a clock, randomness and a setting arrive as parameters, a setting defaulted to its module constant — never the settings object

**Why:** global mutable state, an imported `settings`, a clock or randomness read inside are inputs
no caller can see and no test can fix — a timeout, a limit, a TTL, a size, a width, a duration, a
retry count, the set of statuses worth retrying or a path read in the body changes only by patching
the module. The time arrives as `now` or an injected clock; a setting defaulted in the signature
lets a caller pass nothing and a test pass what it needs, and a constructor keeps each in a field.
`settings: Settings` hides what a function reads and makes a test build the whole tree; the entry
point unpacks it into plain values, or a frozen config dataclass for a group that travels together.
**Except:** the root (`main`, `run`, `lifespan`), a test, a fixture and a signature a framework
parses — a route, a subscriber, a resolver, where a defaulted parameter is an input the client
sets — read the constant where they stand. A value a format or a protocol fixes, a query, a
dispatch table and a security allowlist are code, not settings, and stay in the body. A fresh
identifier whose value no test compares, and a monotonic reading that only measures a duration, are
made inside.

**Example:**
```python
# WRONG — the clock and the lifetime are read inside, and no test can fix either
def is_expired(token: AccessToken) -> bool:
    return datetime.now(UTC) > token.issued_at + settings.token_lifetime


# CORRECT — the time arrives, and the lifetime is defaulted to its constant
def is_expired(
    token: AccessToken, *, now: datetime, lifetime: timedelta = _TOKEN_LIFETIME
) -> bool:
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

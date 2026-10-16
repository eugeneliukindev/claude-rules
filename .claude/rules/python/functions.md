---
paths:
  - "**/*.py"
---

# Python - Functions

## Parameters

### The subject first, then required inputs; dependencies and options by keyword after `*`

**Why:** the call reads as being about its subject, a new dependency never shifts a position, and
the root binds dependencies with `partial(f, mailer=...)`.
**Except:** a payload a library hands in, its name meaning nothing to the caller, is positional-only
(`/`); a signature a framework dictates keeps the framework's order.

**Example:**
```python
# WRONG - the dependency first: the call reads as if it were about the mail
def send_receipt(mailer: Mailer, payment: Payment) -> None:
    mailer.send(payment.customer_email, f"Receipt for {payment.amount}")


# CORRECT - the subject first, the dependency named at every call
def send_receipt(payment: Payment, *, mailer: Mailer) -> None:
    mailer.send(payment.customer_email, f"Receipt for {payment.amount}")
```

### Values that travel together become one frozen dataclass

**Why:** the same four parameters on five functions are a concept without a name, and the next
function gets three of them in another order; its invariant is checked once, in `__post_init__`.

### A boolean that selects between two behaviours is two functions, or a `Literal` or `Enum`

**Why:** `export(readings, as_csv=True)` hides two bodies behind one name, keyword-only or not.
**Except:** a keyword-only boolean that tunes one behaviour - `sorted(reverse=)` - is fine; the test
is whether the branches share a body.

### A function reads only its parameters; a clock, randomness and a setting arrive as parameters, a setting defaulted to its module constant - never the settings object

**Why:** a clock or a setting read inside - a timeout, a TTL, the statuses worth retrying - is an
input no test fixes without patching. A default in the signature, or a constructor's, lets a test
pass what it needs; `settings: Settings` makes it build the whole tree.
**Except:** the root, a test, a fixture and a framework-parsed signature (a route) read the
constant; a value a protocol fixes, a query, a dispatch table, a security allowlist, an uncompared
identifier and a monotonic duration stay in the body.

**Example:**
```python
# WRONG - the clock and the lifetime are read inside, and no test can fix either
def is_expired(token: AccessToken) -> bool:
    return datetime.now(UTC) > token.issued_at + settings.token_lifetime


# CORRECT - the time arrives, and the lifetime is defaulted to its constant
def is_expired(
    token: AccessToken, *, now: datetime, lifetime: timedelta = _TOKEN_LIFETIME
) -> bool:
    return now > token.issued_at + lifetime
```

### Each value a later call needs is named on its own line, and the steps - fetch, act, return - are blocks separated by a blank line

**Why:** a value built inside another call's arguments hides a step, and when one sibling is named
and the other inlined, the asymmetry suggests a difference that is not there. One blank line goes
between the steps - what is fetched, what is done with it, what is returned - and none inside one.
**Except:** a trivial conversion or a literal - `str(order_id)`, `Decimal("0.2")` - stays inline.

**Example:**
```python
# WRONG - one channel named, its sibling built inside the constructor call, no blocks
def build_sensor_pipeline(
    *, site: str, serial_port: str, station_name: str = _STATION_NAME
) -> SensorPipeline:
    station = StationIdentity(name=station_name, site=site)
    readings = open_reading_stream(station, port=serial_port)
    return SensorPipeline(readings, open_alarm_channel(station, port=serial_port))


# CORRECT - what is shared, what is built from it, what is assembled: one block each
def build_sensor_pipeline(
    *, site: str, serial_port: str, station_name: str = _STATION_NAME
) -> SensorPipeline:
    station = StationIdentity(name=station_name, site=site)

    readings = open_reading_stream(station, port=serial_port)
    alarms = open_alarm_channel(station, port=serial_port)

    return SensorPipeline(readings, alarms)
```

## Results

### A query has no side effect; a command returns `None` or the outcome of its own effect

**Why:** a query can be called twice or skipped; a command's return is what its effect produced -
`list.pop()` the item it removed, `dict.setdefault()` the value now under the key, `open_session()`
the id it assigned. Never a value a reader would take for a lookup, and never behind a `get_`
(`naming.md`).

## Extraction

### A helper is extracted only when it pays

**Why:** a helper's name and signature are an interface that pays only by hiding more than it
exposes. Extract for **real reuse** today, when it is **required as an object** (a callback, a
`key=`), when it **hides genuine complexity**, when the parent would otherwise **break its
limits**, when it **needs its own test seam**, or for a **named predicate** (`control-flow.md`).
Inline it when the body is one call or one expression, the reader opens it anyway, or its name is a
moment (`_step_two`, `_log_outcome`) rather than an action.

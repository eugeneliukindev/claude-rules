---
name: python-examples
description: >-
  Sets the standard for Python examples that ship: the smallest complete thing, executed,
  realistic reserved data, deterministic output, versioned with the API. Use when writing a
  docstring example, a README snippet or a file under examples/ that will be published.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Shipped Examples

An example is executable documentation: copy-paste is how it is consumed, so it follows every rule
the code does — a bare `except` in an example is taught to every reader — and it must also run. An
anti-pattern appears only marked `# WRONG` beside a `# CORRECT`.

### An example is the smallest complete thing: every import and object is built inside it

**Why:** an example that starts mid-story is unusable and unverifiable — the reader guesses where
the client came from, and no test can run it. One capability, chosen by what callers do most, with
the one value that proves the point printed.

**Example:**
```python
# WRONG — starts mid-story: the reader has to guess where client and Notification come from
receipt = client.send(Notification(recipient="ann@example.com", subject="Your parcel shipped"))
print(receipt.status)

# CORRECT — every import and every object the snippet uses is built inside it
from notifications import Notification, NotificationClient

with NotificationClient(base_url="https://api.example.com", timeout_seconds=10.0) as client:
    receipt = client.send(Notification(recipient="ann@example.com", subject="Your parcel shipped"))
print(receipt.status)
```

### Examples are executed by the suite, and the output shown is the output a run produced

**Why:** an example nobody runs is wrong within a release or two. An example file is included by
the docs page and imported or run by a test, so the linter and the type checker cover it like any
module. Inline snippets run under `pytest-examples`, which compares what each block prints with the
`#>` comments under it. A `>>>` example runs under `pytest --doctest-modules` in its module's
namespace: the module's constants are there, and what it needs from elsewhere — a fixed clock, a
fake — it builds itself.

**Example:**
```toml
# WRONG — the >>> examples are never collected, and their outputs drift unseen
[tool.pytest]
testpaths = ["tests"]

# CORRECT — every docstring example runs with the suite
[tool.pytest]
testpaths = ["tests", "src"]
addopts = ["--doctest-modules"]
```

### Example data is plausible and reserved: never filler, never real

**Why:** `foo` and `test123` say nothing about what the field holds, and `bar.com` or `1.2.3.4` are
real hosts someone will hit. `example.com` and RFC 5737's documentation ranges can never resolve to
anyone. A real key, token, hostname or customer name never appears, not even redacted.

**Example:**
```python
# WRONG — filler that means nothing, and neither bar.com nor 1.2.3.4 is reserved for examples
user = User(name="foo", email="test123@bar.com", ip_address="1.2.3.4")

# CORRECT — plausible values from the reserved ranges: example.com and RFC 5737's 192.0.2.0/24
user = User(name="Ann Lee", email="ann@example.com", ip_address="192.0.2.10")
```

### The output is deterministic: time, ids and order are pinned

**Why:** a shown output that differs on every run cannot be compared, by a reader or by
`pytest-examples`. A fixed clock, a literal UUID, and a sort before printing make it the same each
time.

**Example:**
```python
# WRONG — a new id and time on every run, and a set of strings reorders between processes
receipt = send_reminder(invoice, sent_at=datetime.now(UTC), reminder_id=uuid4())
print(receipt.reminder_id, receipt.sent_at, receipt.channels)

# CORRECT — the clock and the id are literals, and the set is sorted before printing
receipt = send_reminder(
    invoice,
    sent_at=datetime(2026, 1, 15, 9, 30, tzinfo=UTC),
    reminder_id=UUID("8f14e45f-ceea-467f-a0b7-0c7a1c3e5a10"),
)
print(receipt.reminder_id, receipt.sent_at, sorted(receipt.channels))
```

### The happy path is one example, and each failure a caller must handle is another

**Why:** error handling folded into the main example buries the capability under branches the
reader did not come for, and still leaves out the failures it did not think of. One example per
error the caller must handle shows what to catch and what to do.

**Example:**
```python
# WRONG — the main example is mostly error handling, and swallows what it does not name
try:
    receipt = client.send(notification)
    print(receipt.status)
except Exception as error:
    print(f"failed: {error}")


# CORRECT — the happy path alone; the rejected recipient is the next example
receipt = client.send(notification)
print(receipt.status)
```

### A deprecated path leaves the examples in the release that deprecates it

**Why:** examples are versioned with the API; an example still showing the old call keeps teaching
it, and every copy of it emits a `DeprecationWarning` that fails a suite running warnings as errors.

**Example:**
```python
# WRONG — deprecated in 4.0 and still the documented way
receipt = client.send_email(recipient="ann@example.com", subject="Your parcel shipped")

# CORRECT — the example moved in the same release as the deprecation
receipt = client.send(Notification(recipient="ann@example.com", subject="Your parcel shipped"))
```

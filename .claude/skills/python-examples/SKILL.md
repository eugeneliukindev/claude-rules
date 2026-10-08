---
name: python-examples
description: >-
  Standards for Python examples that ship — a docstring example, a README snippet, a file under
  examples/: the smallest complete thing, executed rather than proofread, ordered by the caller's
  goal, realistic reserved data such as example.com, deterministic output, one example per error
  scenario, and versioned with the API. Use when writing or reviewing a Python example, docstring
  sample or README snippet that will be published.
---

# Shipped Examples

An example is executable documentation, held to the same standard as the code it demonstrates,
plus one extra requirement — it must run.

- **Show the smallest complete thing.** One capability, with every import and object constructed
  inside it. An example that starts mid-story is unusable and unverifiable.

```python
# WRONG — starts mid-story: the reader has to guess where client and Notification come from
receipt = client.send(Notification(recipient="ann@example.com", subject="Your order shipped"))
print(receipt.status)

# CORRECT — every import and every object the snippet uses is built inside it
from notifications import Notification, NotificationClient

with NotificationClient(base_url="https://api.example.com", timeout_seconds=10.0) as client:
    receipt = client.send(Notification(recipient="ann@example.com", subject="Your order shipped"))
print(receipt.status)
```

- **Examples are executed, not proofread.** An example nobody runs is wrong within a release or two.
  An example is a file — a docs page includes it, a test imports or runs it — so the linter and the
  type checker cover it like any module, and the output a page shows is the output a run produced,
  never one typed by hand. Inline snippets get the same through `pytest-examples`, which runs each
  block and compares what it prints with the `#>` comments under it.
- **Start from the caller's goal, not the API surface.** Order examples by frequency of use.
- **Realistic data, no filler.** Never `foo`, `bar`, `test123`. Use reserved example values
  (`example.com`, RFC 5737 addresses) so an example can never hit a real host. Never a real key,
  token, hostname or customer name, not even redacted.

```python
# WRONG — filler that means nothing, and neither bar.com nor 1.2.3.4 is reserved for examples
user = User(name="foo", email="test123@bar.com", ip_address="1.2.3.4")

# CORRECT — plausible values from the reserved ranges: example.com and RFC 5737's 192.0.2.0/24
user = User(name="Ann Lee", email="ann@example.com", ip_address="192.0.2.10")
```

- **Deterministic output.** Anything time-, id- or order-dependent is pinned: inject a fixed clock,
  use a literal UUID, sort before printing.

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

- **Show the outcome, not the plumbing.** Print or assert the one value that proves the point.
- **Examples follow every rule in these files.** Copy-paste is how examples are consumed: an
  example with a bare `except` teaches a bare `except` to every reader.
- **Never demonstrate an anti-pattern without marking it** `# WRONG` next to a `# CORRECT`.
- **The happy path is the example; failures get their own** — one per error scenario a caller must
  handle.
- **Keep examples versioned with the API.** A deprecated path disappears from examples in the same
  release it is deprecated in.

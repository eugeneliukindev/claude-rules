---
name: python-boundaries
description: >-
  Python process boundaries: validating models at the edge versus frozen domain objects inside,
  mandatory timeouts, what may and may not be retried, idempotency keys, operations that promise a
  state so a repeat succeeds, nested retry budgets, explicit serialization and payload versioning,
  atomic file writes and explicit encodings, and the handling of time, money and identifiers. Use
  when Python code talks to HTTP, a queue, a cache, a database or a file, writes a file another
  process reads, or works with datetimes, Decimal money, UUIDs or any value crossing the process
  boundary.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Boundaries

Time, money and identifiers cross every boundary, so their representation is here too.

## Boundary Validation and Domain Models

Two model families, two jobs. Do not mix them.

- **Validating models live at process boundaries only**: request and response shapes, message
  payloads, settings, rows from untrusted sources. Their job is parsing and validating external
  data, and they are the only place that job happens.
- **Frozen dataclasses and value objects live inside**: domain entities and everything between
  layers. Domain code never imports the validation library.
- **Validate once, at the edge.** The boundary parses, converts to a domain object, and passes that
  inward. Services and storage never re-validate; re-validation deeper in the stack means the
  boundary leaked.
- **Boundary models are strict**: no silent coercion of `"1"` to `1`, no unknown fields quietly
  dropped. Whatever the library calls it, turn it on.
- **Explicit mapping between the families**: a `to_domain()` / `from_domain()` pair, or a mapper
  module. Never construct one family by splatting the other's fields — a field rename then breaks
  it silently, and nothing fails until production.

```python
# WRONG — the splat is typed Any: a field renamed on either side passes mypy and fails at runtime
def to_domain(self) -> Order:
    return Order(**self.model_dump())

# CORRECT — every field named once, so a rename on either side fails the type check here
def to_domain(self) -> Order:
    return Order(order_id=OrderId(self.order_id), placed_at=self.placed_at, total=self.total)
```

- **Validating a bare collection reuses one adapter instance**; constructing the validator is the
  expensive part.
- **Output shapes are explicit too**: the boundary returns a response model built from the domain
  object, never a domain or ORM object serialized by accident. Over-exposure of fields is a
  security bug, not a formatting one.

## External Calls: Timeouts, Retries, Idempotency

Every call that leaves the process — HTTP, database, queue, cache, DNS — follows the same
discipline:

- **A timeout is mandatory and explicit.** Client-level defaults set once in the composition root,
  overridden per call only with a named constant. A call with no timeout turns a dependency's
  outage into your own.

```python
# WRONG — no timeout: a server that accepts the connection and never answers holds the worker
with smtplib.SMTP(smtp_host, smtp_port) as smtp:
    smtp.send_message(message)

# CORRECT — the connection and every read on it give up at a named deadline
with smtplib.SMTP(smtp_host, smtp_port, timeout=_SMTP_TIMEOUT_SECONDS) as smtp:
    smtp.send_message(message)
```

- **Retry only transient failures**: connect and read timeouts, rate limits, server errors,
  broker disconnects. **Never retry** business rejections, validation errors or auth failures —
  retrying a conflict is a loop, not resilience. A cache read is not retried even when the failure
  is transient: the source is its fallback (`python-caching`).
- **The adapter translates upstream errors into a transient and a permanent error type first**;
  the retry policy then keys on the type, not on status-code checks scattered around. A pool that
  let the event loop's own timeout escape untranslated broke every caller that caught the
  library's timeout error — the one it documented.

```python
# WRONG — one error type for every status, so the retry policy retries a 409 like a 503
def _raise_for_status(status_code: int, order_id: OrderId) -> None:
    if status_code >= HTTPStatus.BAD_REQUEST:
        raise UpstreamError(f"Order {order_id}: upstream answered {status_code}")

# CORRECT — classified once, here; the retry policy keys on TransientUpstreamError alone
_TRANSIENT_STATUSES: Final = frozenset(
    {
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.BAD_GATEWAY,
        HTTPStatus.SERVICE_UNAVAILABLE,
        HTTPStatus.GATEWAY_TIMEOUT,
    }
)

def _raise_for_status(status_code: int, order_id: OrderId) -> None:
    if status_code in _TRANSIENT_STATUSES:
        raise TransientUpstreamError(f"Order {order_id}: upstream answered {status_code}")
    if status_code >= HTTPStatus.BAD_REQUEST:
        raise PermanentUpstreamError(f"Order {order_id}: upstream answered {status_code}")
```

- **Retries are bounded, exponential, and jittered**, with the jitter set in proportion to the
  backoff rather than left at a library default — the numbers are in `python-tenacity`.
- **Retry a write only if it is idempotent.** Carry an idempotency key when the API supports one;
  otherwise make the operation idempotent on your side, or do not retry it. The key belongs to the
  operation, minted before the first attempt — a client that times out after the server committed
  and retries with a fresh key charges the customer twice:

```python
# WRONG — every attempt mints a new key, so the server sees three different charges
@_RETRY_TRANSIENT
async def _charge(gateway: PaymentGateway, payment: Payment) -> Receipt:
    return await gateway.charge(payment.amount, idempotency_key=str(uuid.uuid4()))

# CORRECT — the payment's own id, minted when the payment was created, is the key
@_RETRY_TRANSIENT
async def _charge(gateway: PaymentGateway, payment: Payment) -> Receipt:
    return await gateway.charge(payment.amount, idempotency_key=str(payment.payment_id))
```

- **Consumers are idempotent**: at-least-once delivery means every handler must tolerate the same
  message twice. The id that makes it so is the event's own, carried in the payload — never the
  broker's; how a consumer achieves it is in `python-workers`.

```python
# WRONG — a redelivered message credits the account a second time
def credit_payment(unit_of_work: UnitOfWork, message: PaymentReceived) -> None:
    with unit_of_work:
        unit_of_work.accounts.credit(message.account_id, message.amount)

# CORRECT — the event id is recorded in the same transaction, and a repeat is skipped
def credit_payment(unit_of_work: UnitOfWork, message: PaymentReceived) -> None:
    with unit_of_work:
        if unit_of_work.processed_events.contains(message.event_id):
            return
        unit_of_work.accounts.credit(message.account_id, message.amount)
        unit_of_work.processed_events.add(message.event_id)
```

- **An operation promises a state, so a repeat of it succeeds** — "define errors out of
  existence". A retry, a redelivery or a double click calls `cancel` on an order the first call
  already cancelled; an error there turns a success into a failure the caller must special-case. A
  state the call cannot reach is still an error: a shipped order is not cancelled. And never a
  guess in place of an error — a clipped index or an empty result for "not found" is a wrong answer
  that looks right.

```python
# WRONG — a retried cancel fails on the order the first attempt already cancelled
def cancel_order(orders: OrderRepository, order_id: OrderId) -> None:
    order = orders.get(order_id)
    if order.status is OrderStatus.CANCELLED:
        raise OrderAlreadyCancelledError(order_id)
    if order.status is OrderStatus.SHIPPED:
        raise OrderAlreadyShippedError(order_id)
    orders.save(replace(order, status=OrderStatus.CANCELLED))

# CORRECT — "cancelled afterwards" holds after a repeat too; only the unreachable state raises
def cancel_order(orders: OrderRepository, order_id: OrderId) -> None:
    order = orders.get(order_id)
    if order.status is OrderStatus.CANCELLED:
        return
    if order.status is OrderStatus.SHIPPED:
        raise OrderAlreadyShippedError(order_id)
    orders.save(replace(order, status=OrderStatus.CANCELLED))
```

- **Retry at one level: the adapter.** Services see one call that either succeeded or raised a
  final error, and never contain retry loops. Budgets nest multiplicatively — four attempts inside
  a caller that also makes four is sixteen, and a five-second budget becomes eighty — so the
  outermost boundary owns the total deadline. A gRPC channel's service-config `retryPolicy` is
  that one layer for its calls (`python-grpc`).
- **The one retry above the adapter: a deadlock or serialization failure retries the whole unit of
  work** — why, in `python-persistence`. So the repository never retries these; it raises them as
  their own transient type, and only the code that opens the unit of work catches it.
- **Fail fast when the dependency is down.** After repeated failures stop hammering and surface a
  clear unavailability error, so callers degrade deliberately instead of queueing timeouts.

## Serialization

- **Serialization is explicit and lives at the boundary**: a boundary model, or a dedicated
  `to_dict` / `from_dict` on a value object. Never `obj.__dict__`, never `vars(obj)`, never
  serializing a domain or ORM object directly — what a serializer can reach, it will publish.

```python
# WRONG — everything the object holds is published: password_hash today, every new field tomorrow
def to_payload(user: User) -> dict[str, object]:
    return dataclasses.asdict(user)

# CORRECT — the payload names each field it publishes, and nothing else gets out
def to_payload(user: User) -> dict[str, object]:
    return {"user_id": str(user.user_id), "email": user.email}
```

- **Round-trip is a contract**: `from_dict(to_dict(x)) == x`, covered by a test for every
  serialized type.
- **Untrusted data is never unpickled** — it executes code on load. Do not use pickle for
  persistence or cross-service messages at all, being version-fragile; it is acceptable only inside
  a single process tree.
- **Safe loaders only** for untrusted text formats; configuration is read once at startup, not
  used as a database.
- **Versioned payloads**: any shape that crosses a queue or is stored carries an explicit version
  field, and consumers tolerate unknown *added* fields. That tolerance is for stored and queued
  data, achieved by explicit migration on read — requests still reject extras. A cache entry is
  the exception: its version is in its key, and an old entry is fetched again from the source,
  never migrated (`python-caching`).

```python
# WRONG — once the shape changes, a consumer cannot tell an old message from a new one
def to_payload(event: OrderPlaced) -> dict[str, object]:
    return {"order_id": str(event.order_id), "total": str(event.total)}

# CORRECT — the shape names its version, so a consumer can migrate an old one on read
def to_payload(event: OrderPlaced) -> dict[str, object]:
    return {
        "version": _ORDER_PLACED_VERSION,
        "order_id": str(event.order_id),
        "total": str(event.total),
    }
```

- **Binary formats follow the same rules**: explicit schema, explicit version, adapters at the
  edge, never in domain code. The protobuf and gRPC mechanics — a gRPC call has no deadline
  until one is passed — are `python-grpc`.

## Files

A file is a boundary too: another process reads it, possibly while it is being written, possibly
on a machine with another locale.

- **`pathlib` by default; `os` where `pathlib` has no answer**, and only there: permission probing
  (`os.access`), process state (`os.getcwd`, `os.environ`), raw file descriptors, `os.replace`
  below. There is no `Path.can_write()`, and the linter that rewrites `os.path` into `Path` says
  nothing about these.

- **A file someone else reads is replaced, never rewritten in place.** Write a temporary file in
  the same directory, flush it to disk, and `os.replace` it over the target: a reader sees the old
  file or the new one, never half of either. The same directory matters — a rename is atomic only
  within one filesystem.

```python
# WRONG — a crash or a full disk mid-write leaves a truncated file where a whole one stood
def write_report(path: Path, payload: bytes) -> None:
    path.write_bytes(payload)

# CORRECT — written beside the target, flushed to disk, then renamed over it in one step
def write_report(path: Path, payload: bytes) -> None:
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", delete_on_close=False
    ) as temporary:
        temporary.write(payload)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary.close()
        os.replace(temporary.name, path)
```

  `delete_on_close=False` (3.12+) keeps the file through `close()` and still removes it when
  anything fails before the rename.
- **Text names its encoding**: `open(path, encoding="utf-8")`, `path.read_text(encoding="utf-8")`,
  `subprocess.run(..., encoding="utf-8")`. Without it Python uses the locale's encoding — UTF-8 on
  the machine that wrote the code, cp1252 on a Windows host — and the same file reads differently.
  CSV files are opened with `newline=""` as well, or quoted line breaks are mangled.

```python
# WRONG — the locale picks the encoding, and a \r\n inside a quoted field comes back as \n
with path.open() as file:
    rows = list(csv.DictReader(file))

# CORRECT — the encoding is named, and csv reads the line endings as the file has them
with path.open(encoding="utf-8", newline="") as file:
    rows = list(csv.DictReader(file))
```

## Time

- **Datetimes are always timezone-aware UTC**: `datetime.now(UTC)` — never `datetime.now()` /
  `datetime.utcnow()`, which are naive, and the second is deprecated. Convert to local time only at
  the presentation edge, with `zoneinfo.ZoneInfo`, never a hand-written offset.

```python
# WRONG — naive host-local time: shifts with the server's zone, cannot be ordered against aware
def _system_clock() -> datetime:
    return datetime.now()

# CORRECT — aware UTC; this is the clock the composition root injects
def _system_clock() -> datetime:
    return datetime.now(UTC)
```

- Naive datetimes are rejected at the boundary: a schema accepting a datetime requires an offset.
  A driver may not reject one: asyncpg writes a naive `datetime` into `timestamptz` as the client
  machine's local time (`python-asyncpg`).

```python
# WRONG — accepts "2026-03-01T09:00:00", an instant in no zone at all
placed_at: datetime

# CORRECT — pydantic rejects a value without an offset
placed_at: AwareDatetime
```

- **Store and serialize as ISO-8601** (`.isoformat()` / `datetime.fromisoformat`); epoch numbers
  only for machine-to-machine metrics.
- **Never compare or mix naive and aware**; never do date arithmetic across DST with a plain
  `timedelta` on local times — do it in UTC.

```python
# WRONG — wall-clock arithmetic: on the night the clocks change, the token lives 23 hours or 25
expires_at = issued_at.astimezone(user_zone) + _TOKEN_LIFETIME

# CORRECT — elapsed time is added in UTC; the user's zone is for display
expires_at = issued_at.astimezone(UTC) + _TOKEN_LIFETIME
```

- **`date` for calendar concepts, `datetime` for instants** — a birthday is a `date`, and storing
  it as midnight `datetime` invents a timezone bug.
- **Time is a dependency.** Any code that needs "now" takes a clock (`now: Callable[[], datetime]`
  or a tiny `Clock` protocol) injected from the composition root; `datetime.now(UTC)` appears only
  in the default wiring, and tests use a fixed clock.

```python
# WRONG — "now" is read inside, so no test can say when it is
def issue_invitation(email: str) -> Invitation:
    return Invitation(email=email, expires_at=datetime.now(UTC) + _INVITATION_LIFETIME)

# CORRECT — the clock is a parameter: the system clock in production, a fixed one in tests
def issue_invitation(now: Callable[[], datetime], email: str) -> Invitation:
    return Invitation(email=email, expires_at=now() + _INVITATION_LIFETIME)
```

- **Durations are `timedelta`**, and a duration or a size stored as a number is an integer of an
  explicit unit — never a float of ambiguous unit.

## Money

- **Money is `Decimal`, never `float`.** Construct from `str` or `int`; quantize explicitly at
  boundaries (`amount.quantize(Decimal("0.01"), ROUND_HALF_EVEN)`); wrap in a `Money` value object
  with currency, so amounts in different currencies cannot be added.

```python
# WRONG — built from a float, so it inherits the float's error: 19.98999999999999843...
price = Decimal(19.99)
# CORRECT — built from the string the amount was written as
price = Decimal("19.99")
```

## Identifiers

- **`uuid.uuid4()` for opaque ids**; `uuid.uuid7()` (stdlib since 3.14) when ids must sort by
  creation time for index locality. **Never** auto-increment integers exposed publicly, which
  invites enumeration, and never `random`-derived ids. Wrap ids in `NewType`. An opaque id makes
  guessing harder; it does not replace the check that the caller owns the resource (`python-auth`).

```python
# WRONG — sequential and public: whoever holds invoice 1042 can ask for 1041
InvoiceId = NewType("InvoiceId", int)

# CORRECT — random and opaque: one invoice id says nothing about any other
InvoiceId = NewType("InvoiceId", UUID)
invoice_id = InvoiceId(uuid.uuid4())
```

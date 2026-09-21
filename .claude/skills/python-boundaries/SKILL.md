---
name: python-boundaries
description: >-
  Python process boundaries: validating models at the edge versus frozen domain objects inside,
  mandatory timeouts, what may and may not be retried, idempotency keys, nested retry budgets,
  explicit serialization and payload versioning, and the handling of time, money and identifiers.
  Use when Python code talks to HTTP, a queue, a cache, a database or a file someone else wrote,
  or when working with datetimes, Decimal money, UUIDs or any value crossing the process boundary.
---

# Boundaries

Time, money and identifiers are boundary concerns wherever they appear, so they are here too.

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
- **Retry only transient failures**: connect and read timeouts, rate limits, server errors,
  deadlocks, broker disconnects. **Never retry** business rejections, validation errors or auth
  failures — retrying a conflict is a loop, not resilience.
- **The adapter translates upstream errors into a transient and a permanent error type first**;
  the retry policy then keys on the type, not on status-code checks scattered around.
- **Retries are bounded, exponential, and jittered.** Set the jitter explicitly rather than
  trusting a library default — a default measured in seconds can dwarf a backoff measured in
  milliseconds and silently flatten the curve.
- **Retry a write only if it is idempotent.** Carry an idempotency key when the API supports one;
  otherwise make the operation idempotent on your side, or do not retry it.
- **Consumers are idempotent**: at-least-once delivery means every handler must tolerate the same
  message twice.
- **Budgets nest.** An operation retried inside a caller that also retries multiplies — four
  attempts inside four is sixteen. The outermost boundary owns the total deadline; when in doubt,
  retry at one layer only, the adapter.
- **Fail fast when the dependency is down.** After repeated failures stop hammering and surface a
  clear unavailability error, so callers degrade deliberately instead of queueing timeouts.
- **Retrying is an adapter concern.** Services see one call that either succeeded or raised a final
  error; they never contain retry loops.

## Serialization

- **Serialization is explicit and lives at the boundary**: a boundary model, or a dedicated
  `to_dict` / `from_dict` on a value object. Never `obj.__dict__`, never `vars(obj)`, never
  serializing a domain or ORM object directly — what a serializer can reach, it will publish.
- **Round-trip is a contract**: `from_dict(to_dict(x)) == x`, covered by a test for every
  serialized type.
- **NEVER unpickle untrusted data** — it executes code on load. Do not use pickle for persistence
  or cross-service messages at all, being version-fragile; it is acceptable only inside a single
  process tree.
- **Safe loaders only** for untrusted text formats; configuration is read once at startup, not
  used as a database.
- **Versioned payloads**: any shape that crosses a queue or is stored carries an explicit version
  field, and consumers tolerate unknown *added* fields. That tolerance is for stored and queued
  data, achieved by explicit migration on read — requests still reject extras.
- **Binary formats follow the same rules**: explicit schema, explicit version, adapters at the
  edge, never in domain code.

## Time, Money, and Identifiers

- **Datetimes are always timezone-aware UTC**: `datetime.now(UTC)` — never `datetime.now()` /
  `datetime.utcnow()`, which are naive, and the second is deprecated. Convert to local time only at
  the presentation edge, with `zoneinfo.ZoneInfo`, never a hand-written offset.
- Naive datetimes are rejected at the boundary: a schema accepting a datetime requires an offset.
- **Store and serialize as ISO-8601** (`.isoformat()` / `datetime.fromisoformat`); epoch numbers
  only for machine-to-machine metrics.
- **Never compare or mix naive and aware**; never do date arithmetic across DST with a plain
  `timedelta` on local times — do it in UTC.
- **`date` for calendar concepts, `datetime` for instants** — a birthday is a `date`, and storing
  it as midnight `datetime` invents a timezone bug.
- **Time is a dependency.** Any code that needs "now" takes a clock (`now: Callable[[], datetime]`
  or a tiny `Clock` protocol) injected from the composition root; `datetime.now(UTC)` appears only
  in the default wiring, and tests use a fixed clock.
- **Money is `Decimal`, never `float`.** Construct from `str` or `int` — `Decimal("19.99")`, since
  `Decimal(19.99)` inherits float error; quantize explicitly at boundaries
  (`amount.quantize(Decimal("0.01"), ROUND_HALF_EVEN)`); wrap in a `Money` value object with
  currency, so amounts in different currencies cannot be added.
- **Durations and sizes are `timedelta` and integers of an explicit unit**, never floats of
  ambiguous unit.
- **Identifiers**: `uuid.uuid4()` for opaque ids; UUIDv7 (or ULID) when ids must sort by creation
  time for index locality; **never** auto-increment integers exposed publicly, which invites
  enumeration, and never `random`-derived ids. Wrap ids in `NewType`.

---
name: python-boundaries
description: >-
  Designs what crosses a process boundary: validation at the edge, timeouts, retries, idempotency,
  serialization, files other processes read, time, money, identifiers. ALWAYS invoke this skill when
  code calls HTTP, a queue, a cache or a database, writes a file or payload another process reads,
  or handles datetimes, Decimal amounts or UUIDs. Do not write boundary code directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Boundaries

This is the design, whatever library carries it; take a library's own API and traps from its current documentation.

## Boundary Models and Domain Objects

- **Parse external data only in a validating model at the process boundary, and use frozen dataclasses inside.** A request or response, a message payload, settings or a row from an untrusted source is parsed there once and passed inward as a domain object; domain code never imports the validation library, and a check repeated in a service means the boundary leaked.
- **Make boundary models strict.** Never coerce `"1"` to `1`, and never drop an unknown field.
- **Validate a bare collection through one adapter built once.** Constructing the validator is the cost.
- **Map the two families field by field, never by splat.** A splat is typed `Any`, so a field renamed on either side passes the type check and fails in production.
- **Write a plain copy as a method on the schema, and a mapping with rules as a function beside it in the same boundary module.** Once the view hides a field by permission, converts a currency or computes a total, a schema that maps itself answers to two actors.
- **Name every field that leaves the process.** A serializer publishes what it can reach, a password hash today and every field added tomorrow; build the output from the domain object field by field, and never serialize a domain or ORM object, `__dict__` or `vars()`.

## External Calls

- **Give every call that leaves the process an explicit timeout.** HTTP, a database, a queue, a cache or DNS without one turns a dependency's outage into yours, since a server that accepts and never answers holds the worker forever.
- **Set client defaults once where the client is built, and override them in a call only with a named constant.**
- **Retry only a transient failure, and let the adapter classify it.** A timeout, a rate limit, a 5xx or a broker disconnect passes with time, and a business rejection, a validation error or an auth failure does not; never retry a cache read, since the source is its fallback.
- **Translate upstream errors in the adapter into a transient and a permanent type (`errors.md`), and key the retry policy on the type.** An error left untranslated breaks every caller catching the documented one.
- **Bound the retry policy, jitter its backoff, and name its numbers in the adapter.**
- **Retry at one level, the adapter, and let the outermost boundary own the deadline.** Budgets multiply: four attempts under a caller making four is sixteen. A client's built-in retry policy is that level; a deadlock or serialization failure is retried above the adapter, by rerunning the transaction.
- **Stop calling a dependency that keeps failing, and raise an unavailability error from the adapter.** Callers then degrade instead of queueing timeouts.
- **Retry a write only with an idempotency key the operation minted before its first attempt.** A client that times out after the server committed and retries with a fresh key charges twice; where the API takes no key, make the operation idempotent on your side, or do not retry it.

## Serialization

- **Make every serialized type round-trip, and test that it does.** A field that goes out as a string and parses back as something else, a `Decimal` through a float or an aware datetime through a naive one, corrupts data without an error.
- **Refuse `NaN` and `Infinity` where a payload arrives.** They are not JSON, yet `json.loads` turns them into floats and a validator's `float` may accept them even in strict mode; one bad number poisons every sum it joins.
- **Put a version in every shape that is queued or stored.** Once the shape changes, a consumer cannot tell an old message from a new one; a cache entry carries its version in its key instead, and an old entry is fetched again from the source, never migrated.
- **Make consumers of stored and queued data tolerate unknown added fields and migrate an old version on read, and keep a request rejecting extras.**
- **Give a binary format the same rules: an explicit schema, an explicit version, adapters at the edge.**

## Files

- **Replace a file someone else reads, never rewrite it in place.** A crash or a full disk mid-write leaves a truncated file; write a temporary file in the same directory, flush it to disk, and move it over the target with `os.replace`.
- **Keep the temporary file in the target's directory.** A rename is atomic only within one filesystem; `delete_on_close=False` (3.12) keeps the file through `close()` and still removes it when anything fails before the rename.

## Time

- **Keep every datetime aware and in UTC, and refuse one without an offset at the boundary.** A naive `datetime.now()` or `utcnow()` shifts with the server's zone and cannot be ordered against an aware value, and a timestamp with no offset is an instant in no zone.
- **Store a datetime as ISO-8601, keep epoch numbers for metrics, and convert to local time only for display, through `zoneinfo.ZoneInfo`.** Never write an offset by hand.
- **Call `datetime.now(UTC)` only in the system clock, and ask an injected `Clock` everywhere else (`testing.md`).**
- **Add elapsed time in UTC, and never compare or mix naive and aware values.** Wall-clock arithmetic on local times is wrong on the nights the clocks change.
- **Keep a calendar day a `date`.** Stored as a midnight `datetime`, it invents a timezone bug.
- **Measure a deadline or an elapsed time on the monotonic clock.** NTP and operators step the wall clock, stretching or cutting a wait; use `time.monotonic()`, or `loop.time()` in async code, and keep `datetime` for instants a person or a record reads.
- **Keep a duration a `timedelta`, and store one as an integer of an explicit unit, never a float of ambiguous unit.**

## Money

- **Build money as a `Decimal` from text, never from a float.** A `float` cannot hold `19.99`, and a `Decimal` built from one inherits the error.
- **Send money on the wire as a string.** The reader's JSON parser turns `19.90` into `19.9`; the string carries the exact digits the consumer builds its `Decimal` from.
- **Quantize amounts explicitly at the boundary, and wrap each with its currency in a value object.** Euros and kroner then cannot be added.

## Identifiers

- **Make a public identifier random and opaque, and wrap it in its own `NewType` (`naming.md`).** A sequential id invites enumeration, and a `random`-derived one is predictable; use `uuid.uuid4()`, or `uuid.uuid7()` (stdlib from 3.14) when ids must sort by creation time for index locality.
- **Check that the caller owns the resource, whatever the id.** An opaque id makes guessing harder and never replaces that check.

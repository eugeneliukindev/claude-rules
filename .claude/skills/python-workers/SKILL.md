---
name: python-workers
description: >-
  Designs queue consumers and background jobs whatever the broker: idempotent handlers, acking
  after commit, dead letters, one retry layer, versioned payloads, nested deadlines, shutdown,
  ordering. Use when writing or reviewing a consumer, a task or a background job, or deciding how
  a message is acked, retried or dead-lettered.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Workers and Queue Consumers

Consumer design, whatever the broker. The examples are plain functions over the application's own
contracts; the broker library is only what calls them — FastStream on RabbitMQ is
`python-faststream`, and Celery 5.6, taskiq 0.13, aiokafka 0.14 and arq 0.28 are mapped in
[libraries.md](libraries.md). The rules a consumer shares with every adapter — idempotent
consumers, one retry level, versioned payloads — are in `python-boundaries`; this file is what a
worker adds. The adapter's retry policy is `python-tenacity`, and the wire model's
strict, versioned JSON parsing in pydantic is `python-pydantic`.

## The Handler

### A handler is a plain function over the raw body and the dependencies it is handed

**Why:** every library wraps the handler in its own decorator and reads one thing back: did it
return or raise — returning means done, raising means failed, and "requeue" or "reject" stay in
the library's wrapper. A plain function validates the payload, bounds the work and calls the use
case, so every rule below is testable without a broker and the same on every broker.
`RoomInventory` is the application's contract (`python-contracts`).

**Example:**
```python
# WRONG — the handler is the library's message object and a module-level inventory
@broker.subscriber("bookings.confirmed")
async def on_booking_confirmed(message: RabbitMessage) -> None:
    payload = json.loads(message.body)
    await _INVENTORY.hold(payload["booking_id"], idempotency_key=payload["event_id"])


# CORRECT — the body and the contract in; the library's wrapper only passes them
async def on_booking_confirmed(body: bytes, /, *, inventory: RoomInventory) -> None:
    event = parse_booking_confirmed(body)
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await hold_room(event, inventory=inventory)


async def hold_room(event: BookingConfirmed, *, inventory: RoomInventory) -> None:
    await inventory.hold(event.booking_id, idempotency_key=str(event.event_id))
```

## Delivery Is At Least Once

### A repeat is absorbed by the cheapest mechanism that holds, keyed on the event's own id

**Why:** every handler will one day run twice — a worker killed before its ack, a relay that
republishes after a timeout, a dead-letter queue replayed by hand. An absolute write — set the
status, an upsert on a natural key — is idempotent already; a relative write — credit, decrement,
send — records the processed event's id in the same transaction; a call out of the process carries
the id as the downstream idempotency key. The key is minted with the event, in the outbox row,
never the broker's message id, delivery tag or offset: a republished copy gets a new one, and a
library may invent one per delivery. Processed ids are kept as long as a
message can come back — the dead-letter queue's retention, not the redelivery window.

**Example:**
```python
# WRONG — the delivery's id: the republished copy arrives under a new one and is held again
async def hold_room(
    event: BookingConfirmed, *, delivery_id: str, inventory: RoomInventory
) -> None:
    await inventory.hold(event.booking_id, idempotency_key=delivery_id)


# CORRECT — the event's id, minted with the event and carried in the payload
async def hold_room(event: BookingConfirmed, *, inventory: RoomInventory) -> None:
    await inventory.hold(event.booking_id, idempotency_key=str(event.event_id))
```

### The handler returns only once its work has committed

**Why:** an acknowledgement tells the broker to forget the message. Given before the transaction
commits, a crash in between loses it; given after, the crash costs one redelivery, which
idempotency absorbs. So the transaction commits inside the handler, and nothing is handed to a task
it does not await. Every library also has a mode that acknowledges on receipt — Celery's default,
aiokafka's auto-commit, FastStream's `ACK_FIRST` — and each is switched to acknowledge when the
handler returns ([libraries.md](libraries.md)).

**Example:**
```python
# WRONG — returns before the room is held: the ack follows, and a crash loses the booking
async def on_booking_confirmed(
    body: bytes, /, *, inventory: RoomInventory, tasks: asyncio.TaskGroup
) -> None:
    event = parse_booking_confirmed(body)
    tasks.create_task(hold_room(event, inventory=inventory))


# CORRECT — returns once the room is held, so the ack that follows is true
async def on_booking_confirmed(body: bytes, /, *, inventory: RoomInventory) -> None:
    event = parse_booking_confirmed(body)
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await hold_room(event, inventory=inventory)
```

## Failure

### A failure escapes the handler, and a message that keeps failing ends in a dead-letter queue

**Why:** caught and logged, an error becomes a return, and a return is an acknowledgement — the
message is gone. A failing message gets a bounded number of attempts, then a dead-letter queue
whose depth is a metric with an alert (`python-observability`). Two bounds are needed because a
crash raises nothing: the library reports a raised error, and only the broker's delivery limit
catches a worker killed mid-handler. A payload that fails validation is dead-lettered on its first
delivery. Where the library has no dead-letter queue — Celery, taskiq, arq — the handler records
the failure before the error escapes; on Kafka the consumer publishes the record to a dead-letter
topic and commits, since a partition retrying one record blocks every record behind it.

**Example:**
```python
# WRONG — the error is logged and swallowed: the handler returns, and the ack drops the booking
async def on_booking_confirmed(body: bytes, /, *, inventory: RoomInventory) -> None:
    event = parse_booking_confirmed(body)
    try:
        async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
            await hold_room(event, inventory=inventory)
    except InventoryError:
        logger.exception("room hold failed", extra={"booking_id": str(event.booking_id)})


# CORRECT — the error escapes: a failed delivery, counted toward the dead-letter queue
async def on_booking_confirmed(body: bytes, /, *, inventory: RoomInventory) -> None:
    event = parse_booking_confirmed(body)
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await hold_room(event, inventory=inventory)
```

### Each failure is retried by exactly one layer

**Why:** the broker redelivers and the adapter's retry policy retries; together they multiply
— three attempts in the adapter under a delivery limit of five is fifteen calls to a dependency
that is already struggling (`python-boundaries`). A redelivery comes at once, with no backoff, so a
retry with backoff that fits inside the handler's deadline lives in the adapter,
and the final error escapes to the dead-letter queue. A wait longer than the
deadline is the broker's — Celery's `self.retry(countdown=...)`, taskiq's `SmartRetryMiddleware`,
a delayed retry queue — and the adapter then does not retry. The delivery limit stays either way:
it bounds crashes, not exceptions.

**Example:**
```python
# WRONG — the handler retries an adapter that retries, under a broker that redelivers
@_RETRY_TRANSIENT
async def on_booking_confirmed(body: bytes, /, *, inventory: RoomInventory) -> None:
    event = parse_booking_confirmed(body)
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await hold_room(event, inventory=inventory)


# CORRECT — the adapter behind RoomInventory retries inside the deadline; the handler does not
async def on_booking_confirmed(body: bytes, /, *, inventory: RoomInventory) -> None:
    event = parse_booking_confirmed(body)
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await hold_room(event, inventory=inventory)
```

## The Payload

### The body is validated as JSON into a strict, versioned wire model

**Why:** a message is a boundary — a wire model validated where it is consumed and converted to a
domain object, never a domain or ORM object and never a pickle (`python-boundaries`); Celery's
`pickle` in `accept_content` lets anyone who can publish run code in the worker. The raw body goes
to the wire model whole, never a dict a library decoded first; a task library
that decodes its arguments itself is handed the JSON text as its one argument. Queued payloads
ignore added fields and pin their version with a `Literal`; a consumer that also knows v2
validates a union discriminated on `version`. A request that enqueues work writes an outbox row in
its own transaction (`python-persistence`), and `BackgroundTasks` are no substitute.

**Example:**
```python
# WRONG — a dict, no version, and any shape accepted
def parse_booking_confirmed(body: bytes) -> BookingConfirmed:
    payload = json.loads(body)
    return BookingConfirmed(
        event_id=EventId(UUID(payload["event_id"])),
        booking_id=BookingId(UUID(payload["booking_id"])),
        confirmed_at=datetime.fromisoformat(payload["confirmed_at"]),
    )


# CORRECT — the wire model of a pinned version parses the whole body in one step
def parse_booking_confirmed(body: bytes) -> BookingConfirmed:
    return BookingConfirmedV1.from_json(body).to_domain()
```

## Deadlines Nest

| broker | where the ack deadline lives | default |
|---|---|---|
| RabbitMQ | `consumer_timeout`, server-side | 30 minutes |
| Kafka (aiokafka) | `max_poll_interval_ms`, for a whole poll's batch | 5 minutes |
| Celery on Redis or SQS | transport `visibility_timeout` | 1 hour, 30 minutes |
| arq | `job_timeout` | 5 minutes |

### The handler's deadline sits inside the broker's ack deadline, and the deliveries held fit too

**Why:** past the ack deadline the broker takes the message back and hands it to another worker
while the first is still running it — two copies at once, which idempotency survives and the
dependency pays for. Every handler has an `asyncio.timeout` where the library has none of its own,
any retry budget fits inside it, and it fits inside the shutdown grace ([shutdown.md](shutdown.md)).
Prefetch — how many messages a worker holds before it acks any — is set, never inherited: each held
message keeps its ack deadline running, so `prefetch × handler deadline` fits inside it, and an
unbounded prefetch pulls the whole queue into one worker while the others idle.

**Example:**
```python
# WRONG — an inventory service that stops answering holds the delivery until the broker takes it
async def on_booking_confirmed(body: bytes, /, *, inventory: RoomInventory) -> None:
    event = parse_booking_confirmed(body)
    await hold_room(event, inventory=inventory)


# CORRECT — the handler gives up at its own deadline, well inside the broker's
async def on_booking_confirmed(body: bytes, /, *, inventory: RoomInventory) -> None:
    event = parse_booking_confirmed(body)
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await hold_room(event, inventory=inventory)
```

## Shutdown

**Before setting a worker's drain timeout, its handler deadline against the orchestrator's grace
period, or its stop path, read [shutdown.md](shutdown.md)** — stop fetching, finish within a bound,
abandon the rest unacknowledged, the numbers that must nest.

## The Worker's Composition Root

**Before writing a worker's `main()`, a Celery or taskiq app object, or a startup or shutdown hook
that builds pools and clients, read [composition-root.md](composition-root.md)** — built once in
the root, nothing at import, hooks per prefork child.

## Ordering

**Before relying on messages arriving in the order they were published, or partitioning by key,
read [ordering.md](ordering.md)** — make the order not matter with a version, or buy it with one
consumer per key.

## Testing

**Before writing a test for a handler, a fake of the contract it calls, or a broker integration
test, read [testing.md](testing.md)** — the handler called with a body and a fake, redelivery as a
second call, one dead-letter test per queue against the real broker.

## Libraries

**Before configuring Celery, taskiq, aiokafka or arq for a consumer, read
[libraries.md](libraries.md)** — the setting that acks after the work, bounds attempts,
dead-letters, sets the deadline and limits deliveries in flight, per library.

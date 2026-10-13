---
name: python-faststream
description: >-
  FastStream on RabbitMQ mechanics behind the consumer design: routers from the root's
  dependencies, AckPolicy, delivery limits and dead letters, message ids, validation mode,
  prefetch, shutdown, tests. Use when code imports faststream, defines a RabbitBroker,
  RabbitRouter, RabbitQueue or subscriber, or runs faststream.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# FastStream

Checked against FastStream 0.7 on RabbitMQ 4.3. The consumer's design — the handler as a plain
function, idempotency, when to acknowledge, dead-lettering, one retry layer, deadlines, shutdown —
is in `python-workers`; this file is how FastStream and RabbitMQ carry it out. Every number marked
measured came from a handler that always raises, on a real broker. `RabbitBroker` lives behind the
`faststream[rabbit]` extra (`aio-pika`), the CLI behind `faststream[cli]`.

## The Subscriber

### Subscribers are registered on a router that a function builds from the root's dependencies

**Why:** the subscriber is FastStream's wrapper around the plain handler: it takes the raw
`RabbitMessage` and passes `message.body` on. A module-level broker with a module-level session
beside it is the global singleton `python-wiring` forbids, and `context.set_global` is a service
locator. `main()` builds the broker, the resources and the router, and owns every lifetime.

**Example:**
```python
# WRONG — importing the module reads the environment and builds the broker and the client
_settings = WorkerSettings()
broker = RabbitBroker(_settings.amqp_url)
inventory = HttpRoomInventory(open_http_client(base_url=_settings.inventory_url))


# CORRECT — the router is built from what main() hands it, and main() owns every lifetime
def build_booking_router(*, inventory: RoomInventory) -> RabbitRouter:
    router = RabbitRouter()

    @router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
    async def on_booking_confirmed_message(message: RabbitMessage) -> None:
        await on_booking_confirmed(message.body, inventory=inventory)

    return router


async def main() -> None:
    settings = WorkerSettings()
    async with managed_inventory_session(settings.inventory_url) as session:
        broker = RabbitBroker(settings.amqp_url, graceful_timeout=_GRACEFUL_TIMEOUT_SECONDS)
        broker.include_router(build_booking_router(inventory=HttpRoomInventory(session)))
        await FastStream(broker).run()
```

### The subscriber takes the raw message and the handler validates its body as JSON

**Why:** an annotated message parameter is validated against the dict FastStream already decoded,
in Python mode, so a strict model rejects every UUID, `Decimal` and datetime in every valid message
— measured: the UUID arrives as a `str`, `is_instance_of` fails, and nothing is handled
(`python-pydantic`). With the raw message, `model_validate_json` runs in JSON mode; a failed
validation escapes, and `REJECT_ON_ERROR` dead-letters the message on its first delivery (measured).

**Example:**
```python
# WRONG — validated in Python mode: the UUID arrives as a str, and every message fails
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: BookingConfirmedV1) -> None:
    await hold_room(message.to_domain(), inventory=inventory)


# CORRECT — the raw body reaches the handler, which validates it in JSON mode
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    await on_booking_confirmed(message.body, inventory=inventory)
```

### `message_id` is never the idempotency key

**Why:** it is whatever the publisher set, and **when the publisher set none, FastStream invents a
fresh one on every delivery** — measured with a message published without one: three deliveries,
three ids. A publisher on aio-pika stamps one per publish, so a relay that republishes still gives
the copy a new one; `correlation_id` behaves the same way. The key is the event's own id, from the
payload (`python-workers`).

**Example:**
```python
# WRONG — a new id on each delivery: every redelivery holds the room again
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    event = BookingConfirmedV1.model_validate_json(message.body).to_domain()
    await inventory.hold(event.booking_id, idempotency_key=message.message_id)


# CORRECT — the event's id, from the body, is the same on every delivery
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    await on_booking_confirmed(message.body, inventory=inventory)
```

## Acknowledgement and Dead Letters

Measured on a quorum queue with `x-delivery-limit` and a dead-letter exchange:

| `AckPolicy` | acked | a message whose handler raises |
|---|---|---|
| `ACK_FIRST` | on receipt | gone; a crash mid-handler loses it too |
| `ACK` | after the handler | acked anyway: gone, nothing dead-lettered |
| `NACK_ON_ERROR` | after the handler | requeued at once, never dead-lettered — over 300 deliveries in three seconds |
| `REJECT_ON_ERROR` (default) | after the handler | rejected once: dead-lettered after one attempt, or dropped without a DLX |

### Every subscriber states `AckPolicy.REJECT_ON_ERROR`

**Why:** it is the default, but a broker or router given another changes it for every subscriber
below, and the dead-letter path depends on it. A cancelled handler — at shutdown — is neither acked
nor rejected, and comes back.

**Example:**
```python
# WRONG — acked on receipt: a worker killed mid-hold loses the booking
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.ACK_FIRST)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    await on_booking_confirmed(message.body, inventory=inventory)


# CORRECT — acked when the handler returns; an error rejects it to the dead-letter exchange
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    await on_booking_confirmed(message.body, inventory=inventory)
```

### The queue carries its delivery limit and its dead-letter exchange

**Why:** without `x-dead-letter-exchange`, `REJECT_ON_ERROR` drops the message; the dead-letter
queue must exist before the first rejection, or the message is dropped too (measured).
`x-delivery-limit` counts deliveries that never got an answer — a worker killed mid-handler, a
delivery abandoned at shutdown — and past it the message is dead-lettered (measured); quorum queues
default to 20 since RabbitMQ 4.0, so the limit is named. A broker policy can carry the same keys
(`delivery-limit`, `dead-letter-exchange`) and is the one to change later: a queue redeclared with
different arguments is refused.

**Example:**
```python
# WRONG — no dead-letter exchange: REJECT_ON_ERROR drops a failing booking without a trace
_BOOKINGS_QUEUE: Final = RabbitQueue(_BOOKINGS_QUEUE_NAME)


# CORRECT — bounded deliveries, and every failure kept where someone can read and replay it
_BOOKINGS_QUEUE: Final = RabbitQueue(
    _BOOKINGS_QUEUE_NAME,
    queue_type=QueueType.QUORUM,
    arguments={
        "x-delivery-limit": _MAX_DELIVERIES,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": _BOOKINGS_DEAD_LETTER_QUEUE_NAME,
    },
)
```

### A failure is not requeued; the client's retry policy is the only retry

**Why:** a requeue is the broker retrying at once, with no backoff, on top of a client that already
retries (`python-workers`). On RabbitMQ 4.3 a requeueing nack does not count toward the delivery
limit and a requeueing reject does (measured): `NACK_ON_ERROR` loops forever even on a quorum
queue, and `RejectMessage(requeue=True)` spends the whole limit at once.

**Example:**
```python
# WRONG — the inventory client already retries; requeueing on top multiplies its attempts
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    try:
        await on_booking_confirmed(message.body, inventory=inventory)
    except InventoryError as error:
        raise RejectMessage(requeue=True) from error


# CORRECT — the client's policy is the only retry; once it is spent the booking is dead-lettered
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    await on_booking_confirmed(message.body, inventory=inventory)
```

## Deadlines and Shutdown

FastStream has no handler timeout of its own — the handler's `asyncio.timeout` is the deadline
(`python-workers`).

### The subscriber sets a prefetch

**Why:** `Channel(prefetch_count=None)` is the default, and FastStream then sends no `basic.qos`
at all (`helpers/channel_manager.py` sets it only when the count is given): RabbitMQ pushes the
queue into the first worker, and every delivery's ack deadline starts running at once.

**Example:**
```python
# WRONG — no prefetch: the whole queue lands in this worker while the others idle
@router.subscriber(_BOOKINGS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    await on_booking_confirmed(message.body, inventory=inventory)


# CORRECT — at most _PREFETCH_COUNT deliveries held at once; the rest wait for a free worker
@router.subscriber(
    _BOOKINGS_QUEUE,
    ack_policy=AckPolicy.REJECT_ON_ERROR,
    channel=Channel(prefetch_count=_PREFETCH_COUNT),
)
async def on_booking_confirmed_message(message: RabbitMessage) -> None:
    await on_booking_confirmed(message.body, inventory=inventory)
```

### `graceful_timeout` is named, and fits inside the orchestrator's grace period

**Why:** `FastStream.run()` handles `SIGTERM` and `SIGINT`, and `graceful_timeout` bounds the wait
for handlers in flight: **15 seconds by default, and `None` is not "wait forever" but no wait at
all** — measured: `stop()` returned at once and the running handler never finished. What is still
running when the drain ends is cancelled and abandoned unacknowledged, and the redelivery counts
toward `x-delivery-limit`: a handler that cannot finish inside the drain is dead-lettered after that
many deploys (measured).

**Example:**
```python
# WRONG — None skips the drain: every deploy abandons every handler in flight
def build_broker(settings: WorkerSettings) -> RabbitBroker:
    return RabbitBroker(settings.amqp_url, graceful_timeout=None)


# CORRECT — named, and inside the 30-second grace period
def build_broker(
    settings: WorkerSettings, *, graceful_timeout_seconds: float = _GRACEFUL_TIMEOUT_SECONDS
) -> RabbitBroker:
    return RabbitBroker(settings.amqp_url, graceful_timeout=graceful_timeout_seconds)
```

## The CLI and the App's Lifespan

**Before running the worker with `faststream run`, writing a `--factory`, a `lifespan`, or an
`on_startup` or `after_startup` hook, read [app-and-cli.md](app-and-cli.md)** — the factory that
builds the app, resources opened in `lifespan`, what each hook is not for.

## Testing

**Before writing a test with `TestRabbitBroker` or against a real RabbitMQ, read
[testing.md](testing.md)** — what the in-memory broker checks and what it cannot, one dead-letter
test per queue on testcontainers.

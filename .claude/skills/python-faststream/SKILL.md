---
name: python-faststream
description: >-
  FastStream on RabbitMQ mechanics behind the consumer design: routers from the root's
  dependencies, AckPolicy, delivery limits and dead letters, message ids, prefetch, graceful
  shutdown, tests. Use when code imports faststream, defines a RabbitBroker, RabbitRouter,
  RabbitQueue or subscriber, or runs faststream. Not for consumer design (python-workers).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# FastStream

Checked against FastStream 0.7 on RabbitMQ 4.3; `AckPolicy` exists since 0.6. The consumer's
design — idempotency, when to acknowledge, one retry layer, deadlines — is `python-workers`. Every
number marked measured came from a handler that always raises, on a real broker. `RabbitBroker`
lives behind the `faststream[rabbit]` extra (`aio-pika`), the CLI behind `faststream[cli]`.

## The Subscriber

### Subscribers are registered on a router that a function builds from the root's dependencies

**Why:** `@broker.subscriber` on a module-level broker needs every collaborator the handler uses at
import too, and `context.set_global` hands them out as a service locator. A function that takes the
collaborators returns a `RabbitRouter`; the subscriber on it takes the `RabbitMessage` and passes
`message.body` to a plain function, which tests call without a broker.

**Example:**
```python
# WRONG — the decorator binds to a module-level broker, the handler to a module-level scheduler
broker = RabbitBroker()


@broker.subscriber(_DOOR_FAULTS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_door_fault_message(message: RabbitMessage) -> None:
    await record_door_fault(message.body, scheduler=_INSPECTION_SCHEDULER)


# CORRECT — the router is built from what the root hands it
def build_telemetry_router(*, scheduler: InspectionScheduler) -> RabbitRouter:
    router = RabbitRouter()

    @router.subscriber(_DOOR_FAULTS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
    async def on_door_fault_message(message: RabbitMessage) -> None:
        await record_door_fault(message.body, scheduler=scheduler)

    return router
```

### A message published without a `message_id` gets a fresh one on every delivery

**Why:** FastStream's publisher sets no `message_id` unless asked, and the subscriber fills a
missing one with a new uuid each time the message arrives — measured: three deliveries, three ids;
`correlation_id` is minted per publish, so a republished copy gets a new one. Neither identifies the
event across deliveries; the key comes from the payload.

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
# WRONG — no dead-letter exchange: REJECT_ON_ERROR drops a failing door fault without a trace
_DOOR_FAULTS_QUEUE: Final = RabbitQueue(_DOOR_FAULTS_QUEUE_NAME)


# CORRECT — bounded deliveries, and every failure kept where someone can read and replay it
_DOOR_FAULTS_QUEUE: Final = RabbitQueue(
    _DOOR_FAULTS_QUEUE_NAME,
    queue_type=QueueType.QUORUM,
    arguments={
        "x-delivery-limit": _MAX_DELIVERIES,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": _DOOR_FAULTS_DEAD_LETTER_QUEUE_NAME,
    },
)
```

### A failure is never requeued from the subscriber

**Why:** a requeue is the broker retrying at once, with no backoff, on top of whatever retries the
adapter already makes. On RabbitMQ 4.3 a requeueing nack does not count toward the delivery limit
and a requeueing reject does (measured): `NACK_ON_ERROR` loops forever even on a quorum queue, and
`RejectMessage(requeue=True)` spends the whole limit at once.

**Example:**
```python
# WRONG — the scheduler's adapter already retries; requeueing on top multiplies its attempts
@router.subscriber(_DOOR_FAULTS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_door_fault_message(message: RabbitMessage) -> None:
    try:
        await record_door_fault(message.body, scheduler=scheduler)
    except InspectionSchedulingError as error:
        raise RejectMessage(requeue=True) from error


# CORRECT — the error escapes; REJECT_ON_ERROR dead-letters the fault once
@router.subscriber(_DOOR_FAULTS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_door_fault_message(message: RabbitMessage) -> None:
    await record_door_fault(message.body, scheduler=scheduler)
```

## Deadlines and Shutdown

FastStream has no handler timeout of its own: the plain function's `asyncio.timeout` is the
deadline.

### The subscriber sets a prefetch

**Why:** `Channel(prefetch_count=None)` is the default, and FastStream then sends no `basic.qos`
at all (`helpers/channel_manager.py` sets it only when the count is given): RabbitMQ pushes the
queue into the first worker, and every delivery's ack deadline starts running at once.

**Example:**
```python
# WRONG — no prefetch: one worker takes the whole queue, and every ack deadline starts now
@router.subscriber(_DOOR_FAULTS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_door_fault_message(message: RabbitMessage) -> None:
    await record_door_fault(message.body, scheduler=scheduler)


# CORRECT — the worker holds at most _DOOR_FAULTS_PREFETCH unacknowledged deliveries
@router.subscriber(
    _DOOR_FAULTS_QUEUE,
    channel=Channel(prefetch_count=_DOOR_FAULTS_PREFETCH),
    ack_policy=AckPolicy.REJECT_ON_ERROR,
)
async def on_door_fault_message(message: RabbitMessage) -> None:
    await record_door_fault(message.body, scheduler=scheduler)
```

### `graceful_timeout` is named, and fits inside the orchestrator's grace period

**Why:** `FastStream.run()` handles `SIGTERM` and `SIGINT`, and the broker's `graceful_timeout`
bounds the wait for handlers in flight: **15 seconds by default, and `None` is not "wait forever"
but no wait at all** — measured: `stop()` returned at once and the running handler never finished.
What is still running when the drain ends is cancelled and abandoned unacknowledged, and the
redelivery counts toward `x-delivery-limit`: a handler that cannot finish inside the drain is
dead-lettered after that many deploys (measured).

## The Entry Point and the App's Lifespan

**Before writing the worker's entry point, `FastStream(broker)`, a `lifespan`, or an `on_startup`
or `after_startup` hook, read [app-and-cli.md](app-and-cli.md)** — the settings read by the entry
point and the app built from them, resources opened in `lifespan`, what each hook is not for.

## Testing

**Before writing a test with `TestRabbitBroker` or against a real RabbitMQ, read
[testing.md](testing.md)** — what the in-memory broker checks and what it cannot, reading a
dead-lettered message back with `get_one`.

## With Other Libraries

**Before publishing a FastStream message from a FastAPI app, read
[fastapi-faststream.md](../python-integrations/fastapi-faststream.md)** — the event written to the
outbox by the service, never published from the route.

**Before typing a FastStream subscriber's message as a pydantic model, read
[faststream-pydantic.md](../python-integrations/faststream-pydantic.md)** — the raw body to the
handler, validated there in JSON mode.

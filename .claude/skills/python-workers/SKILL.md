---
name: python-workers
description: >-
  Queue consumers and background jobs in Python, whatever the broker: the handler as a plain
  function over the application's services, at-least-once delivery and idempotency on the event's
  own id, acknowledging only after the work committed, bounded redelivery ending in a dead-letter
  queue, one retry layer instead of the broker's and tenacity's together, versioned payloads
  validated as JSON, a deadline inside the ack deadline, graceful shutdown inside the grace period,
  ordering, and testing a handler — with Celery, taskiq, aiokafka and arq mapped in a table and
  FastStream's mechanics in python-faststream. Use when designing or reviewing a queue consumer, a
  task or a background job, or deciding how a message is acknowledged, retried or dead-lettered.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Workers and Queue Consumers

Consumer design, whatever the broker. The examples are plain functions over the application's own
contracts; the broker library is only what calls them. How a library carries each rule out is its
own skill — FastStream on RabbitMQ is `python-faststream` — or, for Celery 5.6, taskiq 0.13,
aiokafka 0.14 and arq 0.28, a row in the table at the end. The boundary rules a consumer shares
with every adapter — idempotent consumers, one retry level, versioned payloads — are in
`python-boundaries`; this file is what a worker adds.

## The Handler Is a Plain Function

Every library wraps the handler in its own decorator — a subscriber, a task, a consume loop — and
reads one thing back: did it return or raise. So the handler is a plain function over the raw body
and the dependencies it is handed: it validates the payload, bounds the work with a deadline and
calls the use case. The library's wrapper passes the body in and nothing more, which keeps every
rule below testable without a broker and the same on every broker.

```python
async def on_order_placed(body: bytes, *, warehouse: Warehouse) -> None:
    event = OrderPlacedV1.model_validate_json(body).to_domain()
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await reserve_stock(warehouse, event)


async def reserve_stock(warehouse: Warehouse, event: OrderPlaced) -> None:
    await warehouse.reserve(event.order_id, idempotency_key=str(event.event_id))
```

- **Returning means done, raising means failed** — the two outcomes every library turns into an
  acknowledgement or a failed delivery. "Requeue" and "reject" are a library's vocabulary, and stay
  in its wrapper.
- **`Warehouse` is the application's contract**, an ABC as `python-contracts` describes, with the
  real implementation named for what makes it concrete and a fake in the tests (below).

## Delivery Is At Least Once

Every handler will one day run twice for the same event: a worker killed before its ack, a relay
that republishes after a timeout, a dead-letter queue replayed by hand. That consumers are
idempotent, with its example, is in `python-boundaries`; what a worker decides is how.

- **The cheapest mechanism that holds.** An absolute write — "set the status to shipped", an
  upsert on a natural key — is idempotent already. A relative write — credit, decrement, send — needs
  the processed event's id recorded in the same transaction as the write. A call out of the process
  carries the id as the downstream idempotency key.
- **The key is the event's own id, minted when the event was recorded** — in the outbox row — and
  carried in the payload. Never the broker's message id, delivery tag or offset: a relay that
  republishes gives the copy a new one, and a library may invent a fresh one on every delivery of a
  message published without one (`python-faststream`).

```python
# WRONG — the delivery's id: the republished copy arrives under a new one and is reserved again
await warehouse.reserve(event.order_id, idempotency_key=delivery_id)
# CORRECT — the event's id, minted with the event and carried in the payload
await warehouse.reserve(event.order_id, idempotency_key=str(event.event_id))
```

- **Processed ids are kept as long as a message can come back** — the dead-letter queue's
  retention, not the broker's redelivery window. A replay a week later is a redelivery too.

## Acknowledge After the Work Commits

An acknowledgement — an ack, a committed offset, a deleted job — tells the broker to forget the
message. Given before the transaction commits, a crash in between loses it; given after, the crash
costs one redelivery, which idempotency absorbs. So the handler returns only once its writes are
committed: the unit of work closes inside it, and nothing is handed to a task it does not await.

Every library also has a mode that acknowledges on receipt or before running the handler —
Celery's default, aiokafka's auto-commit, FastStream's `ACK_FIRST` — and each is switched to
acknowledge when the handler returns (the table at the end).

```python
# WRONG — returns before the reservation is made: the ack follows, and a crash loses the order
async def on_order_placed(body: bytes, *, warehouse: Warehouse, tasks: asyncio.TaskGroup) -> None:
    event = OrderPlacedV1.model_validate_json(body).to_domain()
    tasks.create_task(reserve_stock(warehouse, event))

# CORRECT — returns once the reservation is made, so the ack that follows is true
async def on_order_placed(body: bytes, *, warehouse: Warehouse) -> None:
    event = OrderPlacedV1.model_validate_json(body).to_domain()
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await reserve_stock(warehouse, event)
```

## A Poison Message Ends in a Dead-Letter Queue

A message that fails every time must stop being delivered, and must not vanish. It gets a bounded
number of attempts, then lands in a dead-letter queue whose depth is a metric with an alert
(`python-observability`) — a queue nobody watches is a slower way to drop messages.

- **Two bounds, because a crash raises nothing.** A delivery whose handler raised is a failure the
  library reports to the broker, and goes to the dead-letter queue at once or after a few attempts.
  A delivery that never got an answer — a worker killed mid-handler, a delivery abandoned at
  shutdown — is caught only by the broker's own delivery limit.
- **A permanent failure is dead-lettered on its first delivery.** A payload that fails validation
  will fail the same way every time; a retry cannot fix it.
- **The handler lets the error escape.** Caught and logged, it becomes a return, and a return is
  an acknowledgement: the message is gone. A layer that can only log and re-raise does not catch.

```python
# WRONG — the error is logged and swallowed: the handler returns, and the ack drops the order
async def on_order_placed(body: bytes, *, warehouse: Warehouse) -> None:
    event = OrderPlacedV1.model_validate_json(body).to_domain()
    try:
        async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
            await reserve_stock(warehouse, event)
    except WarehouseError:
        logger.exception("stock reservation failed", extra={"order_id": str(event.order_id)})

# CORRECT — the error escapes: a failed delivery, counted toward the dead-letter queue
async def on_order_placed(body: bytes, *, warehouse: Warehouse) -> None:
    event = OrderPlacedV1.model_validate_json(body).to_domain()
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await reserve_stock(warehouse, event)
```

- **Where the library has no dead-letter queue, the handler records the failure** — a
  failed-message table or topic — before the error escapes; Celery, taskiq and arq ack a failed
  task. **Kafka has none either**: the consumer publishes the failed record to a dead-letter topic
  and then commits, since a partition left retrying one record blocks every record behind it.

## One Layer Retries

How budgets nest is in `python-boundaries`. A worker has two candidates for the retry — the broker,
by redelivering or republishing with a delay, and the adapter's `tenacity` policy — and **each
failure is retried by exactly one of them**. Both together multiply: three attempts in the adapter
under a delivery limit of five is fifteen calls to a dependency that is already struggling.

- **A redelivery comes at once, with no backoff** — a requeued RabbitMQ message is back in the
  handler within milliseconds. A retry with backoff that fits inside the handler's deadline lives in the adapter
  (`python-tenacity`), and the handler lets the final error escape to the dead-letter queue.
- **A wait longer than the handler's deadline is the broker's**: Celery's
  `self.retry(countdown=...)`, taskiq's `SmartRetryMiddleware`, a delayed retry queue. The adapter
  then does not retry at all.
- **The delivery limit stays either way** — it bounds crashes, not exceptions.

## The Payload Is a Versioned Wire Model

A message is a boundary: a wire model with a version, validated where it is consumed and converted
to a domain object, never a domain or ORM object and never a pickle (`python-boundaries`). Celery's
serializer is `json` by default; adding `pickle` to `accept_content` lets anyone who can publish
run code in the worker.

- **Validate the raw body as JSON with a strict model** — `model_validate_json`, never a dict a
  library decoded first (why: `python-pydantic`). A task library that decodes its arguments itself
  is handed the JSON text as its one argument.
- **Queued payloads ignore added fields** — the carve-out `python-boundaries` makes for stored and
  queued data — and pin their version with a `Literal`; a consumer that also knows v2 validates a
  union discriminated on `version`.

```python
@final
class OrderPlacedV1(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", frozen=True)

    version: Literal[1]
    event_id: UUID
    order_id: UUID
    placed_at: AwareDatetime

    def to_domain(self) -> OrderPlaced:
        return OrderPlaced(
            event_id=EventId(self.event_id),
            order_id=OrderId(self.order_id),
            placed_at=self.placed_at,
        )
```

**A request that enqueues work writes an outbox row in its own transaction** and a relay publishes
it — the rule is `python-persistence`'s, and `BackgroundTasks` are no substitute
(`python-fastapi`). The relay publishes at least once, which is the second reason the key above is
the event's id.

## Deadlines Nest

Three numbers, each inside the next, all named constants:

- **Every handler has a deadline** — `asyncio.timeout` around the use case where the library has
  none of its own (`python-async`); any retry budget inside it fits within it.
- **The deadline is shorter than the broker's ack deadline.** Past that, the broker takes the
  message back and hands it to another worker while the first is still running it — two copies at
  once, which idempotency survives and the dependency pays for.
- **The deadline fits inside the shutdown grace** (below), or every deploy abandons the work in
  flight.

| broker | where the ack deadline lives | default |
|---|---|---|
| RabbitMQ | `consumer_timeout`, server-side | 30 minutes |
| Kafka (aiokafka) | `max_poll_interval_ms`, for a whole poll's batch | 5 minutes |
| Celery on Redis or SQS | transport `visibility_timeout` | 1 hour, 30 minutes |
| arq | `job_timeout` | 5 minutes |

```python
# WRONG — a warehouse that stops answering holds the delivery until the broker takes it back
async def on_order_placed(body: bytes, *, warehouse: Warehouse) -> None:
    event = OrderPlacedV1.model_validate_json(body).to_domain()
    await reserve_stock(warehouse, event)
# CORRECT — the handler gives up at its own deadline, well inside the broker's
async def on_order_placed(body: bytes, *, warehouse: Warehouse) -> None:
    event = OrderPlacedV1.model_validate_json(body).to_domain()
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await reserve_stock(warehouse, event)
```

## Graceful Shutdown

On `SIGTERM` a worker stops fetching, lets the handlers in flight finish within a bound, abandons
the rest unacknowledged — the broker redelivers them, and a delivery limit counts each one — and
then closes its resources. The general shape is `python-async`'s; the worker's part is the numbers.

- **The library's drain timeout is set explicitly**, never left at a default whose meaning is a
  library fact — FastStream's is in `python-faststream`.
- **The drain fits inside the orchestrator's grace period** — Kubernetes sends `SIGKILL` 30
  seconds after `SIGTERM` by default — with room left to close the pools. A Celery warm shutdown
  waits for running tasks without a limit, so the orchestrator decides for it.

```python
# WRONG — the orchestrator kills the worker at 30 seconds, mid-drain, and nothing is closed
_HANDLER_DEADLINE_SECONDS: Final = 20.0
_GRACEFUL_TIMEOUT_SECONDS: Final = 60.0

# CORRECT — handlers finish inside the drain, and the drain inside the 30-second grace period
_HANDLER_DEADLINE_SECONDS: Final = 20.0
_GRACEFUL_TIMEOUT_SECONDS: Final = 25.0
```

## The Worker's Composition Root

Build settings, pools and clients once in `main()`, pass them down and close them in reverse;
nothing connects at import time (why: `python-wiring`). The handler receives its dependencies as
parameters, and the library's wrapper is registered by a function that main() hands them to —
FastStream's shape is in `python-faststream`.

- **Celery and taskiq decorate tasks with a module-level app object.** It is a declaration and may
  stay one, as long as it opens nothing; pools and clients are built in the worker's startup hook —
  `TaskiqEvents.WORKER_STARTUP`, or Celery's `worker_process_init` in each prefork child, since a
  pool built before the fork is shared by every child — and closed in the matching shutdown hook.

## Ordering Is Not Guaranteed

Two consumers, a prefetch window, a redelivery behind newer messages or a retry republished at the
tail each reorder a queue. Either the handler does not care, or the order is bought explicitly:

- **Make it not matter**: the payload carries the aggregate's version, and the handler skips an
  event older than what is stored — the version column from `python-persistence`.
- **Or partition by key**: a Kafka record's key picks its partition, and one consumer handles a
  partition in order; RabbitMQ's `x-single-active-consumer` gives a queue one consumer at a time.
  Either way, order holds only while one message per key is in flight — concurrency inside the
  consumer undoes it.

## Testing

- **The handler is a plain function, so its unit tests need no broker**: they call it with the
  body and a fake, and the redelivery is a second call. The fake inherits the contract, lives in
  `tests/fakes.py` and passes the same contract suite as the real implementation
  (`python-contracts`) — here, that a repeated idempotency key reserves once.

```python
@final
class InMemoryWarehouse(Warehouse):
    def __init__(self) -> None:
        self.reserved_order_ids: list[OrderId] = []
        self._idempotency_keys: set[str] = set()

    @override
    async def reserve(self, order_id: OrderId, *, idempotency_key: str) -> None:
        if idempotency_key in self._idempotency_keys:
            return
        self._idempotency_keys.add(idempotency_key)
        self.reserved_order_ids.append(order_id)
```

```python
async def test_on_order_placed_redelivered_message_reserves_once() -> None:
    warehouse = InMemoryWarehouse()
    message = make_order_placed_v1()
    body = message.model_dump_json().encode()

    await on_order_placed(body, warehouse=warehouse)
    await on_order_placed(body, warehouse=warehouse)

    assert warehouse.reserved_order_ids == [OrderId(message.order_id)]
```

- **One integration test per queue against the real broker** publishes a message the handler
  rejects and asserts it arrives in the dead-letter queue. Acknowledgement, the delivery limit and
  dead-lettering exist only in the broker, and an in-memory test broker that runs the handler
  inline tests none of them — FastStream's two in `python-faststream`.

## The Same Rules Elsewhere

| | ack after the work | bounded attempts | dead letters | handler deadline |
|---|---|---|---|---|
| FastStream on RabbitMQ (`python-faststream`) | `AckPolicy.REJECT_ON_ERROR` | queue's `x-delivery-limit` | queue's `x-dead-letter-exchange` | `asyncio.timeout` |
| Celery | `acks_late=True` and `task_reject_on_worker_lost=True`; the default acks before running | `max_retries` (3) | none built in: a failed task is acked | `soft_time_limit`, `time_limit` |
| taskiq | `--ack-type` `when_saved` (default) or `when_executed` | `SmartRetryMiddleware(default_retry_count=…)` | none built in | `timeout` label |
| aiokafka | `enable_auto_commit=False`, `commit()` after; the default commits every 5 s whatever happened | your own counter | a dead-letter topic | `asyncio.timeout` |
| arq | — | `max_tries` (5) | none built in | `job_timeout` (300 s) |

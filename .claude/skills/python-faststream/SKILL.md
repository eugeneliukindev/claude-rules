---
name: python-faststream
description: >-
  FastStream on RabbitMQ — the library's mechanics; the consumer design itself is in
  python-workers: subscribers on a router built from the root's dependencies, AckPolicy and its
  REJECT_ON_ERROR default, quorum-queue x-delivery-limit and dead-letter arguments and what each
  policy does with them, the message_id FastStream invents per delivery, strict pydantic models
  rejected by FastStream's Python-mode validation, graceful_timeout, startup and lifespan hooks,
  and TestRabbitBroker versus a real broker on testcontainers. Use when Python code imports
  faststream, defines a RabbitBroker, RabbitRouter, RabbitQueue or subscriber, or runs faststream.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# FastStream

Checked against FastStream 0.7 on RabbitMQ 4.3. The consumer's design — the handler as a plain
function, idempotency, when to acknowledge, dead-lettering, one retry layer, deadlines, shutdown —
is in `python-workers`; this file is how FastStream and RabbitMQ carry it out, and the traps on the
way. Every number marked measured came from a handler that always raises, on a real broker.

## The Subscriber Hands the Body to the Handler

Keep the handler a plain function over the raw body and its dependencies (why:
`python-workers`). The subscriber is FastStream's wrapper around it: it takes the raw
`RabbitMessage` and passes `message.body` on. Subscribers are registered on a router that a
function builds from the dependencies it is handed, and `main()` builds the broker and includes it.
A module-level broker with a module-level session beside it is the global singleton
`python-wiring` forbids, and `context.set_global` is a service locator.

```python
# WRONG — importing the module reads the environment and builds the broker and the session
_settings = WorkerSettings()
broker = RabbitBroker(_settings.amqp_url)
warehouse = HttpWarehouse(niquests.AsyncSession(base_url=_settings.warehouse_url))

# CORRECT — the router is built from what main() hands it, and main() owns every lifetime
def build_order_router(*, warehouse: Warehouse) -> RabbitRouter:
    router = RabbitRouter()

    @router.subscriber(_ORDERS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
    async def on_order_placed_message(message: RabbitMessage) -> None:
        await on_order_placed(message.body, warehouse=warehouse)

    return router


async def main() -> None:
    settings = WorkerSettings()
    async with managed_warehouse_session(settings.warehouse_url) as session:
        broker = RabbitBroker(settings.amqp_url, graceful_timeout=_GRACEFUL_TIMEOUT_SECONDS)
        broker.include_router(build_order_router(warehouse=HttpWarehouse(session)))
        await FastStream(broker).run()


if __name__ == "__main__":
    asyncio.run(main())
```

- **`faststream run module:app` wants a module-level `app`.** Where the CLI is required — the
  `faststream[cli]` extra — `--factory`
  names a function that builds it, and the resources open in the app's `lifespan`, which wraps
  startup, the run and shutdown. `on_startup` hooks run before the broker connects and
  `after_startup` hooks after the subscribers are already consuming — neither is where a resource
  is built and handed out through `context`.

```python
def build_app() -> FastStream:
    settings = WorkerSettings()
    broker = RabbitBroker(settings.amqp_url, graceful_timeout=_GRACEFUL_TIMEOUT_SECONDS)

    @asynccontextmanager
    async def lifespan() -> AsyncIterator[None]:
        async with managed_warehouse_session(settings.warehouse_url) as session:
            broker.include_router(build_order_router(warehouse=HttpWarehouse(session)))
            yield

    return FastStream(broker, lifespan=lifespan)
```

## Acknowledgement Is the `ack_policy`

Acknowledge only after the work committed (why: `python-workers`). In FastStream the subscriber's
`ack_policy` decides; the default is `REJECT_ON_ERROR`, and a broker or router given one changes it
for every subscriber below. Measured on a quorum queue with `x-delivery-limit` and a dead-letter
exchange:

| `AckPolicy` | acked | a message whose handler raises |
|---|---|---|
| `ACK_FIRST` | on receipt | gone; a crash mid-handler loses it too |
| `ACK` | after the handler | acked anyway: gone, nothing dead-lettered |
| `NACK_ON_ERROR` | after the handler | requeued at once, never dead-lettered — over 300 deliveries in three seconds |
| `REJECT_ON_ERROR` (default) | after the handler | rejected once: dead-lettered after one attempt, or dropped without a DLX |

```python
# WRONG — acked on receipt: a worker killed mid-reservation loses the order
@router.subscriber(_ORDERS_QUEUE, ack_policy=AckPolicy.ACK_FIRST)
async def on_order_placed_message(message: RabbitMessage) -> None: ...

# CORRECT — acked when the handler returns; an error rejects it to the dead-letter exchange
@router.subscriber(_ORDERS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_order_placed_message(message: RabbitMessage) -> None: ...
```

State the policy even where it is the default: the dead-letter path below depends on it. A
cancelled handler — the shutdown below — is neither acked nor rejected, and comes back.

## The Queue Carries the Limit and the Dead-Letter Exchange

End a poison message in a dead-letter queue after a bounded number of deliveries (why:
`python-workers`). On RabbitMQ both bounds are queue arguments:

- **`x-dead-letter-exchange` takes every rejected message**; without it `REJECT_ON_ERROR` drops
  the message. The dead-letter queue must exist before the first rejection — a message routed to a
  queue nobody declared is dropped too (measured).
- **`x-delivery-limit` counts deliveries that never got an answer** — a worker killed mid-handler,
  a delivery abandoned at shutdown, each once; past the limit the message is dead-lettered
  (measured). Quorum queues default to a limit of 20 since RabbitMQ 4.0; name your own.
- **A requeueing nack does not count on RabbitMQ 4.3, a requeueing reject does** (measured):
  `NACK_ON_ERROR` loops forever even on a quorum queue, while `RejectMessage(requeue=True)` spends
  the whole limit at once, with no backoff.

```python
# WRONG — no dead-letter exchange: REJECT_ON_ERROR drops a failing order without a trace
_ORDERS_QUEUE: Final = RabbitQueue(_ORDERS_QUEUE_NAME)

# CORRECT — bounded deliveries, and every failure kept where someone can read and replay it
_ORDERS_QUEUE: Final = RabbitQueue(
    _ORDERS_QUEUE_NAME,
    queue_type=QueueType.QUORUM,
    arguments={
        "x-delivery-limit": _MAX_DELIVERIES,
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": _ORDERS_DEAD_LETTER_QUEUE_NAME,
    },
)
```

- **A broker policy can carry the same keys** (`delivery-limit`, `dead-letter-exchange`), and is
  the one to change later: a queue redeclared with different arguments is refused.

## One Retry Layer, Not `RejectMessage(requeue=True)`

Let exactly one layer retry each failure (why: `python-workers`). A requeue is the broker retrying
at once, so a handler that requeues on a transient error under a client that already retries
multiplies the attempts, and gains no backoff.

```python
# WRONG — the warehouse client already retries; requeueing on top multiplies its attempts
@router.subscriber(_ORDERS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_order_placed_message(message: RabbitMessage) -> None:
    try:
        await on_order_placed(message.body, warehouse=warehouse)
    except WarehouseError as error:
        raise RejectMessage(requeue=True) from error

# CORRECT — the client's policy is the only retry; once it is spent the order is dead-lettered
@router.subscriber(_ORDERS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_order_placed_message(message: RabbitMessage) -> None:
    await on_order_placed(message.body, warehouse=warehouse)
```

## `message_id` Is Not an Idempotency Key

Key idempotency on the event's own id from the payload (why: `python-workers`). FastStream's
`message.message_id` is whatever the publisher set, and **when the publisher set none, FastStream
invents a fresh one on every delivery** — measured with a message published without one: three
deliveries, three ids. A publisher on aio-pika stamps one per publish, so a relay that republishes
still gives the copy a new one. `correlation_id` behaves the same way.

## FastStream Validates in Python Mode

Validate the raw body as JSON with a strict model (why: `python-pydantic`). **An annotated message
parameter is validated against the dict FastStream already decoded, in Python mode**, so a strict
model rejects every UUID, `Decimal` and datetime in every valid message — measured: the UUID
arrives as a `str`, `is_instance_of` fails, and nothing is handled. Take the raw message, and
`model_validate_json(message.body)` in the handler.

```python
# WRONG — validated in Python mode: the UUID arrives as a str, and every message fails
@router.subscriber(_ORDERS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_order_placed_message(message: OrderPlacedV1) -> None:
    async with asyncio.timeout(_HANDLER_DEADLINE_SECONDS):
        await reserve_stock(warehouse, message.to_domain())

# CORRECT — the raw body reaches the handler, which validates it in JSON mode
@router.subscriber(_ORDERS_QUEUE, ack_policy=AckPolicy.REJECT_ON_ERROR)
async def on_order_placed_message(message: RabbitMessage) -> None:
    await on_order_placed(message.body, warehouse=warehouse)
```

A failed validation then escapes, and `REJECT_ON_ERROR` dead-letters the message on its first
delivery (measured).

## Deadlines and Shutdown

Give every handler a deadline inside the ack deadline, and the drain inside the orchestrator's
grace period (why: `python-workers`). FastStream has no handler timeout of its own — the handler's
`asyncio.timeout` is the deadline.

- **`FastStream.run()` handles `SIGTERM` and `SIGINT`**, and the broker's `graceful_timeout` bounds
  the wait for handlers in flight: **15 seconds by default, and `None` is not "wait forever" but no
  wait at all** — measured: `stop()` returned at once and the running handler never finished.
- **What is still running when the drain ends is cancelled and abandoned unacknowledged**, and the
  redelivery counts toward `x-delivery-limit`: a handler that cannot finish inside the drain is
  dead-lettered after that many deploys (measured).

```python
# WRONG — None skips the drain: every deploy abandons every handler in flight
broker = RabbitBroker(settings.amqp_url, graceful_timeout=None)
# CORRECT — named, and inside the 30-second grace period
broker = RabbitBroker(settings.amqp_url, graceful_timeout=_GRACEFUL_TIMEOUT_SECONDS)
```

## Testing

The handler's unit tests call the plain function with a fake (`python-workers`). FastStream adds
two levels above it:

- **`TestRabbitBroker` runs the subscriber inline**: it checks the router's wiring, the routing key
  and that a valid message reaches the handler, and raises the handler's exception into the test.
  It has no acknowledgement, no delivery limit and no dead-letter exchange.

```python
async def test_order_router_valid_message_reserves_stock() -> None:
    warehouse = InMemoryWarehouse()
    broker = RabbitBroker()
    broker.include_router(build_order_router(warehouse=warehouse))
    message = make_order_placed_v1()

    async with TestRabbitBroker(broker) as test_broker:
        await test_broker.publish(message.model_dump(mode="json"), _ORDERS_QUEUE_NAME)

    assert warehouse.reserved_order_ids == [OrderId(message.order_id)]
```

- **One integration test per queue against a real RabbitMQ** — `RabbitMqContainer` from
  `testcontainers.community.rabbitmq` (`python-pytest`) — publishes a message the handler rejects
  and reads it back from the dead-letter queue; the subscriber on that queue declares it.

```python
async def test_order_router_malformed_message_is_dead_lettered(amqp_url: str) -> None:
    broker = RabbitBroker(amqp_url)
    broker.include_router(build_order_router(warehouse=InMemoryWarehouse()))
    dead_letters = broker.subscriber(
        RabbitQueue(_ORDERS_DEAD_LETTER_QUEUE_NAME, queue_type=QueueType.QUORUM)
    )

    async with broker:
        await broker.start()
        await broker.publish({"version": 99}, _ORDERS_QUEUE_NAME)
        dead_letter = await dead_letters.get_one(timeout=_DEAD_LETTER_WAIT_SECONDS)

    assert dead_letter is not None
```

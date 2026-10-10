---
name: python-redis
description: >-
  redis-py (redis.asyncio) mechanics: one client built by the composition root and closed with
  aclose, the constructor's default retry of ten attempts versus Redis.from_url with none, socket
  and connect timeouts, max_connections and MaxConnectionsError, ex truncating a timedelta to
  whole seconds versus px, ttl answering -1 and -2, lock() with timeout and blocking_timeout and
  LockNotOwnedError, pub/sub resubscribing silently or raising ConnectionError, and the pubsub
  output buffer limit — shown as RedisCache implementing the cache contract and
  RedisOrderEventChannel implementing the streaming channel contract. The cache design is in
  python-caching, the fan-out design in python-streaming. Use when Python code imports redis or
  redis.asyncio, builds a Redis client, or calls set, lock or pubsub on it.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# redis-py

Checked against redis-py 8.1 (`redis.asyncio`) and redis 8; everything marked *measured* was run
against a real server. What a cache must do whatever holds it — the contract, keys, TTLs, the wire
format, stampedes, invalidation — is `python-caching`; the channel contract, the relay and its fake
are `python-streaming`. This file is how redis-py carries them out, and where its defaults
disagree. Retries in general are `python-boundaries`; who builds and closes the client is
`python-wiring`.

## Contents

- The Client: Built Once, Closed with `aclose`
- Retry Depends on How the Client Was Built
- Expiry: `ex` Truncates, `px` Does Not
- `RedisCache`
- Locks
- Pub/Sub: `RedisOrderEventChannel`
- Testing

## The Client: Built Once, Closed with `aclose`

- **One client per process, built by the composition root and closed with `await
  client.aclose()`** — `close()` is deprecated since 5.0.1. A client per request opens a pool per
  request. The cache and the pub/sub channel share it: a subscription takes a connection of its own
  from the same pool.
- **Timeouts are chosen, not inherited**: both `socket_connect_timeout` and `socket_timeout`
  default to five seconds, so an unreachable server holds every call that long.
- **The pool raises instead of waiting.** The asyncio `ConnectionPool` holds at most 100
  connections by default (`max_connections=`), and the call past that raises
  `MaxConnectionsError` — a `ConnectionError` — at once (*measured*); `BlockingConnectionPool`
  waits instead, up to its `timeout`. An adapter that catches `RedisError` counts it like any other
  failure.
- **Every string reply is typed `bytes | str`**, because `decode_responses` decides it at runtime.
  A client for payloads keeps the default `decode_responses=False`, and the adapter narrows the
  type with `isinstance` rather than a `cast`.

```python
@asynccontextmanager
async def managed_redis(*, url: str, timeout_seconds: float) -> AsyncIterator[Redis]:
    client = Redis.from_url(
        url,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
        retry=Retry(NoBackoff(), retries=0),
    )
    try:
        yield client
    finally:
        await client.aclose()
```

`Retry` is `redis.asyncio.retry.Retry`, `NoBackoff` is `redis.backoff.NoBackoff`.

## Retry Depends on How the Client Was Built

**The two ways to build a client retry differently, and nothing in the call says so.**
`Redis(host=...)` carries a `Retry` of ten retries with exponential backoff on `ConnectionError`
and `TimeoutError`; `Redis.from_url(...)` builds its pool's connections with no retry at all
(*measured*: `retries` is 10 against 0 on the connection each one makes). Two consequences:

- **Time to fail.** With a 0.2-second connect timeout, a `get` against an unreachable host failed
  after 6.4 seconds through the constructor's retry, and after 0.2 with `retries=0` or through
  `from_url` (*measured*). A cache read is never retried — a cache failure is a counted miss, never
  an error (why and how: `python-caching`).
- **What a dropped subscription looks like** — silent resubscription or `ConnectionError`; the
  pub/sub section below.

So **pass `retry=` explicitly, whichever way the client is built**: a later switch from `from_url`
to the constructor, or a library that builds the client for you, then cannot add ten retries
behind every call.

```python
# WRONG — the constructor's ten retries: an unreachable cache holds each read for six seconds
client = Redis(
    host=host, port=port, socket_connect_timeout=timeout_seconds, socket_timeout=timeout_seconds
)

# CORRECT — one attempt, bounded by the timeout chosen for the cache
client = Redis(
    host=host,
    port=port,
    socket_connect_timeout=timeout_seconds,
    socket_timeout=timeout_seconds,
    retry=Retry(NoBackoff(), retries=0),
)
```

## Expiry: `ex` Truncates, `px` Does Not

- **A `timedelta` passed as `ex=` is truncated to whole seconds**: 1.9 seconds becomes 1, and
  anything under a second becomes `EX 0`, which redis rejects with `invalid expire time`
  (*measured*). `px=` takes the same `timedelta` in milliseconds, so a contract that accepts any
  `timedelta` is implemented with `px`.

```python
# WRONG — a jittered 0.8-second TTL becomes EX 0, and redis refuses the write
await self._client.set(key, value, ex=ttl)

# CORRECT — milliseconds: the TTL the contract was given is the TTL redis holds
await self._client.set(key, value, px=ttl)
```

- **`ttl` answers `-1` for a key with no expiry and `-2` for no key at all**; `pttl` the same in
  milliseconds. A test that every written key expires asserts a positive TTL, never "not `None`".

## `RedisCache`

The cache contract from `python-caching`, on redis. `RedisError` is the root of every redis-py
error — connection, timeout, a full pool, a refused write — so one `except` turns them all into
the empty-cache answer, counted:

```python
@final
class RedisCache(Cache):
    def __init__(self, client: Redis) -> None:
        self._client = client

    @override
    async def get(self, key: str) -> bytes | None:
        try:
            value = await self._client.get(key)
        except RedisError as error:
            _CACHE_FAILURES.add(1, {"operation": "get", "error.type": type(error).__name__})
            return None
        return value.encode() if isinstance(value, str) else value

    @override
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None:
        try:
            await self._client.set(key, value, px=ttl)
        except RedisError as error:
            _CACHE_FAILURES.add(1, {"operation": "set", "error.type": type(error).__name__})

    @override
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        try:
            was_set = await self._client.set(key, value, px=ttl, nx=True)
        except RedisError as error:
            _CACHE_FAILURES.add(1, {"operation": "add", "error.type": type(error).__name__})
            return True
        return was_set is True

    @override
    async def delete(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except RedisError as error:
            _CACHE_FAILURES.add(1, {"operation": "delete", "error.type": type(error).__name__})
```

```python
# WRONG — a redis outage raises through every read, and the cache's failure is the service's
@override
async def get(self, key: str) -> bytes | None:
    value = await self._client.get(key)
    return value.encode() if isinstance(value, str) else value
```

`set(..., nx=True)` answers `True` when it wrote and `None` when the key existed. `_CACHE_FAILURES`
is a module-level counter (`python-observability`). It lives in `cache/redis.py`, the one module
that imports redis.

## Locks

redis-py's `client.lock()` is the same efficiency lock as the cache's `add` marker — a lock in a
cache saves work and guarantees nothing; correctness comes from the resource (why and how:
`python-caching`). Its own mechanics:

- **`timeout=` and `blocking_timeout=` are both always set.** Both default to `None`:
  `timeout=None` writes a lock key with no expiry, held forever by a holder that dies (*measured*:
  `ttl` answers `-1`); `blocking_timeout=None` waits forever to acquire.
- Used as `async with`, a lock not acquired within `blocking_timeout` raises `LockError`.
- **A holder learns its lock expired only at release**, with `LockNotOwnedError`, after its writes
  (*measured*: a 0.2-second lock was taken by a second client, and the first one's `release()`
  raised).

```python
# WRONG — no expiry and no wait limit: a crashed holder blocks every later caller for good
async with self._client.lock(_invoice_lock_key(order_id)):
    await self._issue(order_id)

# CORRECT — the lock expires, and a caller gives up waiting
async with self._client.lock(
    _invoice_lock_key(order_id),
    timeout=_INVOICE_LOCK_SECONDS,
    blocking_timeout=_INVOICE_LOCK_WAIT_SECONDS,
):
    await self._issue(order_id)
```

## Pub/Sub: `RedisOrderEventChannel`

The channel contract, the relay and the fake are in `python-streaming`; the contract's promise is
that **a subscription that may have missed an event raises `OrderEventChannelLostError`**. Here is
how redis-py shows a gap, and the implementation that turns it into that error.

**What a dropped connection looks like depends on how the client was built** (*measured*, with
`CLIENT KILL TYPE pubsub` from a second client). Through the constructor's retry,
`pubsub.listen()` reconnects and resubscribes without raising: an event published in between is
never delivered, and the only sign is a second `subscribe` confirmation. Through `from_url`, or
with `retries=0`, `listen()` raises `ConnectionError`. The implementation turns both into the
contract's error while iterating — not only on leaving the `async with`, where the consumer's loop
would never see it.

```python
# WRONG — only messages are read: after a silent resubscribe nobody learns what was missed
async def _decode_events(messages: AsyncIterator[Any]) -> AsyncIterator[OrderEvent]:
    async for received in messages:
        match received:
            case {"type": "message", "data": bytes() as payload}:
                try:
                    decoded = _OrderEventMessage.model_validate_json(payload)
                except ValidationError:
                    logger.warning("order event dropped", extra={"payload_size": len(payload)})
                    continue
                yield decoded.to_domain()


# CORRECT — a second confirmation is a gap, and the contract says so
async def _decode_events(messages: AsyncIterator[Any]) -> AsyncIterator[OrderEvent]:
    async for received in messages:
        match received:
            case {"type": "subscribe"}:
                raise OrderEventChannelLostError(_ORDER_EVENTS_CHANNEL)
            case {"type": "message", "data": bytes() as payload}:
                try:
                    decoded = _OrderEventMessage.model_validate_json(payload)
                except ValidationError:
                    logger.warning("order event dropped", extra={"payload_size": len(payload)})
                    continue
                yield decoded.to_domain()
```

The whole implementation, in `order_events/redis_pubsub.py` — named for its mechanism, so a Redis
Streams implementation, which would also replay what a dropped subscriber missed, is a second file
beside it. `subscribe` reads the first confirmation before it yields, so the relay ends its streams
only once the subscription is live; the wire model is a queued payload, so it ignores fields a
newer worker adds (`python-pydantic`), and a payload that fails is logged and skipped, never a
reason to drop the subscription.

```python
@final
class _OrderEventMessage(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="ignore")

    version: Literal[1] = 1
    order_id: str
    sequence: int
    status: OrderStatus

    @classmethod
    def from_domain(cls, event: OrderEvent) -> Self:
        return cls(order_id=event.order_id, sequence=event.sequence, status=event.status)

    def to_domain(self) -> OrderEvent:
        return OrderEvent(
            order_id=OrderId(self.order_id), sequence=self.sequence, status=self.status
        )


@final
class RedisOrderEventChannel(OrderEventChannel):
    def __init__(self, *, redis: Redis) -> None:
        self._redis = redis

    @override
    async def publish(self, event: OrderEvent) -> None:
        message = _OrderEventMessage.from_domain(event)
        await self._redis.publish(_ORDER_EVENTS_CHANNEL, message.model_dump_json())

    @override
    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[OrderEvent]]:
        async with self._redis.pubsub() as pubsub:
            messages = pubsub.listen()
            try:
                await pubsub.subscribe(_ORDER_EVENTS_CHANNEL)
                await anext(messages)  # the confirmation: the subscription is live from here
            except RedisConnectionError as error:
                raise OrderEventChannelLostError(_ORDER_EVENTS_CHANNEL) from error
            yield _decode_events(messages)


async def _decode_events(messages: AsyncIterator[Any]) -> AsyncIterator[OrderEvent]:
    try:
        async for received in messages:
            match received:
                case {"type": "subscribe"}:
                    raise OrderEventChannelLostError(_ORDER_EVENTS_CHANNEL)
                case {"type": "message", "data": bytes() as payload}:
                    try:
                        decoded = _OrderEventMessage.model_validate_json(payload)
                    except ValidationError:
                        logger.warning("order event dropped", extra={"payload_size": len(payload)})
                        continue
                    yield decoded.to_domain()
    except RedisConnectionError as error:
        raise OrderEventChannelLostError(_ORDER_EVENTS_CHANNEL) from error
```

`RedisConnectionError` is `redis.exceptions.ConnectionError`, imported under that name so it does
not shadow the builtin.

- **A subscription idle past `socket_timeout` is not a gap**: *measured*, `listen()` kept waiting
  through three times a 0.3-second timeout and then delivered, so the root's shared client, with
  its short cache timeouts, serves the subscription too.
- **redis drops a subscriber that stops reading**: the default `client-output-buffer-limit pubsub
  32mb 8mb 60` disconnects one whose unread output passes 32 MiB, or 8 MiB for a minute — which
  the implementation above reports as a gap. The relay that never awaits a socket is what keeps it
  reading (`python-streaming`).

The lifespan builds the client once and both implementations on it, runs the relay in its task
group and cancels it at shutdown (`python-fastapi`):

```python
def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with (
            managed_redis(
                url=settings.redis_url, timeout_seconds=settings.redis_timeout_seconds
            ) as redis,
            asyncio.TaskGroup() as tasks,
        ):
            feed = OrderFeed()
            order_events = RedisOrderEventChannel(redis=redis)
            relay = tasks.create_task(OrderEventRelay(channel=order_events, feed=feed).run())
            yield {"cache": RedisCache(redis), "feed": feed, "order_events": order_events}
            relay.cancel()

    return FastAPI(lifespan=lifespan)
```

## Testing

- **Both implementations join their contract's suite** as the `redis` parameter, with the
  integration marker, against `testcontainers.community.redis.RedisContainer("redis:8")`
  (`python-pytest`) — the module `testcontainers.redis` is deprecated, and with warnings as errors
  importing it fails the run. Each test starts from `flushdb()` on a client built by the same
  `managed_redis` the root uses.
- **The channel's loss test drops the subscription from a second client** —
  `await admin.client_kill_filter(_type="pubsub")` — and expects `OrderEventChannelLostError` from
  the next `anext`. Run it for a client from the constructor and one from `from_url`: they fail
  differently, and the implementation has to catch both.
- **One test belongs to `RedisCache` alone**: no key it writes lives forever.

```python
async def test_every_written_key_expires(redis_client: Redis) -> None:
    await RedisCache(redis_client).set(_ORDER_KEY, _ORDER_PAYLOAD, ttl=_ORDER_TTL)

    ttls_seconds = [await redis_client.ttl(key) async for key in redis_client.scan_iter()]

    assert ttls_seconds
    assert all(ttl_seconds > 0 for ttl_seconds in ttls_seconds)
```

---
name: python-redis
description: >-
  redis-py mechanics behind the cache and channel contracts: one client with chosen timeouts and
  retry, pool limits, px against ex, RedisCache, locks, pub/sub gaps, tests. Use when code imports
  redis or redis.asyncio, builds a Redis client, or calls set, lock or pubsub on it.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# redis-py

Checked against redis-py 8.1 (`redis.asyncio`) and redis 8; everything marked *measured* was run
against a real server. What a cache must do whatever holds it is `python-caching`; the channel
contract, the relay and its fake are `python-streaming`. Retries in general are `python-boundaries`;
who builds and closes the client is `python-wiring`.

## The Client

### One client per process, built by the composition root with chosen timeouts, closed with `aclose`

**Why:** a client per request opens a pool per request. The cache and the pub/sub channel share the
one client — a subscription takes a connection of its own from the same pool. `close()` is
deprecated since 5.0.1. Both `socket_connect_timeout` and `socket_timeout` default to five
seconds, so an unreachable server holds every call that long unless the timeouts are chosen.

**Example:**
```python
# WRONG — a client per call: a pool per request, five-second default timeouts, never closed
async def cached_profile(user_id: UserId, *, redis_url: str) -> bytes | None:
    client = Redis.from_url(redis_url)
    value = await client.get(_profile_key(user_id))
    return value.encode() if isinstance(value, str) else value


# CORRECT — built once by the root, with the timeouts the cache was given, and closed
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

### `retry=` is passed explicitly, whichever way the client is built

**Why:** `Redis(host=...)` carries a `Retry` of ten retries with exponential backoff on
`ConnectionError` and `TimeoutError`; `Redis.from_url(...)` builds its connections with none
(*measured*: `retries` is 10 against 0). With a 0.2-second connect timeout, a `get` against an
unreachable host failed after 6.4 seconds through the constructor's retry, and after 0.2 with
`retries=0` (*measured*) — and a cache read is never retried, its failure is a counted miss. Passed
explicitly, a later switch between the two, or a library that builds the client, cannot add ten
retries behind every call. How a dropped subscription looks depends on it too
([pubsub.md](pubsub.md)). `Retry` is `redis.asyncio.retry.Retry`, `NoBackoff` is
`redis.backoff.NoBackoff`.

**Example:**
```python
# WRONG — the constructor's ten retries: an unreachable cache holds each read for six seconds
def build_redis(*, host: str, port: int, timeout_seconds: float) -> Redis:
    return Redis(
        host=host, port=port, socket_connect_timeout=timeout_seconds, socket_timeout=timeout_seconds
    )


# CORRECT — one attempt, bounded by the timeout chosen for the cache
def build_redis(*, host: str, port: int, timeout_seconds: float) -> Redis:
    return Redis(
        host=host,
        port=port,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
        retry=Retry(NoBackoff(), retries=0),
    )
```

### The pool is sized, and a full pool's error is a failure like any other

**Why:** the asyncio `ConnectionPool` holds at most 100 connections by default, and the call past
that raises `MaxConnectionsError` — a `ConnectionError` — at once (*measured*);
`BlockingConnectionPool` waits instead, up to its `timeout`. An adapter that catches `RedisError`
counts it with the rest; the size is a named setting, not a default nobody chose.

### A reply is narrowed with `isinstance`, because `decode_responses` decides its type at runtime

**Why:** every string reply is typed `bytes | str`. A client for payloads keeps the default
`decode_responses=False`; a `cast` to `bytes` is a claim the checker cannot verify, and a client
built with `decode_responses=True` breaks it silently.

**Example:**
```python
# WRONG — a claim: a client built with decode_responses=True returns str, and this passes it on
async def read_payload(key: str, *, client: Redis) -> bytes | None:
    return cast(bytes | None, await client.get(key))


# CORRECT — narrowed: whatever the client was built with, the caller gets bytes
async def read_payload(key: str, *, client: Redis) -> bytes | None:
    value = await client.get(key)
    return value.encode() if isinstance(value, str) else value
```

## Expiry

### A TTL goes in as `px`, never `ex`

**Why:** a `timedelta` passed as `ex=` is truncated to whole seconds — 1.9 seconds becomes 1, and
anything under a second becomes `EX 0`, which redis rejects with `invalid expire time`
(*measured*). `px=` takes the same `timedelta` in milliseconds, so a contract that accepts any
`timedelta` is implemented with `px`. `ttl` answers `-1` for a key with no expiry and `-2` for no
key at all, `pttl` the same in milliseconds — a test that a key expires asserts a positive TTL.

**Example:**
```python
# WRONG — a jittered 0.8-second TTL becomes EX 0, and redis refuses the write
async def write_payload(key: str, value: bytes, *, ttl: timedelta, client: Redis) -> None:
    await client.set(key, value, ex=ttl)


# CORRECT — milliseconds: the TTL the contract was given is the TTL redis holds
async def write_payload(key: str, value: bytes, *, ttl: timedelta, client: Redis) -> None:
    await client.set(key, value, px=ttl)
```

## `RedisCache`

### `RedisCache` turns every `RedisError` into the empty-cache answer, counted

**Why:** `RedisError` is the root of every redis-py error — connection, timeout, a full pool, a
refused write — so one `except` per operation gives the contract's promise: a cache that cannot
answer behaves as an empty one. `set(..., nx=True)` answers `True` when it wrote and `None` when
the key existed. The class lives in `cache/redis.py`, the one module that imports redis;
`_CACHE_FAILURES` is a module-level counter (`python-observability`).

**Example:**
```python
# WRONG — a redis outage raises through every operation, and the cache's failure is the service's
@final
class RedisCache(Cache):
    def __init__(self, client: Redis) -> None:
        self._client = client

    @override
    async def get(self, key: str) -> bytes | None:
        value = await self._client.get(key)
        return value.encode() if isinstance(value, str) else value

    @override
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None:
        await self._client.set(key, value, px=ttl)

    @override
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        return await self._client.set(key, value, px=ttl, nx=True) is True

    @override
    async def delete(self, key: str) -> None:
        await self._client.delete(key)


# CORRECT — each operation answers as an empty cache would, and the failure is counted
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

## Locks

**Before calling `client.lock()`, read [locks.md](locks.md)** — `timeout` and `blocking_timeout`
always set, `LockError`, and `LockNotOwnedError` arriving only at release.

## Pub/Sub

**Before subscribing with `pubsub()` or publishing to a channel other processes listen on, read
[pubsub.md](pubsub.md)** — a silent resubscribe or a `ConnectionError` depending on how the client
was built, both raised as the contract's gap, the subscription live before it yields, the output
buffer limit, the whole `RedisParcelEventChannel`.

## Testing

**Before writing a test against redis, read [testing.md](testing.md)** — both implementations in
their contract suites on testcontainers, the loss test that kills a subscription, every written key
expiring.

---
name: python-redis
description: >-
  redis-py mechanics: one client per process with chosen timeouts and retry, closed by async with,
  pool limits, px against ex, an outage answered as a counted miss, locks, pub/sub gaps, tests.
  Use when code imports redis or redis.asyncio, builds a Redis client, or calls set, lock or pubsub
  on it. Not for cache design (python-caching).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# redis-py

Checked against redis-py 8.1 (`redis.asyncio`) and redis 8; everything marked *measured* was run
against a real server. What a cache must do whatever holds it is `python-caching`; fanning one
subscription out to many client streams is `python-streaming`.

## The Client

### One client per process, entered by the composition root with `async with`

**Why:** a client per request opens a pool per request. Every use in the process — the cache, the
pub/sub channel, the locks — shares the one client, and a subscription takes a connection of its
own from the same pool. `Redis` is an async context manager whose exit closes the pool; where it
cannot be entered, `aclose()` closes it — `close()` is deprecated since 5.0.1. Both
`socket_connect_timeout` and `socket_timeout` default to five seconds, so an unreachable server
holds every call that long unless the timeouts are chosen. The tests build their client with the
same function.

**Example:**
```python
# WRONG — a client per call: a pool per request, five-second default timeouts, never closed
async def read_free_bays(level_id: LevelId, *, redis_url: str) -> bytes | None:
    client = Redis.from_url(redis_url)
    snapshot = await client.get(_level_snapshot_key(level_id))
    return snapshot if isinstance(snapshot, bytes) else None


# CORRECT — built with chosen timeouts and no retry, entered once by the root, closed on exit
def build_occupancy_client(*, url: str, timeout_seconds: float = _REDIS_TIMEOUT_SECONDS) -> Redis:
    return Redis.from_url(
        url,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
        retry=Retry(NoBackoff(), retries=0),
    )


async def main() -> None:
    settings = Settings()
    async with build_occupancy_client(url=settings.redis_url) as client:
        await serve_occupancy_board(client=client)
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

- A second `subscribe` confirmation is a gap, raised as the channel's error
- A `ConnectionError` while listening is the channel's error too, and a bad payload is skipped
- `subscribe` reads the first confirmation before it yields

**Example:**
```python
# WRONG — the constructor's ten retries: an unreachable replica holds each read for six seconds
def build_replica_client(
    *, host: str, port: int, timeout_seconds: float = _REDIS_TIMEOUT_SECONDS
) -> Redis:
    return Redis(
        host=host, port=port, socket_connect_timeout=timeout_seconds, socket_timeout=timeout_seconds
    )


# CORRECT — one attempt, bounded by the timeout chosen for the client
def build_replica_client(
    *, host: str, port: int, timeout_seconds: float = _REDIS_TIMEOUT_SECONDS
) -> Redis:
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
`BlockingConnectionPool` waits instead, up to its `timeout`. Code that catches `RedisError` counts
it with the rest; the size is a named setting, not a default nobody chose.

### A reply is narrowed with `isinstance`, because `decode_responses` decides its type at runtime

**Why:** every string reply is typed `bytes | str`. A client for payloads keeps the default
`decode_responses=False`; a `cast` to `bytes` is a claim the checker cannot verify, and a client
built with `decode_responses=True` breaks it silently.

**Example:**
```python
# WRONG — a claim: a client built with decode_responses=True returns str, and this passes it on
async def read_level_snapshot(level_id: LevelId, *, client: Redis) -> bytes | None:
    return cast(bytes | None, await client.get(_level_snapshot_key(level_id)))


# CORRECT — narrowed: whatever the client was built with, the caller gets bytes
async def read_level_snapshot(level_id: LevelId, *, client: Redis) -> bytes | None:
    snapshot = await client.get(_level_snapshot_key(level_id))
    return snapshot.encode() if isinstance(snapshot, str) else snapshot
```

## Expiry

### A TTL goes in as `px`, never `ex`

**Why:** a `timedelta` passed as `ex=` is truncated to whole seconds — 1.9 seconds becomes 1, and
anything under a second becomes `EX 0`, which redis rejects with `invalid expire time`
(*measured*). `px=` takes the same `timedelta` in milliseconds. `ttl` answers `-1` for a key with
no expiry and `-2` for no key at all, `pttl` the same in milliseconds — a test that a key expires
asserts a positive TTL.

**Example:**
```python
# WRONG — a jittered 0.8-second TTL becomes EX 0, and redis refuses the write
async def write_level_snapshot(
    level_id: LevelId, snapshot: bytes, *, ttl: timedelta, client: Redis
) -> None:
    await client.set(_level_snapshot_key(level_id), snapshot, ex=ttl)


# CORRECT — milliseconds: the TTL the caller chose is the TTL redis holds
async def write_level_snapshot(
    level_id: LevelId, snapshot: bytes, *, ttl: timedelta, client: Redis
) -> None:
    await client.set(_level_snapshot_key(level_id), snapshot, px=ttl)
```

## An Outage Is a Miss

### Code that uses redis as a cache catches `RedisError` and answers as an empty cache, counted

**Why:** `RedisError` is the root of every redis-py error — connection, timeout, a full pool, a
refused write — so one `except` per call turns an outage into "slower, still correct": a read is a
miss, a write does nothing, and the board is served from the sensors' database. `set(..., nx=True)`
answers `True` when it wrote and `None`, not `False`, when the key existed. The class lives in the
one module that imports redis.

**Example:**
```python
# WRONG — a redis outage raises through every call, and the cache's failure is the board's
@final
class LevelOccupancyCache:
    def __init__(self, *, client: Redis, ttl: timedelta = _OCCUPANCY_TTL) -> None:
        self._client = client
        self._ttl = ttl

    async def find(self, level_id: LevelId) -> LevelOccupancy | None:
        snapshot = await self._client.get(_level_snapshot_key(level_id))
        return _occupancy_from_snapshot(snapshot) if isinstance(snapshot, bytes) else None

    async def store(self, occupancy: LevelOccupancy) -> None:
        snapshot = _occupancy_to_snapshot(occupancy)
        await self._client.set(_level_snapshot_key(occupancy.level_id), snapshot, px=self._ttl)

    async def claim_recount(self, level_id: LevelId) -> bool:
        claimed = await self._client.set(_recount_key(level_id), b"", px=self._ttl, nx=True)
        return claimed is True


# CORRECT — each call answers as an empty cache would, and the failure is counted
@final
class LevelOccupancyCache:
    def __init__(self, *, client: Redis, ttl: timedelta = _OCCUPANCY_TTL) -> None:
        self._client = client
        self._ttl = ttl

    async def find(self, level_id: LevelId) -> LevelOccupancy | None:
        try:
            snapshot = await self._client.get(_level_snapshot_key(level_id))
        except RedisError as error:
            _count_occupancy_failure("get", error)
            return None
        return _occupancy_from_snapshot(snapshot) if isinstance(snapshot, bytes) else None

    async def store(self, occupancy: LevelOccupancy) -> None:
        snapshot = _occupancy_to_snapshot(occupancy)
        try:
            await self._client.set(_level_snapshot_key(occupancy.level_id), snapshot, px=self._ttl)
        except RedisError as error:
            _count_occupancy_failure("set", error)

    async def claim_recount(self, level_id: LevelId) -> bool:
        try:
            claimed = await self._client.set(_recount_key(level_id), b"", px=self._ttl, nx=True)
        except RedisError as error:
            _count_occupancy_failure("set_nx", error)
            return True
        return claimed is True


def _count_occupancy_failure(operation: str, error: RedisError) -> None:
    _OCCUPANCY_CACHE_FAILURES.add(1, {"operation": operation, "error.type": type(error).__name__})
```

## Locks

**Before calling `client.lock()`, read [locks.md](locks.md)** — `timeout` and `blocking_timeout`
always set, `LockError`, and `LockNotOwnedError` arriving only at release.

- `lock()` is always given `timeout` and `blocking_timeout`

## Pub/Sub

**Before subscribing with `pubsub()` or publishing to a channel other processes listen on, read
[pubsub.md](pubsub.md)** — a silent resubscribe or a `ConnectionError` depending on how the client
was built, both raised as one gap error, the subscription live before it yields, the output buffer
limit.

## Testing

**Before writing a test against redis, read [testing.md](testing.md)** — a real redis from
testcontainers with the production client, the loss test that kills a subscription, every written
key expiring.

- Tests run against a real redis from testcontainers, on the client the root builds
- The loss test kills the subscription from a second client, for both kinds of client
- A cache in redis has one test of its own: no key it writes lives forever

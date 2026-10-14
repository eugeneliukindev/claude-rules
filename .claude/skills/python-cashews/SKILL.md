---
name: python-cashews
description: >-
  cashews mechanics: an instance the composition root sets up and closes, safe setup options, bytes
  under the null pickler, an adapter that turns failures into misses, decorator traps, locks,
  invalidation, tests. Use when code imports cashews, calls cache.setup, or decorates a function
  with @cache, @cache.locked or @cache.invalidate. Not for cache design (python-caching).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# cashews

Checked against cashews 7.6 with redis-py 8.1, against redis 8; everything marked *measured* was run
against a real server. What a cache must do whatever the library — keys, TTLs, stampedes,
invalidation after commit — is `python-caching`; the redis-py client underneath is `python-redis`.
`import cashews` and write `cashews.Cache`, so the library's class is never confused with a cache
class of the application's own.

## Setup

### The root sets up a `cashews.Cache` of its own and closes it, never the package's global

**Why:** the README calls `cache.setup(...)` on the global `cashews.cache` at import time — the
settings read on import that `modules.md` forbids, and one object every test shares. `cashews.Cache`
is not a context manager: the root builds the instance, calls `setup()` with the URL from settings,
and awaits `close()` in a `finally`; `setup()` does not connect, the first command does.

**Example:**
```python
# WRONG — the package global, configured at import from the environment
cashews.cache.setup(os.environ["CACHE_URL"])


# CORRECT — the root's own instance, set up from settings and closed on the way out
async def main() -> None:
    settings = Settings()
    seat_maps = cashews.Cache(name="seat-maps")
    set_up_seat_map_cache(
        seat_maps, url=settings.cache_url, timeout_seconds=settings.cache_timeout_seconds
    )
    try:
        await serve_box_office(seat_maps=SeatMapCache(cache=seat_maps))
    finally:
        await seat_maps.close()
```

### Four defaults are overridden in the one `setup()` call

**Why:** `pickle_type` — the redis backend pickles values (next rule). `suppress=True` turns a
failure into a miss, which is right, but logs it at `ERROR` with a traceback on every command — a
line per request while redis is down; with `suppress=False` every redis-py error arrives as
`CacheBackendInteractionError` with the original as its `__cause__` (*measured*), counted where it
is caught. The connect timeout is redis-py's five seconds — cashews sets only `socket_timeout=1` —
and *measured*, with redis unreachable a decorated call took ten seconds. The pool holds ten
connections and waits ten seconds for one. cashews builds its pool through `from_url`, so no
retry is added underneath (*measured*), and `retry=` is passed anyway so a later default cannot.
The tests set up their instance with the same function.

**Example:**
```python
# WRONG — pickle, an ERROR log per failed command, five seconds to give up, ten pooled connections
def set_up_seat_map_cache(cache: cashews.Cache, *, url: str, timeout_seconds: float) -> None:
    cache.setup(url)


# CORRECT — bytes only, failures raised to the code that counts them, every wait bounded
def set_up_seat_map_cache(
    cache: cashews.Cache,
    *,
    url: str,
    timeout_seconds: float,
    max_connections: int = _CACHE_MAX_CONNECTIONS,
) -> None:
    cache.setup(
        url,
        pickle_type="null",
        suppress=False,
        socket_connect_timeout=timeout_seconds,
        socket_timeout=timeout_seconds,
        retry=Retry(NoBackoff(), retries=0),
        max_connections=max_connections,
        wait_for_connection_timeout=timeout_seconds,
    )
```

## Values

### A value is the payload's bytes, under `pickle_type="null"`

**Why:** the redis backend pickles by default — *measured*, a pickle written to a key with plain
redis-py ran its code inside `cache.get`. With `pickle_type="null"` `bytes` are stored under a
`bytes:` tag and come back as `bytes`, and a forged pickle comes back as `None`. `secret=` is not
the fix: it signs entries and rejects a forged one by raising `UnSecureDataError` out of the call
(*measured*), and the values are still pickles. `pickle_type="json"` hands back dicts, and a value
json cannot encode raises `TypeError` out of the decorated call itself (*measured*).
`cashews.serialize.register_type` keeps a process-wide registry keyed by the bare class name, so
two `SeatMap` classes in two modules collide.

**Example:**
```python
# WRONG — pickled: a renamed class breaks the reader, and a forged entry runs on get
async def store_seat_map(
    seat_map: SeatMap, *, cache: cashews.Cache, ttl: timedelta = _SEAT_MAP_TTL
) -> None:
    await cache.set(_seat_map_key(seat_map.screening_id), seat_map, expire=ttl)


# CORRECT — the payload's bytes, the shape versioned in the key
async def store_seat_map(
    seat_map: SeatMap, *, cache: cashews.Cache, ttl: timedelta = _SEAT_MAP_TTL
) -> None:
    payload = _seat_map_to_payload(seat_map)
    await cache.set(_seat_map_key(seat_map.screening_id), payload, expire=ttl)
```

## The Adapter

### A class of the application's own wraps `cashews.Cache`, one `except` per call

**Why:** the cache is an optimization, so a backend failure is a counted miss — a read answers
`None`, a write does nothing — and the box office serves from the source. `get` is typed `Any`;
under the null pickler only `bytes` come back, and anything else is a miss. cashews sends a TTL as
milliseconds, so a sub-second `timedelta` survives — but **a TTL of zero writes a key that never
expires** (*measured*: `ttl` answered `-1`), so a computed TTL never reaches zero. It lives in the
one module that imports cashews, and only it sees a `cashews.Cache`.

**Example:**
```python
# WRONG — a backend failure raises through every call into the box office
@final
class SeatMapCache:
    def __init__(self, *, cache: cashews.Cache, ttl: timedelta = _SEAT_MAP_TTL) -> None:
        self._cache = cache
        self._ttl = ttl

    async def find(self, screening_id: ScreeningId) -> SeatMap | None:
        value = await self._cache.get(_seat_map_key(screening_id))
        return _seat_map_from_payload(value) if isinstance(value, bytes) else None

    async def store(self, seat_map: SeatMap) -> None:
        payload = _seat_map_to_payload(seat_map)
        await self._cache.set(_seat_map_key(seat_map.screening_id), payload, expire=self._ttl)

    async def forget(self, screening_id: ScreeningId) -> None:
        await self._cache.delete(_seat_map_key(screening_id))


# CORRECT — each call answers as an empty cache would, and the failure is counted
@final
class SeatMapCache:
    def __init__(self, *, cache: cashews.Cache, ttl: timedelta = _SEAT_MAP_TTL) -> None:
        self._cache = cache
        self._ttl = ttl

    async def find(self, screening_id: ScreeningId) -> SeatMap | None:
        try:
            value = await self._cache.get(_seat_map_key(screening_id))
        except CacheBackendInteractionError as error:
            _count_seat_map_failure("get", error)
            return None
        return _seat_map_from_payload(value) if isinstance(value, bytes) else None

    async def store(self, seat_map: SeatMap) -> None:
        payload = _seat_map_to_payload(seat_map)
        try:
            await self._cache.set(_seat_map_key(seat_map.screening_id), payload, expire=self._ttl)
        except CacheBackendInteractionError as error:
            _count_seat_map_failure("set", error)

    async def forget(self, screening_id: ScreeningId) -> None:
        try:
            await self._cache.delete(_seat_map_key(screening_id))
        except CacheBackendInteractionError as error:
            _count_seat_map_failure("delete", error)


def _count_seat_map_failure(operation: str, error: CacheBackendInteractionError) -> None:
    error_type = type(error.__cause__).__name__
    _SEAT_MAP_CACHE_FAILURES.add(1, {"operation": operation, "error.type": error_type})
```

## Decorators

**Before decorating a function with `@cache(...)`, `@cache.early`, `@cache.soft` or `@cache.hit`,
or adding a cashews middleware, read [decorators.md](decorators.md)** — when the decorator shape is
worth it, the failure-counting middleware, explicit key templates, `condition=NOT_NONE`, no `None`
TTL, no `jwt` key filter, single-flight without a shield, the shapes that need pickle, `failover`
and `circuit_breaker` options.

## Locks and Invalidation

**Before using `@cache.locked`, `@cache.invalidate`, tags or `client_side=True`, read
[locks-and-invalidation.md](locks-and-invalidation.md)** — a lock that spins, `wait=False`,
invalidation after the function returns, what tags and the client-side cache cost.

## Testing

**Before testing code that uses cashews, read [testing.md](testing.md)** — the adapter against
redis with the production options, why `mem://` proves nothing about serialization, `disabling()`,
and the deprecated `close()` under warnings as errors.

## With Other Libraries

**Before caching with cashews in a FastAPI app, read
[cashews-fastapi.md](../python-integrations/cashews-fastapi.md)** — the cache entered in the
lifespan, no middleware that lets a client clear it, decorators on the service and not the route,
and 429 and 503 for its rate limit and circuit breaker.

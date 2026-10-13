---
name: python-cashews
description: >-
  cashews mechanics behind the application's cache contract: setup in the composition root, safe
  defaults, the adapter, decorator traps, locks, invalidation, tests. Use when code imports
  cashews, calls cache.setup, or decorates a function with @cache, @cache.locked or
  @cache.invalidate.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# cashews

Checked against cashews 7.6 with redis-py 8.1, against redis 8; everything marked *measured* was run
against a real server. What a cache must do whatever the library — the `Cache` contract, keys, TTLs,
the wire format, stampedes, invalidation after commit — is `python-caching`. The redis-py client
underneath is `python-redis`. `import cashews` and write `cashews.Cache`: the application's contract
is also named `Cache`, and the prefix keeps the two apart in the one file that sees both.

## Setup

### The root sets up a `cashews.Cache` of its own, never the package's global `cashews.cache`

**Why:** the README calls `cache.setup(...)` on the global at import time — the settings read on
import that `modules.md` forbids, and one object every test shares. The root builds the instance,
calls `setup()` with the URL from settings, and awaits `close()` on shutdown; `setup()` does not
connect, the first command does.

**Example:**
```python
# WRONG — the package global, configured at import from the environment
cashews.cache.setup(os.environ["CACHE_URL"])


# CORRECT — the root's own instance, set up from settings and closed on the way out
@asynccontextmanager
async def managed_cashews(*, url: str, timeout_seconds: float) -> AsyncIterator[cashews.Cache]:
    cache = cashews.Cache(name="profiles")
    cache.setup(url, **_setup_options(timeout_seconds=timeout_seconds))
    try:
        yield cache
    finally:
        await cache.close()
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

**Example:**
```python
# WRONG — pickle, an ERROR log per failed command, five seconds to give up, ten pooled connections
def _setup_options(*, timeout_seconds: float) -> dict[str, object]:
    return {}


# CORRECT — bytes only, failures raised to the code that counts them, every wait bounded
def _setup_options(*, timeout_seconds: float) -> dict[str, object]:
    return {
        "pickle_type": "null",
        "suppress": False,
        "socket_connect_timeout": timeout_seconds,
        "socket_timeout": timeout_seconds,
        "retry": Retry(NoBackoff(), retries=0),
        "max_connections": _CACHE_MAX_CONNECTIONS,
        "wait_for_connection_timeout": timeout_seconds,
    }
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
two `Profile` classes in two modules collide.

**Example:**
```python
# WRONG — pickled: a renamed class breaks the reader, and a forged entry runs on get
async def store_profile(profile: Profile, *, cache: cashews.Cache) -> None:
    await cache.set(_profile_key(profile.user_id), profile, expire=_PROFILE_TTL)


# CORRECT — the payload's bytes, the shape versioned in the key
async def store_profile(profile: Profile, *, cache: cashews.Cache) -> None:
    payload = _profile_to_payload(profile)
    await cache.set(_profile_key(profile.user_id), payload, expire=_PROFILE_TTL)
```

## The Default Shape: `CashewsCache`

### `CashewsCache` implements the application's `Cache`, one `except` per method

**Why:** an adapter keeps every rule of `python-caching` as written — the key function, the
jittered TTL, the service's shielded single-flight, invalidation after commit, the fake and the
contract suite — and a failure is a counted miss. `get` is typed `Any`; under the null pickler only
`bytes` come back, and anything else is a miss. cashews sends a TTL as milliseconds, so a
sub-second `timedelta` survives — but **a TTL of zero writes a key that never expires** (*measured*:
`ttl` answered `-1`), so a computed TTL never reaches zero. It lives in `cache/cashews.py`, the one
module that imports cashews.

**Example:**
```python
# WRONG — a backend failure raises through every operation into the service
@final
class CashewsCache(Cache):
    def __init__(self, cache: cashews.Cache) -> None:
        self._cache = cache

    @override
    async def get(self, key: str) -> bytes | None:
        value = await self._cache.get(key)
        return value if isinstance(value, bytes) else None

    @override
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None:
        await self._cache.set(key, value, expire=ttl)

    @override
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        return await self._cache.set(key, value, expire=ttl, exist=False)

    @override
    async def delete(self, key: str) -> None:
        await self._cache.delete(key)


# CORRECT — each operation answers as an empty cache would, and the failure is counted
@final
class CashewsCache(Cache):
    def __init__(self, cache: cashews.Cache) -> None:
        self._cache = cache

    @override
    async def get(self, key: str) -> bytes | None:
        try:
            value = await self._cache.get(key)
        except CacheBackendInteractionError as error:
            _count_failure("get", error)
            return None
        return value if isinstance(value, bytes) else None

    @override
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None:
        try:
            await self._cache.set(key, value, expire=ttl)
        except CacheBackendInteractionError as error:
            _count_failure("set", error)

    @override
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        try:
            return await self._cache.set(key, value, expire=ttl, exist=False)
        except CacheBackendInteractionError as error:
            _count_failure("add", error)
            return True

    @override
    async def delete(self, key: str) -> None:
        try:
            await self._cache.delete(key)
        except CacheBackendInteractionError as error:
            _count_failure("delete", error)


def _count_failure(operation: str, error: CacheBackendInteractionError) -> None:
    _CACHE_FAILURES.add(1, {"operation": operation, "error.type": type(error.__cause__).__name__})
```

## Decorators

**Before decorating a function with `@cache(...)`, `@cache.early`, `@cache.soft` or `@cache.hit`,
or adding a cashews middleware, read [decorators.md](decorators.md)** — when the decorator shape is
worth it, the failure-counting middleware, explicit key templates, `condition=NOT_NONE`, no `None`
TTL, no `jwt` key filter, single-flight without a shield, the shapes that need pickle, the
middlewares that let a client clear the cache.

## Locks and Invalidation

**Before using `@cache.locked`, `@cache.invalidate`, tags or `client_side=True`, read
[locks-and-invalidation.md](locks-and-invalidation.md)** — a lock that spins, `wait=False`,
invalidation after the function returns, what tags and the client-side cache cost.

## Testing

**Before testing code that uses cashews, read [testing.md](testing.md)** — the adapter in the
contract suite against redis, why `mem://` proves nothing about serialization, `disabling()`, and
the deprecated `close()` under warnings as errors.

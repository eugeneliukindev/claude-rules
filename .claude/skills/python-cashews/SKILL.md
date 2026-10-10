---
name: python-cashews
description: >-
  cashews mechanics: a Cache instance set up by the composition root rather than the package
  global, pickle_type="null" instead of the default pickle, suppress=False with failures counted,
  connect timeout and pool limits, CashewsCache implementing the application's cache contract as
  the default shape and @cache decorators as the alternative, explicit key templates,
  condition=NOT_NONE, ttl never None, no jwt key filters, protected single-flight and
  cancellation, early/soft/hit needing pickle, @cache.locked spinning, invalidate timing, mem://
  in tests, and the close() deprecation warning. The cache design is in python-caching. Use when
  Python code imports cashews, calls cache.setup, or decorates a function with @cache,
  @cache.locked or @cache.invalidate.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# cashews

Checked against cashews 7.6 with redis-py 8.1, against redis 8; everything marked *measured* was
run against a real server. What a cache must do whatever the library — the `Cache` contract, keys,
TTLs, the wire format, stampedes, invalidation after commit, negative caching — is
`python-caching`. This file is how cashews carries it out, and which of its defaults break it.
The redis-py client underneath is `python-redis`.

## Contents

- Setup in the Composition Root
- Values Are Bytes, Not Pickle
- The Default Shape: `CashewsCache`
- The Alternative Shape: Decorators
- Decorator Traps
- Locks and Invalidation
- Testing

## Setup in the Composition Root

- **Build a `cashews.Cache(name=...)` of your own; never configure the package's `cashews.cache`.**
  The README calls `cache.setup(...)` on that global at import time — the settings read on import
  that `modules.md` forbids, and one object every test shares. The root builds the instance, calls
  `setup()` with the URL from settings, and awaits `close()` on shutdown. `setup()` does not
  connect; the first command does.
- **`import cashews` and write `cashews.Cache`**: the application's own contract is also named
  `Cache`, and the module prefix keeps the two apart in the one file that sees both.
- **Four defaults need overriding, all in the one `setup()` call:**
  - **`pickle_type`** — the redis backend pickles values (next section).
  - **`suppress=True`** turns a redis failure into a miss, which is right, but logs it at `ERROR`
    with a traceback on every command — one line per request while redis is down. Set
    `suppress=False` and count the failure where it is caught: in the adapter, or in a middleware
    for decorators. With it, every redis-py error — a connection, a timeout, a write refused for
    memory — arrives as `CacheBackendInteractionError` with the original as its `__cause__`
    (*measured*).
  - **The connect timeout is redis-py's five seconds** (cashews sets only `socket_timeout=1`).
    *Measured*: with redis unreachable a decorated call — a read, then a write — took ten seconds.
  - **The pool holds ten connections and waits ten seconds for one**: the eleventh concurrent call
    queues behind a cache. Set `max_connections` and `wait_for_connection_timeout`.
- **cashews builds its pool through `from_url`, so redis-py adds no retry underneath**
  (*measured*: one 0.2-second attempt). Pass `retry=` anyway, as `python-redis` asks of every
  client, so the next version's default cannot change it.

```python
# WRONG — pickle, an ERROR log per failed command, five seconds to give up, ten pooled connections
cache.setup(url)

# CORRECT — bytes only, failures raised to the code that counts them, every wait bounded
cache.setup(
    url,
    pickle_type="null",
    suppress=False,
    socket_connect_timeout=timeout_seconds,
    socket_timeout=timeout_seconds,
    retry=Retry(NoBackoff(), retries=0),
    max_connections=_CACHE_MAX_CONNECTIONS,
    wait_for_connection_timeout=timeout_seconds,
)
```

The call sits in an `@asynccontextmanager` that awaits `cache.close()` in `finally`.

## Values Are Bytes, Not Pickle

- **The redis backend pickles by default.** *Measured*: a pickle written to a key with plain
  redis-py ran its code inside `cache.get`. With `pickle_type="null"` nothing is unpickled: `bytes`
  are stored under a `bytes:` tag and come back as `bytes`, and a forged pickle comes back as
  `None`. So the value is the explicit payload `python-caching` asks for.

```python
# WRONG — pickled: a renamed class breaks the reader, and a forged entry runs on get
await self._cache.set(_order_key(order.order_id), order, expire=ttl)

# CORRECT — the payload's bytes, the shape versioned in the key
await self._cache.set(_order_key(order.order_id), _order_to_payload(order), expire=ttl)
```

- **`secret=` is not the fix.** It signs entries (HMAC, `md5` unless `digestmod` says otherwise)
  and rejects a forged one — *measured*, by raising `UnSecureDataError` out of the call rather than
  missing — and the values are still pickles, tied to the class's import path.
- **`pickle_type="json"`** hands back dicts where the function returned objects, and a value json
  cannot encode raises `TypeError` out of the decorated call itself (*measured*), so the cache's
  failure becomes the caller's.
- **`register_type(cls, encoder, decoder)`** works with the null pickler, but the registry is
  process-wide and keyed by the bare class name: two `Order` classes in two modules collide. If it
  is used, the root registers before `setup()`.

## The Default Shape: `CashewsCache`

**An adapter implementing the application's `Cache` contract keeps every rule in `python-caching`
as written** — the key function, the jittered TTL, the service's shielded single-flight,
invalidation after commit, the fake and the contract suite. A cache failure is a counted miss,
never an error (why and how: `python-caching`); here that is one `except` per method:

```python
@final
class CashewsCache(Cache):
    def __init__(self, cache: cashews.Cache) -> None:
        self._cache = cache

    @override
    async def get(self, key: str) -> bytes | None:
        try:
            value = await self._cache.get(key)
        except CacheBackendInteractionError as error:
            _CACHE_FAILURES.add(
                1, {"operation": "get", "error.type": type(error.__cause__).__name__}
            )
            return None
        return value if isinstance(value, bytes) else None

    @override
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None:
        try:
            await self._cache.set(key, value, expire=ttl)
        except CacheBackendInteractionError as error:
            _CACHE_FAILURES.add(
                1, {"operation": "set", "error.type": type(error.__cause__).__name__}
            )

    @override
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        try:
            return await self._cache.set(key, value, expire=ttl, exist=False)
        except CacheBackendInteractionError as error:
            _CACHE_FAILURES.add(
                1, {"operation": "add", "error.type": type(error.__cause__).__name__}
            )
            return True

    @override
    async def delete(self, key: str) -> None:
        try:
            await self._cache.delete(key)
        except CacheBackendInteractionError as error:
            _CACHE_FAILURES.add(
                1, {"operation": "delete", "error.type": type(error.__cause__).__name__}
            )
```

`get` is typed `Any`; under the null pickler only `bytes` come back, and anything else is a miss.
cashews sends a TTL as milliseconds (`PX`), so a sub-second `timedelta` survives — but **a TTL of
zero writes a key that never expires** (*measured*: `ttl` answered `-1`), so a computed TTL is
never allowed to reach zero. It lives in `cache/cashews.py`, the one module that imports cashews.

## The Alternative Shape: Decorators

`@cache(...)` caches a function's result with no adapter and no service code — and with no
contract, no fake, and a single-flight that a cancelled caller breaks (below). Take it for a read
whose result is already a payload and needs nothing the adapter shape gives.

- **Decorators need the `cashews.Cache` at import time**, so it is a module-level
  `cashews.Cache(name=...)` that does nothing until the root calls `setup()` — the standing the
  logger and the meter have in `python-wiring`. Nothing else about it is global: the URL, the
  options and `close()` stay in the root.
- **Failures are counted by a middleware**, passed to the same `setup()` as
  `middlewares=(_count_failures_as_misses,)`. It wraps every command the cache and its decorators
  send, so a failure becomes the miss the contract would promise — `get` answers its `default`,
  anything else `None`. *Measured*: a decorated call against an unreachable host returned the
  function's own result in 0.2 seconds and raised nothing. Its signature is fixed by cashews'
  `Middleware` protocol, which is generic in the result and leaves the arguments untyped — the one
  place `Any` belongs:

```python
async def _count_failures_as_misses[T](
    call: Callable[..., Awaitable[T]],
    cmd: Command,
    backend: Backend,
    *args: Any,
    **kwargs: Any,
) -> T | None:
    try:
        return await call(*args, **kwargs)
    except CacheBackendInteractionError as error:
        _CACHE_FAILURES.add(
            1, {"operation": cmd.value, "error.type": type(error.__cause__).__name__}
        )
        return kwargs.get("default")
```

## Decorator Traps

- **An explicit key template, always**, with the namespace, the payload version and every input
  the value depends on. The default key is the module, the function and every argument rendered
  as text: an injected repository or `self` enters as its `repr`, which holds a memory address, so
  *measured* — two instances of one class never shared an entry. A template's placeholders are
  checked against the parameters when the function is decorated; a parameter missing from the
  template is not.

```python
# WRONG — the key names the page, not the user: one user's orders are served to everyone
@orders_cache(ttl=_RECENT_ORDERS_TTL, key="recent-orders:v1", condition=NOT_NONE)
async def fetch_recent_orders_payload(orders: OrderReader, user_id: UserId) -> bytes: ...

# CORRECT — the user is in the key, the repository is not
@orders_cache(ttl=_RECENT_ORDERS_TTL, key="recent-orders:v1:{user_id}", condition=NOT_NONE)
async def fetch_recent_orders_payload(orders: OrderReader, user_id: UserId) -> bytes: ...
```

- **`condition=NOT_NONE` unless absence is cached on purpose.** The default condition stores every
  result, `None` included (*measured*), which is negative caching nobody decided.

```python
# WRONG — "not found" is cached for ten minutes: an order created a second later stays missing
@orders_cache(ttl=_ORDER_TTL, key="orders:v3:{order_id}")
async def fetch_order_payload(orders: OrderReader, order_id: OrderId) -> bytes | None:
    order = await orders.find(order_id)
    return None if order is None else _order_to_payload(order)

# CORRECT — only a found order is cached
@orders_cache(ttl=_ORDER_TTL, key="orders:v3:{order_id}", condition=NOT_NONE)
async def fetch_order_payload(orders: OrderReader, order_id: OrderId) -> bytes | None:
    order = await orders.find(order_id)
    return None if order is None else _order_to_payload(order)
```

- **`ttl` is never `None`** — cashews accepts it and writes a key with no expiry (*measured*).
- **Never key on `{token:jwt(claim)}`.** The filter decodes the token's payload without checking
  its signature (*measured*: a forged, unsigned token produced the claimed user's key), and the
  hit is served before the function's own authentication runs. Key on the verified principal.
- **`protected=True`, the default, is single-flight without a shield**: *measured*, cancelling the
  first caller — which every deadline `python-async` requires eventually does — cancelled the load
  the second caller was awaiting. Where that matters, take the adapter shape.
- **`@cache.early`, `@cache.soft` and `@cache.hit` store `[datetime, value]`, which needs pickle.**
  Under the null pickler they silently never cache (*measured*: every call ran); under json they
  raise `TypeError`. Spread expiry with the adapter's jittered TTL and the refresh marker from
  `python-caching` instead.
- **`CacheRequestControlMiddleware` and `CacheDeleteMiddleware`** let any client skip or clear the
  cache with a request header (`Cache-Control: no-cache`, `Clear-Site-Data: "cache"`) — each such
  request goes to the source. Leave them out of a FastAPI or Starlette app the public can reach.

## Locks and Invalidation

- **`@cache.locked` waits by spinning, with no deadline**: `check_interval=0` and no blocking
  timeout. *Measured*: one waiter sent 1,647 `SET NX` in half a second. Without `ttl` it raises
  `TypeError` on the first call against redis. And when redis is down the function runs unlocked
  (*measured*) — a lock in a cache saves work and guarantees nothing (why and how:
  `python-caching`).

```python
# WRONG — a second worker spins against redis for as long as the first one runs
@orders_cache.locked(ttl=_REPORT_LOCK_SECONDS, key="nightly-report")
async def build_nightly_report() -> None: ...

# CORRECT — a second worker gets LockedError at once, and its caller skips the run
@orders_cache.locked(ttl=_REPORT_LOCK_SECONDS, key="nightly-report", wait=False)
async def build_nightly_report() -> None: ...
```

- **`@cache.invalidate(template)` deletes after the decorated function returns** (*measured*). So
  it decorates the function whose return means committed — the service method that closes the
  unit of work — never a repository method inside it. A template with `*` scans the keyspace on
  every call.
- **Tags** keep a redis set per tag, written beside every tagged value. **`client_side=True`**
  keeps a bounded in-process copy (10,000 entries) that redis invalidates by broadcast and clears
  when the connection breaks — the one in-process cache that a write reaches in every worker.

## Testing

- **The adapter joins the cache contract's suite** as the `cashews` parameter, with the
  integration marker, against real redis with the production `setup()` options
  (`python-caching`); the unit tests of the service run on the fake.
- **`mem://` stores Python objects without serializing them**, so it caches what redis refuses.
  *Measured*: the same decorated function returning a dataclass ran once on `mem://` and on every
  call on redis with the null pickler. A decorator is proven by one integration test against redis
  with the root's `setup()`, never by `mem://` alone.
- **`cache.disabling()`** switches the cache off in the current context, to test the decorated
  function's own logic; the cache still needs a `setup()`, or the call raises `NotConfiguredError`.
- **`close()` calls redis-py's deprecated `close()`**, so a suite with warnings as errors fails at
  shutdown. Ignore that one message, not the category:
  `filterwarnings = ["error", "ignore:Call to deprecated close:DeprecationWarning"]`.

---
name: python-caching
description: >-
  Cache design in Python services whatever the library — redis, cashews, memcached or an
  in-process cachetools TTLCache: an application Cache contract with a mandatory TTL, cache-aside
  as the default, a cache failure as a counted miss rather than an outage, keys built by one
  function with a namespace, a payload version and the user id, an explicit wire format instead of
  pickle, stampede single-flight and jittered expiry, invalidation after commit, negative caching
  as a decision, a distributed lock as an efficiency lock only, per-process caches, and testing
  with a fake and one contract suite. The library mechanics are python-redis and python-cashews.
  Use when putting a cache in front of a database or an API, choosing a TTL or a cache key,
  invalidating after a write, or building a TTLCache.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Caching

This file is the design, whatever holds the entries. The implementations of the contract below
and their libraries' traps are `python-redis` (`RedisCache`) and `python-cashews`
(`CashewsCache`); cachetools, checked against 7.2, stays here as one section. Timeouts, retries and
serialization in general are `python-boundaries`; memoizing a pure function with `functools.cache`
or `lru_cache` is `python-performance`; where a client is built and closed is `python-wiring`. In
a one-off script a dict that lives as long as the run is the whole cache; a script that writes into
a shared cache is not exempt from anything below, because other processes read what it writes.

## The Contract

The application talks to a `Cache` of its own, named for the capability (`python-contracts`):
bytes by key, every entry expiring. The service owns the keys and the payloads; an implementation
owns only the transport. `RedisCache` and `CashewsCache` implement it, `InMemoryCache` in
`tests/fakes.py` is its fake, and all three pass one contract suite (Testing, below).

```python
class Cache(ABC):
    """Bytes by key, every entry expiring; a cache that cannot answer behaves as an empty one."""

    @abstractmethod
    async def get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None: ...

    @abstractmethod
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        """Set the key only if it is absent, and say whether it was set."""

    @abstractmethod
    async def delete(self, key: str) -> None: ...
```

```
cache/
    base.py       # Cache(ABC)
    redis.py      # RedisCache(Cache) — the only file that imports redis
    cashews.py    # CashewsCache(Cache) — the only file that imports cashews
    __init__.py
```

## Cache-Aside, and a Cache That May Fail

- **Cache-aside is the default**: read the cache; on a miss load from the source and set the
  value; a write goes to the source and deletes the key. Write-behind makes the cache the system of
  record and needs a reason written down.
- **The read path and the invalidation live in the service, beside the unit of work.** A caching
  repository cannot see the commit it must invalidate after (`python-persistence`).
- **The cache is an optimization, so its failure is a miss, never an error.** Every implementation
  catches its library's errors and answers as an empty cache would — `get` a miss, `set` and
  `delete` nothing, `add` "set" — counts the failure, and never raises: the service serves from
  the source. The direction of degradation is "slower, still correct", and the source must carry
  the load a cold or absent cache sends it, which is the same event as a restart.
- **A counter, not a log line per failure** — with the cache down every request fails alike — and
  a hit-and-miss counter beside it is what justifies the cache (`python-observability`).
- **A cache read is not retried**: the source is its retry, and an unreachable cache must answer
  within its own timeout. The contract suite's last test holds every implementation to both.

```python
@final
class OrderLookup:
    def __init__(
        self,
        *,
        unit_of_work: Callable[[], UnitOfWork],
        cache: Cache,
        randomness: random.Random | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._cache = cache
        self._randomness = randomness or random.Random()
        self._loads_in_flight: dict[OrderId, asyncio.Task[Order | None]] = {}

    async def find(self, order_id: OrderId) -> Order | None:
        payload = await self._cache.get(_order_key(order_id))
        if payload is not None:
            return _order_from_payload(payload)
        load = self._loads_in_flight.get(order_id)
        if load is None:
            load = asyncio.create_task(self._load_and_cache(order_id))
            self._loads_in_flight[order_id] = load
            load.add_done_callback(lambda _: self._loads_in_flight.pop(order_id, None))
        return await asyncio.shield(load)
```

## Keys

- **One function builds each kind of key**, used by the read, the write and the invalidation alike.
  Keys spelled at each call site drift apart, and an invalidation then deletes a key nobody reads.

```python
# WRONG — the read and the invalidation spell the key differently, and the delete misses
payload = await self._cache.get(f"order:{order_id}")
await self._cache.delete(f"orders:{order_id}")

# CORRECT — one function, so the two cannot disagree
payload = await self._cache.get(_order_key(order_id))
await self._cache.delete(_order_key(order_id))
```

- **The key carries a namespace and the payload's version**:
  `f"{_ORDER_KEY_NAMESPACE}:v{_ORDER_PAYLOAD_VERSION}:{order_id}"`. A changed payload shape bumps
  the version; the new code never reads an old entry, and the old entries expire on their TTL.
  During a rolling deploy both versions run, each reading its own keys. **This is the carve-out
  from migrate-on-read in `python-boundaries`**: a stored message is migrated, a cache entry never
  is — it is fetched again from the source.
- **Every input the value depends on is a parameter of the key function** — the user, the tenant,
  the locale, the permission set. A value computed for one user under a key without the user's id
  is served to the next user who asks.

```python
# WRONG — the key names the page, not the user: one user's orders are served to everyone
def _recent_orders_key() -> str:
    return f"recent-orders:v{_RECENT_ORDERS_PAYLOAD_VERSION}"

# CORRECT — the user is part of the key, because the value depends on the user
def _recent_orders_key(user_id: UserId) -> str:
    return f"recent-orders:v{_RECENT_ORDERS_PAYLOAD_VERSION}:{user_id}"
```

- **A key built from free text — a search query — hashes it** with `hashlib.sha256`, so its length
  is bounded and its content does not leak into a key listing.

## Every Key Expires

- **The TTL is a required parameter of the contract, so no call can forget it.** It is the
  staleness the readers accept, named, with its reason on the line. Without it a missed
  invalidation is permanent; with it, it is bounded.

```python
# WRONG — the TTL is optional: one call without it serves a stale order until someone flushes
async def set(self, key: str, value: bytes, *, ttl: timedelta | None = None) -> None: ...

# CORRECT — the signature makes every write name how long the readers may see it
async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None: ...
```

```python
_ORDER_TTL: Final = timedelta(minutes=10)  # support agreed to see an order up to ten minutes stale
```

- **The TTL is jittered** where entries are written together — a warm-up, a deploy, a batch — or
  they all expire in the same second and send their misses to the source at once:
  `ttl = _ORDER_TTL * self._randomness.uniform(1 - _TTL_JITTER_FRACTION, 1)`, with the
  `randomness` constructor parameter above defaulting to `random.Random()` — injected like the
  clock (`functions.md`, `python-wiring`), so a test can seed it.
- **An implementation honours the TTL to the millisecond, or says it cannot**: a library that
  truncates to whole seconds turns a sub-second TTL into "no expiry" or an error — the redis and
  cashews cases are in their skills.

## Values Are an Explicit Wire Format

A cache entry outlives the process that wrote it: the next deploy reads it, and so does every other
service pointed at the same cache. It follows the serialization rules in `python-boundaries`,
spelled with `python-orjson`, and the contract takes `bytes` so the service decides the format.
**Never `pickle`**: an entry is then tied to the class's import path and attributes, so a rename
breaks every reader, and whoever can write to the cache runs code in every process that reads it.
A library that pickles by default is configured not to — cashews does (`python-cashews`).

```python
payload = pickle.dumps(order)          # WRONG — a rename breaks the reader; a forged entry runs
payload = _order_to_payload(order)     # CORRECT — named fields, the shape versioned in the key
```

## Stampede

When a hot key expires, every request in flight misses at once and each loads the same value.

- **In one process, single-flight per key**: the first miss starts the load, later misses for the
  same key await that load. `shield` keeps one caller's cancellation from cancelling the load the
  others are waiting on; the dictionary holds the task, so it is never a dropped `create_task`
  (`python-async`), and the done callback removes it, so it does not grow.

```python
# WRONG — fifty concurrent misses for one order are fifty loads from the database
async def find(self, order_id: OrderId) -> Order | None:
    payload = await self._cache.get(_order_key(order_id))
    if payload is not None:
        return _order_from_payload(payload)
    return await self._load_and_cache(order_id)

# CORRECT — the first miss loads; the others for the same order await the same task
async def find(self, order_id: OrderId) -> Order | None:
    payload = await self._cache.get(_order_key(order_id))
    if payload is not None:
        return _order_from_payload(payload)
    load = self._loads_in_flight.get(order_id)
    if load is None:
        load = asyncio.create_task(self._load_and_cache(order_id))
        self._loads_in_flight[order_id] = load
        load.add_done_callback(lambda _: self._loads_in_flight.pop(order_id, None))
    return await asyncio.shield(load)
```

- **Across processes, single-flight still leaves one load per worker.** Jitter the TTL (above), and
  for a key that is both hot and expensive, refresh before it expires: store when the value was
  computed in the payload, and once it is past a fraction of the TTL, the one caller whose
  `add(refresh_key, b"", ttl=...)` answers `True` recomputes while everyone else is served the
  current value. That marker is an efficiency lock — the section after next.

## Invalidation After Commit

- **Delete the key after the transaction commits, never before or inside it.** A reader between
  the delete and the commit misses, reads the old row, and puts it back for a full TTL.

```python
# WRONG — deleted inside the transaction: a concurrent miss re-caches the uncancelled order
async def cancel(self, order_id: OrderId) -> None:
    async with self._unit_of_work() as unit:
        await unit.orders.mark_cancelled(order_id)
        await self._cache.delete(_order_key(order_id))

# CORRECT — deleted once the cancellation is committed
async def cancel(self, order_id: OrderId) -> None:
    async with self._unit_of_work() as unit:
        await unit.orders.mark_cancelled(order_id)
    await self._cache.delete(_order_key(order_id))
```

- **Delete, do not set.** Two writers that each set their own new value can land in either order
  and leave the older one cached; a delete is idempotent, and the next read fills the key from the
  committed state.
- **A narrow race remains** — a read that began before the commit can put the old value after the
  delete — and the TTL is what bounds it. A failed delete is counted like any cache failure; the
  commit stands.

## Negative Caching Is a Decision

Whether "this does not exist" is cached is decided per kind, not left to what a decorator happens
to do. Without it, every request for an id that does not exist reaches the database — and a caller
enumerating ids is a load test. With it, absence is a payload of its own — `null`, which
`_order_from_payload` reads back as `None` — under its own, shorter TTL, and the path that creates
the entity deletes that key after its commit, which the shared key function makes one line.

```python
_ABSENT_ORDER_TTL: Final = timedelta(seconds=30)  # a new order may look missing this long

# WRONG — absence kept as long as an order: one created a second later stays "missing" ten minutes
await self._cache.set(_order_key(order_id), _ABSENT_ORDER_PAYLOAD, ttl=_ORDER_TTL)

# CORRECT — absence lives only as long as a caller may wait for a new order to appear
await self._cache.set(_order_key(order_id), _ABSENT_ORDER_PAYLOAD, ttl=_ABSENT_ORDER_TTL)
```

## A Distributed Lock Saves Work; It Guarantees Nothing

- **A lock held in a cache expires, and must**: one without an expiry is held forever by a holder
  that died. So it also expires under a holder that is still working — a long pause, a slow call —
  and a second process takes it while the first is mid-write. And a cache that cannot answer grants
  it to everyone, as `add` does above.
- So a lock in a cache is for **efficiency**: sparing duplicate work. **Correctness** — exactly one
  invoice, no lost update — comes from the resource itself: a unique constraint, a version column
  (`python-persistence`), an idempotency key (`python-boundaries`), or a fencing token the resource
  checks. The marker is never deleted by its holder, only expired, so a slow holder cannot delete
  the next holder's marker. redis-py's own `lock()` and its traps: `python-redis`.

```python
# WRONG — the check-then-insert is safe only while the marker holds, and it can expire mid-way
async def issue_invoice(self, order_id: OrderId) -> None:
    if not await self._cache.add(_invoice_lock_key(order_id), b"", ttl=_INVOICE_LOCK_TTL):
        return
    async with self._unit_of_work() as unit:
        if not await unit.invoices.exists_for_order(order_id):
            await unit.invoices.add_for_order(order_id)

# CORRECT — the unique constraint on order_id decides; the marker only spares the duplicate work
async def issue_invoice(self, order_id: OrderId) -> None:
    if not await self._cache.add(_invoice_lock_key(order_id), b"", ttl=_INVOICE_LOCK_TTL):
        return
    try:
        async with self._unit_of_work() as unit:
            await unit.invoices.add_for_order(order_id)
    except DuplicateInvoiceError:
        logger.info("invoice already issued", extra={"order_id": str(order_id)})
```

## In-Process Caches

**An in-process cache is per process, per worker**: four workers on three hosts are twelve copies,
and an invalidation reaches one of them. Keep it for data where staleness up to the TTL is
acceptable and no write path needs to invalidate — reference data, feature configuration, a key
set fetched from an identity provider — and bound it on both axes, each a named constant, as state
owned by an object the root builds, never a module-level global. It holds objects, not payloads:
nothing outlives the process, so no wire format is needed.

**cachetools** is the usual one: `TTLCache(maxsize=..., ttl=..., timer=timer)` with
`timer: Callable[[], float] = time.monotonic` injected through the constructor, so a test moves
time instead of sleeping. It is not thread-safe — one event loop needs no lock; threaded code
passes `lock=` to `cached`, or `condition=threading.Condition()`, which also makes threads asking
for a key being computed wait for that computation. **Never `@cached` or `@cachedmethod` on an
`async def`**: it caches the coroutine object, and the second call raises `RuntimeError: cannot
reuse already awaited coroutine`.

```python
# WRONG — the cache holds the coroutine; the second fetch of a currency raises RuntimeError
@cachedmethod(attrgetter("_rate_by_currency"))
async def fetch(self, currency: Currency) -> Decimal:
    return await self._source.fetch(currency)

# CORRECT — the awaited rate is what goes into the cache
async def fetch(self, currency: Currency) -> Decimal:
    rate = self._rate_by_currency.get(currency)
    if rate is None:
        rate = await self._source.fetch(currency)
        self._rate_by_currency[currency] = rate
    return rate
```

## Testing

- **The service's unit tests run on the fake**, which honours the TTL against an injected clock and
  is held to the same suite as every implementation (`python-contracts`, `testing.md`):

```python
@final
class InMemoryCache(Cache):
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._cached_by_key: dict[str, _CachedValue] = {}

    @override
    async def get(self, key: str) -> bytes | None:
        cached = self._cached_by_key.get(key)
        if cached is None or cached.expires_at_seconds <= self._clock():
            return None
        return cached.value

    @override
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None:
        expires_at_seconds = self._clock() + ttl.total_seconds()
        self._cached_by_key[key] = _CachedValue(value=value, expires_at_seconds=expires_at_seconds)

    @override
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        if await self.get(key) is not None:
            return False
        await self.set(key, value, ttl=ttl)
        return True

    @override
    async def delete(self, key: str) -> None:
        self._cached_by_key.pop(key, None)
```

`_CachedValue` is a frozen dataclass of the two fields. The suite runs every test against each
implementation, the real ones with the integration marker against a real server from
testcontainers (`python-pytest`), and holds every real one to failing as a fast miss:

```python
@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("redis", id="redis", marks=pytest.mark.integration),
        pytest.param("cashews", id="cashews", marks=pytest.mark.integration),
    ]
)
def cache(request: pytest.FixtureRequest) -> Cache:
    cache: Cache = request.getfixturevalue(f"{request.param}_cache")
    return cache


async def test_add_sets_only_an_absent_key(cache: Cache) -> None:
    was_added_first = await cache.add(_KEY, _VALUE, ttl=_TTL)
    was_added_second = await cache.add(_KEY, b"other", ttl=_TTL)

    assert (was_added_first, was_added_second) == (True, False)
    assert await cache.get(_KEY) == _VALUE


async def test_unreachable_cache_behaves_as_empty(unreachable_cache: Cache) -> None:
    async with asyncio.timeout(_UNREACHABLE_DEADLINE_SECONDS):
        await unreachable_cache.set(_KEY, _VALUE, ttl=_TTL)
        cached = await unreachable_cache.get(_KEY)
        was_added = await unreachable_cache.add(_KEY, _VALUE, ttl=_TTL)
        await unreachable_cache.delete(_KEY)

    assert cached is None
    assert was_added
```

`unreachable_cache` is parametrized the same way over the real implementations, each built
against an address nothing answers on with the production timeouts. The rest of the suite — a set
value is found, a deleted key is a miss, a value is gone once its TTL has passed (polled under a
deadline, never slept) — has the same shape.

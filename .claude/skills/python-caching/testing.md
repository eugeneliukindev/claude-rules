# Testing a Cache

## Contents

- The service's tests run on a fake that honours the TTL against an injected clock
- One contract suite runs against every implementation
- An unreachable cache answers as an empty one, fast

Real servers for the suite come from testcontainers, configured in `python-pytest`.

### The service's unit tests run on a fake that honours the TTL against an injected clock

**Why:** a fake that never expires passes a service that forgets its TTL, and a test that sleeps
for a TTL is slow and flaky. The fake lives in `tests/fakes.py`, inherits the contract and passes
the same suite as every implementation (`python-contracts`).

**Example:**
```python
# WRONG — entries never expire, so a missing TTL is never noticed
@final
class InMemoryCache(Cache):
    def __init__(self) -> None:
        self._value_by_key: dict[str, bytes] = {}

    @override
    async def get(self, key: str) -> bytes | None:
        return self._value_by_key.get(key)

    @override
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None:
        self._value_by_key[key] = value

    @override
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        return self._value_by_key.setdefault(key, value) is value

    @override
    async def delete(self, key: str) -> None:
        self._value_by_key.pop(key, None)


# CORRECT — every entry expires on the clock the test controls
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class _CachedValue:
    value: bytes
    expires_at_seconds: float


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

### One contract suite runs against the fake and every real implementation

**Why:** an implementation tested only by its own tests passes things the contract forbids, and the
fake drifts from what production does. The fixture parametrizes over every implementation, the real
ones with the integration marker; the tests are written once against `Cache` — a set value is
found, a deleted key is a miss, a value is gone once its TTL has passed (polled under a deadline,
never slept).

**Example:**
```python
# WRONG — the fake has its own tests, and the redis implementation its own
async def test_in_memory_cache_add_sets_only_absent_key() -> None:
    cache = InMemoryCache()

    was_added_first = await cache.add(_KEY, _VALUE, ttl=_TTL)

    assert was_added_first


# CORRECT — one test, every implementation
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
```

### An unreachable cache answers as an empty one, within its timeout

**Why:** the contract promises that a cache which cannot answer behaves as an empty one, and fast:
the source is the fallback, and a slow failure is an outage of its own. Every real implementation
is built against an address nothing answers on, with the production timeouts.

**Example:**
```python
# WRONG — an unreachable cache is not tested, so a raised error or a hang ships
async def test_get_after_set_returns_value(cache: Cache) -> None:
    await cache.set(_KEY, _VALUE, ttl=_TTL)

    cached = await cache.get(_KEY)

    assert cached == _VALUE


# CORRECT — every operation answers within the deadline, as an empty cache would
async def test_unreachable_cache_behaves_as_empty(unreachable_cache: Cache) -> None:
    async with asyncio.timeout(_UNREACHABLE_DEADLINE_SECONDS):
        await unreachable_cache.set(_KEY, _VALUE, ttl=_TTL)
        cached = await unreachable_cache.get(_KEY)
        was_added = await unreachable_cache.add(_KEY, _VALUE, ttl=_TTL)
        await unreachable_cache.delete(_KEY)

    assert cached is None
    assert was_added
```

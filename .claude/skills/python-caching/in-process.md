# In-Process Caches

Checked against cachetools 7.2.

### An in-process cache holds what may be stale for its TTL, bounded, in an object the root builds

**Why:** it is per process, per worker — four workers on three hosts are twelve copies, and an
invalidation reaches one of them. So it holds data where staleness up to the TTL is acceptable and
no write path needs to invalidate — reference data, feature configuration, a key set fetched from
an identity provider — bounded in size and in age, each a named constant, as state of an object
the composition root builds, never a module global. It holds objects, not payloads: nothing
outlives the process, so no wire format is needed. cachetools' `TTLCache` takes an injected
`timer`, so a test moves time instead of sleeping; it is not thread-safe — one event loop needs no
lock, threaded code passes `lock=` to `cached`.

**Example:**
```python
# WRONG — a module global, bounded by nothing, read by the wall clock
_rate_by_currency: dict[Currency, Decimal] = {}


# CORRECT — bounded in size and age, owned by an object the root builds, on an injected timer
@final
class ExchangeRates:
    def __init__(
        self,
        *,
        source: RateSource,
        timer: Callable[[], float] = time.monotonic,
        max_currencies: int = _MAX_CACHED_CURRENCIES,
        rate_ttl_seconds: float = _RATE_TTL_SECONDS,
    ) -> None:
        self._source = source
        self._rate_by_currency: TTLCache[Currency, Decimal] = TTLCache(
            maxsize=max_currencies, ttl=rate_ttl_seconds, timer=timer
        )
```

### cachetools' decorators never go on an `async def`

**Why:** `@cached` and `@cachedmethod` cache what the call returns — for an `async def`, the
coroutine object — and the second call awaits it again and raises `RuntimeError: cannot reuse
already awaited coroutine`. The awaited value is what goes into the cache.

**Example:**
```python
# WRONG — the cache holds the coroutine; the second fetch of a currency raises RuntimeError
@final
class ExchangeRates:
    def __init__(
        self,
        *,
        source: RateSource,
        max_currencies: int = _MAX_CACHED_CURRENCIES,
        rate_ttl_seconds: float = _RATE_TTL_SECONDS,
    ) -> None:
        self._source = source
        self._rate_by_currency: TTLCache[Currency, Decimal] = TTLCache(
            maxsize=max_currencies, ttl=rate_ttl_seconds
        )

    @cachedmethod(attrgetter("_rate_by_currency"))
    async def fetch(self, currency: Currency) -> Decimal:
        return await self._source.fetch(currency)


# CORRECT — the awaited rate is what goes into the cache
@final
class ExchangeRates:
    def __init__(
        self,
        *,
        source: RateSource,
        max_currencies: int = _MAX_CACHED_CURRENCIES,
        rate_ttl_seconds: float = _RATE_TTL_SECONDS,
    ) -> None:
        self._source = source
        self._rate_by_currency: TTLCache[Currency, Decimal] = TTLCache(
            maxsize=max_currencies, ttl=rate_ttl_seconds
        )

    async def fetch(self, currency: Currency) -> Decimal:
        rate = self._rate_by_currency.get(currency)
        if rate is None:
            rate = await self._source.fetch(currency)
            self._rate_by_currency[currency] = rate
        return rate
```

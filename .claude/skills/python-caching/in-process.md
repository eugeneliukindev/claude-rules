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
_inflections_by_headword: dict[Headword, Inflections] = {}


# CORRECT — bounded in size and age, owned by an object the root builds, on an injected timer
@final
class InflectionTables:
    def __init__(
        self,
        *,
        morphology: MorphologyService,
        timer: Callable[[], float] = time.monotonic,
        max_headwords: int = _MAX_CACHED_HEADWORDS,
        inflection_ttl_seconds: float = _INFLECTION_TTL_SECONDS,
    ) -> None:
        self._morphology = morphology
        self._inflections_by_headword: TTLCache[Headword, Inflections] = TTLCache(
            maxsize=max_headwords, ttl=inflection_ttl_seconds, timer=timer
        )
```

### cachetools' decorators never go on an `async def`

**Why:** `@cached` and `@cachedmethod` cache what the call returns — for an `async def`, the
coroutine object — and the second call awaits it again and raises `RuntimeError: cannot reuse
already awaited coroutine`. The awaited value is what goes into the cache.

**Example:**
```python
# WRONG — the cache holds the coroutine; the second lookup of a headword raises RuntimeError
@final
class InflectionTables:
    def __init__(
        self,
        *,
        morphology: MorphologyService,
        max_headwords: int = _MAX_CACHED_HEADWORDS,
        inflection_ttl_seconds: float = _INFLECTION_TTL_SECONDS,
    ) -> None:
        self._morphology = morphology
        self._inflections_by_headword: TTLCache[Headword, Inflections] = TTLCache(
            maxsize=max_headwords, ttl=inflection_ttl_seconds
        )

    @cachedmethod(attrgetter("_inflections_by_headword"))
    async def inflect(self, headword: Headword) -> Inflections:
        return await self._morphology.inflect(headword)


# CORRECT — the awaited inflections are what goes into the cache
@final
class InflectionTables:
    def __init__(
        self,
        *,
        morphology: MorphologyService,
        max_headwords: int = _MAX_CACHED_HEADWORDS,
        inflection_ttl_seconds: float = _INFLECTION_TTL_SECONDS,
    ) -> None:
        self._morphology = morphology
        self._inflections_by_headword: TTLCache[Headword, Inflections] = TTLCache(
            maxsize=max_headwords, ttl=inflection_ttl_seconds
        )

    async def inflect(self, headword: Headword) -> Inflections:
        inflections = self._inflections_by_headword.get(headword)
        if inflections is None:
            inflections = await self._morphology.inflect(headword)
            self._inflections_by_headword[headword] = inflections
        return inflections
```

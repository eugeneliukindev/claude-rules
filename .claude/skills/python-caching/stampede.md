# Stampede

When a hot key expires, every request in flight misses at once and each loads the same value.

### In one process, a miss for a key that is already loading awaits that load

**Why:** fifty concurrent misses for one headword are fifty loads from the database. The first
miss starts the load and later misses await the same task. `shield` keeps one caller's cancellation
from cancelling the load the others wait on; the dictionary holds the task, so it is never dropped,
and the done callback removes it, so the dictionary does not grow.

**Example:**
```python
# WRONG — every concurrent miss for one headword loads it again
@final
class SharedArticleLookup:
    def __init__(self, *, lexicon: Lexicon, cache: Cache, ttl: timedelta = _ARTICLE_TTL) -> None:
        self._lexicon = lexicon
        self._cache = cache
        self._ttl = ttl

    async def find(self, headword: Headword) -> DictionaryArticle | None:
        payload = await self._cache.get(_article_key(headword))
        if payload is not None:
            return _article_from_payload(payload)
        return await self._load_and_cache(headword)

    async def _load_and_cache(self, headword: Headword) -> DictionaryArticle | None:
        article = await self._lexicon.find_article(headword)
        if article is not None:
            payload = _article_to_payload(article)
            await self._cache.set(_article_key(headword), payload, ttl=self._ttl)
        return article


# CORRECT — the first miss loads; the others for the same headword await the same task
@final
class SharedArticleLookup:
    def __init__(self, *, lexicon: Lexicon, cache: Cache, ttl: timedelta = _ARTICLE_TTL) -> None:
        self._lexicon = lexicon
        self._cache = cache
        self._ttl = ttl
        self._loads_in_flight: dict[Headword, asyncio.Task[DictionaryArticle | None]] = {}

    async def find(self, headword: Headword) -> DictionaryArticle | None:
        payload = await self._cache.get(_article_key(headword))
        if payload is not None:
            return _article_from_payload(payload)
        load = self._loads_in_flight.get(headword)
        if load is None:
            load = asyncio.create_task(self._load_and_cache(headword))
            self._loads_in_flight[headword] = load
            load.add_done_callback(lambda _: self._loads_in_flight.pop(headword, None))
        return await asyncio.shield(load)

    async def _load_and_cache(self, headword: Headword) -> DictionaryArticle | None:
        article = await self._lexicon.find_article(headword)
        if article is not None:
            payload = _article_to_payload(article)
            await self._cache.set(_article_key(headword), payload, ttl=self._ttl)
        return article
```

### Across processes, a hot and expensive key is refreshed before it expires, by one caller

**Why:** single-flight still leaves one load per worker, and a jittered TTL only spreads keys that
were written together. For a key both hot and expensive, the payload records when it was computed;
once it is past a fraction of the TTL, the one caller whose `add` on a refresh marker answers `True`
recomputes, while everyone else is served the current value. The marker is an efficiency lock
([locks.md](locks.md)).

**Example:**
```python
# WRONG — the trending list expires everywhere at once, and every worker recomputes it
async def trending_headwords(
    *, cache: Cache, lookups: LookupStatistics, ttl: timedelta = _TRENDING_TTL
) -> TrendingHeadwords:
    payload = await cache.get(_TRENDING_KEY)
    if payload is not None:
        return _trending_from_payload(payload)
    trending = await lookups.rank_trending()
    await cache.set(_TRENDING_KEY, _trending_to_payload(trending), ttl=ttl)
    return trending


# CORRECT — past most of its life, one caller refreshes it; the rest keep reading the old one
async def trending_headwords(
    *,
    cache: Cache,
    lookups: LookupStatistics,
    clock: Clock,
    ttl: timedelta = _TRENDING_TTL,
    refresh_after_fraction: float = _REFRESH_AFTER_FRACTION,
    refresh_marker_ttl: timedelta = _REFRESH_MARKER_TTL,
) -> TrendingHeadwords:
    payload = await cache.get(_TRENDING_KEY)
    if payload is None:
        return await _rank_and_cache(cache=cache, lookups=lookups, clock=clock, ttl=ttl)
    trending = _trending_from_payload(payload)
    is_ageing = clock.now() - trending.computed_at > ttl * refresh_after_fraction
    if is_ageing and await cache.add(_TRENDING_REFRESH_KEY, b"", ttl=refresh_marker_ttl):
        return await _rank_and_cache(cache=cache, lookups=lookups, clock=clock, ttl=ttl)
    return trending
```

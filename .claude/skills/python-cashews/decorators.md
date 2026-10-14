# Decorators

## Contents

- When the decorator shape is worth it, and the cache it needs at import
- Failures counted by a middleware
- An explicit key template, always
- `condition=NOT_NONE`, and `ttl` never `None`
- No `jwt` filter in a key
- `protected=True`, the default, has no shield; `early`, `soft` and `hit` need pickle
- `failover` names its exceptions
- `circuit_breaker` sets `min_calls`

`@cache(...)` caches a function's result with no adapter and no service code — and with no fake,
and a single-flight a cancelled caller breaks. It fits a read whose result is already a payload and
that needs nothing the adapter shape in `SKILL.md` gives.

### Decorators use a module-level `cashews.Cache` the root sets up, with a counting middleware

**Why:** a decorator needs its cache at import time, so the instance is module-level and does
nothing until the root calls `setup()` — the standing the logger has in `modules.md`; the URL, the
options and `close()` stay in the root. A middleware passed to the same `setup()` wraps every
command, so a failure becomes a miss — *measured*: a decorated call against an unreachable host
returned the function's own result in 0.2 seconds. Its signature is fixed by cashews' `Middleware`
protocol, generic in the result and untyped in the arguments — the one place `Any` belongs.

**Example:**
```python
# WRONG — suppress=True: every failed command logs an ERROR traceback, and nothing counts it
showtime_cache = cashews.Cache(name="showtimes")


def setup_showtime_cache(*, url: str) -> None:
    showtime_cache.setup(url, pickle_type="null", suppress=True)


# CORRECT — the failure is counted once, in the middleware, and answered as a miss
showtime_cache = cashews.Cache(name="showtimes")


async def _count_failures_as_misses[T](
    call: Callable[..., Awaitable[T]], cmd: Command, backend: Backend, *args: Any, **kwargs: Any
) -> T | None:
    try:
        return await call(*args, **kwargs)
    except CacheBackendInteractionError as error:
        error_type = type(error.__cause__).__name__
        _SHOWTIME_CACHE_FAILURES.add(1, {"operation": cmd.value, "error.type": error_type})
        return kwargs.get("default")


def setup_showtime_cache(*, url: str) -> None:
    showtime_cache.setup(
        url, pickle_type="null", suppress=False, middlewares=(_count_failures_as_misses,)
    )
```

### Every decorator has an explicit key template with the namespace, the version and every input

**Why:** the default key is the module, the function and every argument rendered as text: an
injected repository or `self` enters as its `repr`, which holds a memory address — *measured*, two
instances of one class never shared an entry. A template's placeholders are checked against the
parameters when the function is decorated; a parameter missing from the template is not.

### `condition=NOT_NONE` unless absence is cached on purpose, and `ttl` is never `None`

**Why:** the default condition stores every result, `None` included (*measured*) — negative caching
nobody decided. A `ttl` of `None` is accepted and writes a key with no expiry (*measured*).

**Example:**
```python
# WRONG — "no such screening" is cached: a screening added a second later stays missing
@showtime_cache(ttl=_SCREENING_TTL, key="screening:v3:{screening_id}")
async def fetch_screening_payload(
    screening_id: ScreeningId, *, programme: ProgrammeReader
) -> bytes | None:
    screening = await programme.find_screening(screening_id)
    return None if screening is None else _screening_to_payload(screening)


# CORRECT — only a found screening is cached
@showtime_cache(ttl=_SCREENING_TTL, key="screening:v3:{screening_id}", condition=NOT_NONE)
async def fetch_screening_payload(
    screening_id: ScreeningId, *, programme: ProgrammeReader
) -> bytes | None:
    screening = await programme.find_screening(screening_id)
    return None if screening is None else _screening_to_payload(screening)
```

### A key never uses `{token:jwt(claim)}`

**Why:** the filter decodes the token's payload without checking its signature — *measured*, a
forged, unsigned token produced the claimed patron's key — and the hit is served before the
function's own authentication runs. The key uses the verified patron.

**Example:**
```python
# WRONG — any client that forges a token reads another patron's cached watchlist
@showtime_cache(ttl=_WATCHLIST_TTL, key="watchlist:v1:{token:jwt(sub)}", condition=NOT_NONE)
async def fetch_watchlist_payload(token: str, *, watchlists: WatchlistReader) -> bytes:
    return _watchlist_to_payload(await watchlists.for_token(token))


# CORRECT — the key is the patron that authentication already verified
@showtime_cache(ttl=_WATCHLIST_TTL, key="watchlist:v1:{patron_id}", condition=NOT_NONE)
async def fetch_watchlist_payload(patron_id: PatronId, *, watchlists: WatchlistReader) -> bytes:
    return _watchlist_to_payload(await watchlists.for_patron(patron_id))
```

### `protected=True`, the default, has no shield; `early`, `soft` and `hit` need pickle

**Why:** `@cache`, `@cache.early` and `@cache.soft` take `protected=True` unless told otherwise
(cashews 7.6). *Measured*, cancelling the first caller — which every deadline eventually does —
cancelled the load the second caller was awaiting; where that matters, the adapter shape with a
shielded single-flight of the application's own is used. `@cache.early`, `@cache.soft` and
`@cache.hit` store `[datetime, value]`, which needs pickle: under the null pickler they silently
never cache (*measured*: every call ran), under json they raise `TypeError`. Expiry is spread with
a jittered TTL and a refresh marker of the application's own instead.

**Example:**
```python
# WRONG — under pickle_type="null" this never caches, and nothing says so
@showtime_cache.early(ttl=_SCREENING_TTL, early_ttl=_SCREENING_EARLY_TTL, key="day:v1:{cinema_id}")
async def fetch_day_programme_payload(cinema_id: CinemaId, *, programme: ProgrammeReader) -> bytes:
    return _day_programme_to_payload(await programme.today_at(cinema_id))


# CORRECT — a plain cached read; spreading expiry is the adapter's job
@showtime_cache(ttl=_SCREENING_TTL, key="day:v1:{cinema_id}", condition=NOT_NONE)
async def fetch_day_programme_payload(cinema_id: CinemaId, *, programme: ProgrammeReader) -> bytes:
    return _day_programme_to_payload(await programme.today_at(cinema_id))
```

### `@cache.failover` names the transient errors it answers with the last good value

**Why:** with no `exceptions`, it catches everything — *measured*, a `KeyError` raised by a bug in
the function came back as the cached value, and the bug never surfaced. Named, only an outage serves
stale data; anything else escapes. It needs one success first: before that, the error escapes too.

**Example:**
```python
# WRONG — every exception, a bug's included, is answered with yesterday's film ratings
@showtime_cache.failover(ttl=_RATINGS_FAILOVER_TTL, key="ratings:v1:{film_id}")
async def fetch_film_ratings(film_id: FilmId, *, ratings: RatingAggregator) -> bytes:
    return _ratings_to_payload(await ratings.for_film(film_id))


# CORRECT — only the aggregator being down serves the last good ratings
@showtime_cache.failover(
    ttl=_RATINGS_FAILOVER_TTL,
    key="ratings:v1:{film_id}",
    exceptions=(RatingAggregatorUnavailableError,),
)
async def fetch_film_ratings(film_id: FilmId, *, ratings: RatingAggregator) -> bytes:
    return _ratings_to_payload(await ratings.for_film(film_id))
```

### `@cache.circuit_breaker` sets `min_calls`, so one failure does not open it

**Why:** `min_calls` defaults to 1, so the error rate is judged on a single call — *measured*, with
`errors_rate=50`, the first `ConnectionError` opened the circuit, and the next calls, which would
have succeeded, got `CircuitBreakerOpen` for the whole `ttl`. `min_calls` makes the rate a rate.
`exceptions` names what counts as a failure, as for `failover`.

**Example:**
```python
# WRONG — the first failed call opens the circuit for everyone, for thirty seconds
@showtime_cache.circuit_breaker(errors_rate=50, period="1m", ttl="30s", key="rating-aggregator")
async def fetch_latest_ratings(film_id: FilmId, *, ratings: RatingAggregator) -> FilmRatings:
    return await ratings.for_film(film_id)


# CORRECT — opened by half of at least twenty calls failing, and only by the aggregator's outage
@showtime_cache.circuit_breaker(
    errors_rate=50,
    period="1m",
    ttl="30s",
    min_calls=_CIRCUIT_MIN_CALLS,
    exceptions=(RatingAggregatorUnavailableError,),
    key="rating-aggregator",
)
async def fetch_latest_ratings(film_id: FilmId, *, ratings: RatingAggregator) -> FilmRatings:
    return await ratings.for_film(film_id)
```

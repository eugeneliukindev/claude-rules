# cashews and FastAPI

The seam between `python-cashews` and `python-fastapi`, linked from both skills.

### The lifespan sets up the app's `cashews.Cache` and closes it in `finally`

**Why:** set up at import, the cache reads its URL on import and is closed by nobody, so its
connections outlive every worker's shutdown. `cashews.Cache` is no context manager: the lifespan
builds the instance beside the other resources, sets it up, builds the services on its adapter, and
awaits `close()` in a `finally` after the last request.

**Example:**
```python
# WRONG — set up when the module is imported, closed by nobody
_SEASON_PASSES: Final = cashews.Cache(name="season-passes")
_SEASON_PASSES.setup(os.environ["CACHE_URL"])


def build_ski_resort_api(*, database_url: str) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with ResortStore.connect(database_url) as resort:
            pass_cache = SeasonPassCache(cache=_SEASON_PASSES)
            yield {"ski_resort": SkiResortService(resort=resort, pass_cache=pass_cache)}

    app = FastAPI(lifespan=lifespan)
    app.include_router(resort_router)
    return app


# CORRECT — set up with the other resources, closed after the last request
def build_ski_resort_api(
    *,
    database_url: str,
    cache_url: str,
    cache_timeout_seconds: float = _CACHE_TIMEOUT_SECONDS,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        season_passes = cashews.Cache(name="season-passes")
        set_up_season_pass_cache(
            season_passes, url=cache_url, timeout_seconds=cache_timeout_seconds
        )
        try:
            async with ResortStore.connect(database_url) as resort:
                pass_cache = SeasonPassCache(cache=season_passes)
                yield {"ski_resort": SkiResortService(resort=resort, pass_cache=pass_cache)}
        finally:
            await season_passes.close()

    app = FastAPI(lifespan=lifespan)
    app.include_router(resort_router)
    return app
```

### The app installs none of cashews' FastAPI middlewares

**Why:** `CacheRequestControlMiddleware` and `CacheDeleteMiddleware` let any client skip or clear
the cache with a request header — `Cache-Control: no-cache`, `Clear-Site-Data: "cache"` — and each
such request goes to the source; a client that sends them on every request turns the cache off.
`CacheEtagMiddleware` defaults to the global `cashews.cache`, which raises `NotConfiguredError`
(*measured*), and given the app's own instance it stores `True` beside each entry, which the null
pickler cannot encode: under `suppress=False` every cached `GET` became a 500 (*measured*, cashews
7.6). An ETag the app needs is computed by its route from the payload.

**Example:**
```python
# WRONG — any client can skip or clear the cache, and the ETags fail every cached read
app.add_middleware(CacheRequestControlMiddleware, cache_instance=season_passes)
app.add_middleware(CacheDeleteMiddleware)
app.add_middleware(CacheEtagMiddleware, cache_instance=season_passes)

# CORRECT — no cashews middleware; invalidation stays with the writes
app.include_router(resort_router)
```

### A cashews decorator goes on the service or the adapter, never on the route

**Why:** a route's arguments are the request's — the caller, the headers, the dependencies — and a
key built from some of them serves one caller's answer to another: a route keyed on the pass id
that also depends on who asks is a data leak. On the service or the adapter, the key is built from
the arguments that decide the value, and the route stays a parse, a call and a response.

**Example:**
```python
# WRONG — keyed on the pass alone: the first caller's view is served to everyone after
@resort_router.get("/season-passes/{pass_id}")
@season_pass_cache(ttl="5m", key="season-pass:v1:{pass_id}", condition=NOT_NONE)
async def read_season_pass(
    pass_id: SeasonPassId, skier: SkierDep, ski_resort: SkiResortDep
) -> SeasonPassResponse:
    season_pass = await ski_resort.get_season_pass(pass_id)
    return SeasonPassResponse.for_viewer(season_pass, viewer=skier)


# CORRECT — the adapter caches the pass; the route builds each viewer's response
@resort_router.get("/season-passes/{pass_id}")
async def read_season_pass(
    pass_id: SeasonPassId, skier: SkierDep, ski_resort: SkiResortDep
) -> SeasonPassResponse:
    season_pass = await ski_resort.get_season_pass(pass_id)
    return SeasonPassResponse.for_viewer(season_pass, viewer=skier)
```

### `RateLimitError` is a 429 and `CircuitBreakerOpen` a 503, each with `Retry-After`

**Why:** unmapped, both escape as a 500, which a client cannot tell from a bug and retries at once.
The exception handlers answer a rate limit with 429 and an open circuit with 503, and `Retry-After`
tells the client when trying again can work — the `ttl` of `@cache.rate_limit` for the one, of
`@cache.circuit_breaker` for the other, each one named constant shared with its decorator.

**Example:**
```python
# WRONG — both reach the client as a 500, and it retries immediately
def add_resort_routes(app: FastAPI) -> None:
    app.include_router(resort_router)


# CORRECT — the status a client acts on, and when to come back
async def _rate_limited_response(
    request: Request, error: Exception, *, retry_after_seconds: int = _SNOW_REPORT_BAN_SECONDS
) -> JSONResponse:
    return JSONResponse(
        {"detail": "too many requests"},
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
        headers={"Retry-After": str(retry_after_seconds)},
    )


async def _circuit_open_response(
    request: Request,
    error: Exception,
    *,
    retry_after_seconds: int = _WEATHER_STATION_CIRCUIT_SECONDS,
) -> JSONResponse:
    return JSONResponse(
        {"detail": "snow reports are unavailable"},
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        headers={"Retry-After": str(retry_after_seconds)},
    )


def add_resort_routes(app: FastAPI) -> None:
    app.add_exception_handler(RateLimitError, _rate_limited_response)
    app.add_exception_handler(CircuitBreakerOpen, _circuit_open_response)
    app.include_router(resort_router)
```

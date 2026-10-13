# cashews and FastAPI

The seam between `python-cashews` and `python-fastapi`, linked from both skills.

### The lifespan enters the cache and closes it when the app stops

**Why:** set up outside the lifespan, the cache is configured at import or never closed, and its
connections outlive every worker's shutdown. Entered in the lifespan beside the other resources, it
closes after the last request, and the services that use it are built inside.

**Example:**
```python
# WRONG — set up when the module is imported, closed by nobody
_CACHE: Final = cashews.Cache(name="catalog")
_CACHE.setup(os.environ["CACHE_URL"])


def create_app() -> FastAPI:
    app = FastAPI()
    app.state.catalog = CatalogService(cache=_CACHE)
    return app


# CORRECT — entered with the other resources, closed after the last request
def create_app(*, cache_url: str, cache_timeout_seconds: float) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_cashews(url=cache_url, timeout_seconds=cache_timeout_seconds) as cache:
            yield {"catalog": CatalogService(cache=CashewsCache(cache))}

    app = FastAPI(lifespan=lifespan)
    app.include_router(catalog_router)
    return app
```

### A public app never installs the middlewares that let a request clear the cache

**Why:** `CacheRequestControlMiddleware` and `CacheDeleteMiddleware` let any client skip or clear
the cache with a request header — `Cache-Control: no-cache`, `Clear-Site-Data: "cache"` — and each
such request goes to the source; a client that sends them on every request turns the cache off.
`CacheEtagMiddleware` answers conditional requests and gives clients no such control.

**Example:**
```python
# WRONG — any client can skip or clear the cache with a header
app.add_middleware(CacheRequestControlMiddleware)
app.add_middleware(CacheDeleteMiddleware)

# CORRECT — the ETags save bandwidth; invalidation stays with the writes
app.add_middleware(CacheEtagMiddleware)
```

### A cashews decorator goes on the service or the adapter, never on the route

**Why:** a route's arguments are the request's — the principal, the headers, the dependencies — and
a key built from some of them serves one caller's answer to another: a route keyed on the account id
that also depends on who asks is a data leak. On the service or the adapter, the key is built from
the arguments that decide the value, and the route stays an adapter (`python-fastapi`).

**Example:**
```python
# WRONG — keyed on the account alone: the first caller's view is served to everyone after
@accounts_router.get("/accounts/{account_id}")
@account_cache(ttl="5m", key="account:v1:{account_id}")
async def read_account(account_id: AccountId, principal: PrincipalDep) -> AccountResponse:
    return AccountResponse.for_viewer(await load_account(account_id), viewer=principal)


# CORRECT — the adapter caches the account; the route builds each viewer's response
@accounts_router.get("/accounts/{account_id}")
async def read_account(
    account_id: AccountId, principal: PrincipalDep, accounts: AccountServiceDep
) -> AccountResponse:
    return AccountResponse.for_viewer(await accounts.get(account_id), viewer=principal)
```

### `RateLimitError` is a 429 and `CircuitBreakerOpen` a 503, each with `Retry-After`

**Why:** unmapped, both escape as a 500, which a client cannot tell from a bug and retries at once.
The exception handler answers a rate limit with 429 and an open circuit with 503, and `Retry-After`
tells the client when trying again can work — the ban's `ttl` for the one, the circuit's for the
other.

**Example:**
```python
# WRONG — both reach the client as a 500, and it retries immediately
app = FastAPI(lifespan=lifespan)
app.include_router(rates_router)


# CORRECT — the status a client acts on, and when to come back
async def _rate_limited_response(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": "too many requests"},
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
        headers={"Retry-After": str(_RATE_LIMIT_BAN_SECONDS)},
    )


async def _circuit_open_response(request: Request, error: Exception) -> JSONResponse:
    return JSONResponse(
        {"detail": "rates are unavailable"},
        status_code=HTTPStatus.SERVICE_UNAVAILABLE,
        headers={"Retry-After": str(_CIRCUIT_OPEN_SECONDS)},
    )


app = FastAPI(lifespan=lifespan)
app.add_exception_handler(RateLimitError, _rate_limited_response)
app.add_exception_handler(CircuitBreakerOpen, _circuit_open_response)
app.include_router(rates_router)
```

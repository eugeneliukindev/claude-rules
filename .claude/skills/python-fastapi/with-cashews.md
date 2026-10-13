# FastAPI With cashews

The cache instance, its setup and its decorators are `python-cashews`.

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
def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_cashews(
            url=settings.cache_url, timeout_seconds=settings.cache_timeout_seconds
        ) as cache:
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

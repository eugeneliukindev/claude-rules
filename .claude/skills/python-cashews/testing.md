# Testing cashews

### The adapter is tested against real redis, set up with the production options

**Why:** only the root's own options — the null pickler, `suppress=False`, the timeouts — show what
production does: that a value comes back as `bytes`, that an outage is a miss within the timeout,
that every written key carries a TTL. The fixture sets up its instance with the same function the
root calls, under the integration marker.

**Example:**
```python
# WRONG — a cache set up with the defaults: pickle, suppressed errors, five-second connects
@pytest.fixture
async def seat_map_cache(redis_url: str) -> AsyncIterator[SeatMapCache]:
    cache = cashews.Cache(name="test")
    cache.setup(redis_url)
    yield SeatMapCache(cache=cache)
    await cache.close()


# CORRECT — the root's own options, so the test runs what production runs
@pytest.fixture
async def seat_map_cache(redis_url: str) -> AsyncIterator[SeatMapCache]:
    cache = cashews.Cache(name="test")
    set_up_seat_map_cache(cache, url=redis_url, timeout_seconds=_TIMEOUT_SECONDS)
    yield SeatMapCache(cache=cache)
    await cache.close()
```

### A decorator is proven against redis, never by `mem://` alone

**Why:** `mem://` stores Python objects without serializing them, so it caches what redis refuses
— *measured*, the same decorated function returning a dataclass ran once on `mem://` and on every
call on redis with the null pickler. `cache.disabling()` switches the cache off in the current
context to test the function's own logic, and still needs a `setup()`, or the call raises
`NotConfiguredError`.

### Warnings stay errors, with the one deprecated `close()` message ignored by name

**Why:** cashews' `close()` calls redis-py's deprecated `close()`, so a suite with warnings as
errors fails at shutdown. Ignoring the whole category would hide every other deprecation.

**Example:**
```toml
# WRONG — every deprecation is silenced to hide one
[tool.pytest]
filterwarnings = ["error", "ignore::DeprecationWarning"]


# CORRECT — only the message cashews causes
[tool.pytest]
filterwarnings = ["error", "ignore:Call to deprecated close:DeprecationWarning"]
```

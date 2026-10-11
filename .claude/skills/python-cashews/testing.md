# Testing cashews

The cache contract suite is in `python-caching`; the service's unit tests run on its fake.

### The adapter joins the contract suite against real redis, with the production `setup()`

**Why:** the suite holds `CashewsCache` to the same promises as every implementation, and only the
root's own options — the null pickler, `suppress=False`, the timeouts — show what production does.
It is the `cashews` parameter of the suite, with the integration marker.

**Example:**
```python
# WRONG — a cache set up with the defaults: pickle, suppressed errors, five-second connects
@pytest.fixture
async def cashews_cache(redis_url: str) -> AsyncIterator[Cache]:
    cache = cashews.Cache(name="test")
    cache.setup(redis_url)
    yield CashewsCache(cache)
    await cache.close()


# CORRECT — the root's own builder, so the suite tests what production runs
@pytest.fixture
async def cashews_cache(redis_url: str) -> AsyncIterator[Cache]:
    async with managed_cashews(url=redis_url, timeout_seconds=_TIMEOUT_SECONDS) as cache:
        yield CashewsCache(cache)
```

### A decorator is proven against redis, never by `mem://` alone

**Why:** `mem://` stores Python objects without serializing them, so it caches what redis refuses
— *measured*, the same decorated function returning a dataclass ran once on `mem://` and on every
call on redis with the null pickler. `cache.disabling()` switches the cache off in the current
context to test the function's own logic, and still needs a `setup()`, or the call raises
`NotConfiguredError`.

**Example:**
```python
# WRONG — passes on mem://, where nothing is serialized, and caches nothing in production
async def test_feed_is_cached(feeds: CountingFeedReader) -> None:
    profile_cache.setup("mem://")

    await fetch_feed_payload(_USER_ID, feeds=feeds)
    await fetch_feed_payload(_USER_ID, feeds=feeds)

    assert feeds.calls == 1


# CORRECT — the root's setup against real redis
@pytest.mark.integration
async def test_feed_is_cached(redis_url: str, feeds: CountingFeedReader) -> None:
    setup_profile_cache(url=redis_url)

    await fetch_feed_payload(_USER_ID, feeds=feeds)
    await fetch_feed_payload(_USER_ID, feeds=feeds)

    assert feeds.calls == 1
```

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

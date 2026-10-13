# Decorators

## Contents

- When the decorator shape is worth it, and the cache it needs at import
- Failures counted by a middleware
- An explicit key template, always
- `condition=NOT_NONE`, and `ttl` never `None`
- No `jwt` filter in a key
- `protected=True` has no shield
- `early`, `soft` and `hit` need pickle

`@cache(...)` caches a function's result with no adapter and no service code — and with no contract,
no fake, and a single-flight a cancelled caller breaks. It fits a read whose result is already a
payload and that needs nothing the adapter shape in `SKILL.md` gives.

### Decorators use a module-level `cashews.Cache` the root sets up, with a counting middleware

**Why:** a decorator needs its cache at import time, so the instance is module-level and does
nothing until the root calls `setup()` — the standing the logger and the meter have in
`python-wiring`; the URL, the options and `close()` stay in the root. A middleware passed to the
same `setup()` wraps every command, so a failure becomes the miss the contract would promise —
*measured*: a decorated call against an unreachable host returned the function's own result in 0.2
seconds. Its signature is fixed by cashews' `Middleware` protocol, generic in the result and
untyped in the arguments — the one place `Any` belongs.

**Example:**
```python
# WRONG — suppress=True: every failed command logs an ERROR traceback, and nothing counts it
profile_cache = cashews.Cache(name="profiles")


def setup_profile_cache(*, url: str) -> None:
    profile_cache.setup(url, pickle_type="null", suppress=True)


# CORRECT — the failure is counted once, in the middleware, and answered as a miss
profile_cache = cashews.Cache(name="profiles")


async def _count_failures_as_misses[T](
    call: Callable[..., Awaitable[T]], cmd: Command, backend: Backend, *args: Any, **kwargs: Any
) -> T | None:
    try:
        return await call(*args, **kwargs)
    except CacheBackendInteractionError as error:
        error_type = type(error.__cause__).__name__
        _CACHE_FAILURES.add(1, {"operation": cmd.value, "error.type": error_type})
        return kwargs.get("default")


def setup_profile_cache(*, url: str) -> None:
    profile_cache.setup(
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
nobody decided (`python-caching`). A `ttl` of `None` is accepted and writes a key with no expiry
(*measured*).

**Example:**
```python
# WRONG — "not found" is cached for ten minutes: a profile created a second later stays missing
@profile_cache(ttl=_PROFILE_TTL, key="profile:v2:{user_id}")
async def fetch_profile_payload(user_id: UserId, *, profiles: ProfileReader) -> bytes | None:
    profile = await profiles.find(user_id)
    return None if profile is None else _profile_to_payload(profile)


# CORRECT — only a found profile is cached
@profile_cache(ttl=_PROFILE_TTL, key="profile:v2:{user_id}", condition=NOT_NONE)
async def fetch_profile_payload(user_id: UserId, *, profiles: ProfileReader) -> bytes | None:
    profile = await profiles.find(user_id)
    return None if profile is None else _profile_to_payload(profile)
```

### A key never uses `{token:jwt(claim)}`

**Why:** the filter decodes the token's payload without checking its signature — *measured*, a
forged, unsigned token produced the claimed user's key — and the hit is served before the
function's own authentication runs. The key uses the verified principal.

**Example:**
```python
# WRONG — any client that forges a token reads another user's cached feed
@profile_cache(ttl=_FEED_TTL, key="feed:v1:{token:jwt(sub)}", condition=NOT_NONE)
async def fetch_feed_payload(token: str, *, feeds: FeedReader) -> bytes:
    return _feed_to_payload(await feeds.latest_for_token(token))


# CORRECT — the key is the principal that authentication already verified
@profile_cache(ttl=_FEED_TTL, key="feed:v1:{user_id}", condition=NOT_NONE)
async def fetch_feed_payload(user_id: UserId, *, feeds: FeedReader) -> bytes:
    return _feed_to_payload(await feeds.latest_for(user_id))
```

### `protected=True` is single-flight without a shield, and `early`, `soft` and `hit` need pickle

**Why:** *measured*, cancelling the first caller — which every deadline eventually does — cancelled
the load the second caller was awaiting; where that matters, the adapter shape with the service's
shielded single-flight is used. `@cache.early`, `@cache.soft` and `@cache.hit` store
`[datetime, value]`, which needs pickle: under the null pickler they silently never cache
(*measured*: every call ran), under json they raise `TypeError`. Expiry is spread with the
adapter's jittered TTL and the refresh marker of `python-caching` instead.

**Example:**
```python
# WRONG — under pickle_type="null" this never caches, and nothing says so
@profile_cache.early(ttl=_FEED_TTL, early_ttl=_FEED_EARLY_TTL, key="feed:v1:{user_id}")
async def fetch_feed_payload(user_id: UserId, *, feeds: FeedReader) -> bytes:
    return _feed_to_payload(await feeds.latest_for(user_id))


# CORRECT — a plain cached read; spreading expiry is the adapter's job
@profile_cache(ttl=_FEED_TTL, key="feed:v1:{user_id}", condition=NOT_NONE)
async def fetch_feed_payload(user_id: UserId, *, feeds: FeedReader) -> bytes:
    return _feed_to_payload(await feeds.latest_for(user_id))
```

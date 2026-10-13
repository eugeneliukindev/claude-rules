---
name: python-caching
description: >-
  Designs a cache in front of a database or an API, whatever the library. Use when code reads or
  writes a cache, picks a TTL or a cache key, invalidates after a write, serves a hot key read by
  many requests at once, or builds a TTLCache. Not for cashews or redis calls (python-cashews,
  python-redis).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Caching

The design, whatever holds the entries. The implementations of the contract and their libraries'
traps are `python-redis` (`RedisCache`) and `python-cashews` (`CashewsCache`); payloads are spelled
with `python-orjson`. Timeouts, retries and serialization in general are `python-boundaries`;
memoizing a pure function with `functools.cache` is `python-performance`; where a client is built
and closed is `python-wiring`. In a one-off script a dict that lives as long as the run is the whole
cache; a script that writes into a shared cache is not exempt, because other processes read what it
writes.

## The Contract

### The service talks to a `Cache` of its own — bytes by key, and every write names its TTL

**Why:** the service owns the keys and the payloads; an implementation owns only the transport,
named for its library in `cache/redis.py` or `cache/cashews.py`, the only file that imports it
(`python-contracts`). The TTL is a required parameter so no call can forget it: without one a
missed invalidation is permanent, with one it is bounded. `InMemoryCache` is the fake, and all
three pass one contract suite ([testing.md](testing.md)).

**Example:**
```python
# WRONG — the TTL is optional: one call without it serves a stale profile until someone flushes
class Cache(ABC):
    @abstractmethod
    async def get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def set(self, key: str, value: bytes, *, ttl: timedelta | None = None) -> None: ...


# CORRECT — every write says how long readers may see it
class Cache(ABC):
    """Bytes by key, every entry expiring; a cache that cannot answer behaves as an empty one."""

    @abstractmethod
    async def get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def set(self, key: str, value: bytes, *, ttl: timedelta) -> None: ...

    @abstractmethod
    async def add(self, key: str, value: bytes, *, ttl: timedelta) -> bool:
        """Set the key only if it is absent, and say whether it was set."""

    @abstractmethod
    async def delete(self, key: str) -> None: ...
```

### Cache-aside is the default, and it lives in the service beside the repository

**Why:** read the cache; on a miss load from the source and set the value; a write goes to the
source and deletes the key. A caching repository cannot see the commit it must invalidate after
(`python-persistence`). Write-behind makes the cache the system of record and needs a reason
written down.

**Example:**
```python
# WRONG — the repository caches, and the service's commit happens where it cannot see it
@final
class CachingProfileRepository(ProfileRepository):
    def __init__(self, *, inner: ProfileRepository, cache: Cache) -> None:
        self._inner = inner
        self._cache = cache

    @override
    async def find(self, user_id: UserId) -> Profile | None:
        payload = await self._cache.get(_profile_key(user_id))
        if payload is not None:
            return _profile_from_payload(payload)
        return await self._inner.find(user_id)


# CORRECT — the service reads through the cache, and invalidates after its own commit
@final
class ProfileLookup:
    def __init__(
        self, *, profiles: ProfileRepository, cache: Cache, ttl: timedelta = _PROFILE_TTL
    ) -> None:
        self._profiles = profiles
        self._cache = cache
        self._ttl = ttl

    async def find(self, user_id: UserId) -> Profile | None:
        payload = await self._cache.get(_profile_key(user_id))
        if payload is not None:
            return _profile_from_payload(payload)
        profile = await self._profiles.find(user_id)
        if profile is not None:
            payload = _profile_to_payload(profile)
            await self._cache.set(_profile_key(user_id), payload, ttl=self._ttl)
        return profile
```

### A cache failure is a counted miss, never an error, and a cache read is never retried

**Why:** the cache is an optimization, so its failure degrades to "slower, still correct": every
implementation catches its library's errors and answers as an empty cache would — `get` a miss,
`set` and `delete` nothing, `add` "set" — counts the failure, and the service serves from the
source, which must carry the load a cold cache sends it. A counter, not a log line per failure —
with the cache down every request fails alike — and a hit-and-miss counter beside it is what
justifies the cache (`python-observability`). The source is a read's retry, so an unreachable cache
answers within its own timeout.

**Example:**
```python
# WRONG — an unreachable cache fails the request that the database could have served
async def _get_or_miss(key: str, *, client: KeyValueClient) -> bytes | None:
    return await client.get(key)


# CORRECT — every method of the implementation goes through this: the failure is counted,
# and the caller sees a miss
async def _get_or_miss(key: str, *, client: KeyValueClient, failures: Counter) -> bytes | None:
    try:
        return await client.get(key)
    except KeyValueClientError:
        failures.add(1, {"operation": "get"})
        return None
```

## Keys

### One function builds each kind of key, with a namespace and the payload's version

**Why:** keys spelled at each call site drift apart, and an invalidation then deletes a key nobody
reads. A changed payload shape bumps the version: the new code never reads an old entry, and the
old ones expire on their TTL, so both versions run side by side during a rolling deploy. This is
the carve-out from migrate-on-read in `python-boundaries` — a stored message is migrated, a cache
entry is fetched again from the source.

### Every input the value depends on is in the key, and a free-form input is hashed

**Why:** a value computed for one user under a key without the user's id is served to the next user
who asks — the same for the tenant, the locale, the permission set. A free-form part — a search
phrase — is hashed with `hashlib.sha256`, so the key stays inside the store's limit and its content
stays out of a key listing: measured on memcached 1.6, a key over 250 bytes is refused, and the
adapter, treating a failure as a miss, then misses on that entry forever without an error.

## Values

### A TTL is named with the staleness it accepts, and jittered where entries are written together

**Why:** the TTL is a decision about how stale readers may see the value, so it is a constant with
its reason on the line. Entries written together — a warm-up, a deploy, a batch — expire in the
same second and send their misses to the source at once unless the TTL is jittered, with the
randomness injected like the clock (`functions.md`) so a test can seed it. An implementation
honours the TTL to the millisecond or says it cannot — the redis and cashews cases are in their
skills.

**Example:**
```python
# WRONG — a bare literal, and every profile warmed at deploy expires in the same second
async def warm_profiles(profiles: Iterable[Profile], *, cache: Cache) -> None:
    for profile in profiles:
        payload = _profile_to_payload(profile)
        await cache.set(_profile_key(profile.user_id), payload, ttl=timedelta(minutes=10))


# CORRECT — the named TTL, spread over its last tenth
_PROFILE_TTL: Final = timedelta(minutes=10)  # support agreed a profile may be ten minutes stale


async def warm_profiles(
    profiles: Iterable[Profile], *, cache: Cache, randomness: random.Random
) -> None:
    for profile in profiles:
        ttl = _PROFILE_TTL * randomness.uniform(1 - _TTL_JITTER_FRACTION, 1)
        await cache.set(_profile_key(profile.user_id), _profile_to_payload(profile), ttl=ttl)
```

### A cache entry is an explicit wire format, never a pickle

**Why:** an entry outlives the process that wrote it — the next deploy reads it, and so does every
other service on the same cache. A pickle ties it to the class's import path and attributes, so a
rename breaks every reader, and whoever can write to the cache runs code in every process that
reads it. The payload follows `python-boundaries`; a library that pickles by default is
configured not to.

## Invalidation

### A write deletes the key after its transaction commits

**Why:** deleted before or inside the transaction, a reader between the delete and the commit
misses, reads the old row, and puts it back for a full TTL. Delete, do not set: two writers that
each set their own value land in either order and can leave the older one; a delete is idempotent.
A narrow race remains — a read that began before the commit can put the old value after the delete
— and the TTL bounds it. A failed delete is counted like any cache failure; the commit stands.

**Example:**
```python
# WRONG — deleted before the write: a concurrent miss re-caches the old name before it changes
@final
class ProfileEditing:
    def __init__(self, *, profiles: ProfileRepository, cache: Cache) -> None:
        self._profiles = profiles
        self._cache = cache

    async def rename(self, user_id: UserId, display_name: str) -> None:
        await self._cache.delete(_profile_key(user_id))
        await self._profiles.set_display_name(user_id, display_name)


# CORRECT — deleted once the new name is committed
@final
class ProfileEditing:
    def __init__(self, *, profiles: ProfileRepository, cache: Cache) -> None:
        self._profiles = profiles
        self._cache = cache

    async def rename(self, user_id: UserId, display_name: str) -> None:
        await self._profiles.set_display_name(user_id, display_name)
        await self._cache.delete(_profile_key(user_id))
```

## Stampede

**Before caching a hot or expensive key — one that many concurrent requests read — read
[stampede.md](stampede.md)** — single-flight per key in one process, refresh ahead across processes.

## Negative Caching

**Before caching the answer "this does not exist", read [negative-caching.md](negative-caching.md)**
— absence as its own payload, its own shorter TTL, deleted when the entity is created.

## A Lock in the Cache

**Before using the cache as a lock — `add` as a marker, redis `lock()`, "only one worker should do
this" — read [locks.md](locks.md)** — an efficiency lock only; correctness from the resource.

## In-Process Caches

**Before building a `TTLCache`, decorating with cachetools' `cached`, or keeping any cache inside
one process, read [in-process.md](in-process.md)** — per process, bounded on both axes, an injected
timer, never on an `async def`.

## Testing

**Before writing a fake cache, the cache contract suite, or a test of a service that caches, read
[testing.md](testing.md)** — the fake against an injected clock, one suite for every implementation,
an unreachable cache that answers as an empty one.

# Locks and Invalidation

A lock in a cache saves work and guarantees nothing; correctness comes from the resource
(`python-caching`).

### `@cache.locked` is given `wait=False`, and a `ttl`

**Why:** it waits by spinning, with no deadline — `check_interval=0` and no blocking timeout;
*measured*, one waiter sent 1,647 `SET NX` in half a second. Without `ttl` it raises `TypeError` on
the first call against redis. And when redis is down the function runs unlocked (*measured*).

**Example:**
```python
# WRONG — a second worker spins against redis for as long as the first one runs
@report_cache.locked(ttl=_REPORT_LOCK_SECONDS, key="nightly-report")
async def build_nightly_report(*, reports: ReportBuilder) -> None:
    await reports.build_nightly()


# CORRECT — a second worker gets LockedError at once, and its caller skips the run
@report_cache.locked(ttl=_REPORT_LOCK_SECONDS, key="nightly-report", wait=False)
async def build_nightly_report(*, reports: ReportBuilder) -> None:
    await reports.build_nightly()
```

### `@cache.invalidate` decorates the method whose return means committed

**Why:** it deletes after the decorated function returns (*measured*), so on a repository method
inside a transaction it deletes before the commit, and a concurrent miss re-caches the old row.
A template with `*` scans the keyspace on every call. Tags keep a redis set per tag, written beside
every tagged value; `client_side=True` keeps a bounded in-process copy — 10,000 entries — that
redis invalidates by broadcast and clears when the connection breaks, the one in-process cache a
write reaches in every worker.

**Example:**
```python
# WRONG — the repository's method returns inside the transaction, so the delete comes first
@final
class ProfileRepository:
    def __init__(self, *, connection: DatabaseConnection) -> None:
        self._connection = connection

    @profile_cache.invalidate("profile:v2:{user_id}")
    async def set_display_name(self, user_id: UserId, display_name: str) -> None:
        await self._connection.execute(_RENAME_PROFILE, user_id, display_name)


# CORRECT — the service method closes the transaction, so its return means committed
@final
class ProfileEditing:
    def __init__(self, *, database: Database, profiles: ProfileRepository) -> None:
        self._database = database
        self._profiles = profiles

    @profile_cache.invalidate("profile:v2:{user_id}")
    async def rename(self, user_id: UserId, display_name: str) -> None:
        async with self._database.transaction():
            await self._profiles.set_display_name(user_id, display_name)
```

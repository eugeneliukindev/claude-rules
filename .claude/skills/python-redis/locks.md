# Locks

`client.lock()` saves duplicate work and guarantees nothing: it expires under a holder that is
still working, so the write it guards is safe without it — idempotent, or held by a unique
constraint or a version column.

### `lock()` is always given `timeout` and `blocking_timeout`

**Why:** both default to `None`. `timeout=None` writes a lock key with no expiry, held forever by a
holder that dies (*measured*: `ttl` answers `-1`); `blocking_timeout=None` waits forever to
acquire. Used as `async with`, a lock not acquired within `blocking_timeout` raises `LockError`. A
holder learns its lock expired only at release, with `LockNotOwnedError`, after its writes
(*measured*: a 0.2-second lock was taken by a second client, and the first one's `release()`
raised).

**Example:**
```python
# WRONG — no expiry and no wait limit: a crashed holder blocks every later recount for good
async def recount_level(level_id: LevelId, *, client: Redis, sensors: BaySensors) -> None:
    async with client.lock(_recount_lock_key(level_id)):
        await sensors.recount(level_id)


# CORRECT — the lock expires, and a caller gives up waiting
async def recount_level(
    level_id: LevelId,
    *,
    client: Redis,
    sensors: BaySensors,
    lock_seconds: float = _RECOUNT_LOCK_SECONDS,
    lock_wait_seconds: float = _RECOUNT_LOCK_WAIT_SECONDS,
) -> None:
    async with client.lock(
        _recount_lock_key(level_id), timeout=lock_seconds, blocking_timeout=lock_wait_seconds
    ):
        await sensors.recount(level_id)
```

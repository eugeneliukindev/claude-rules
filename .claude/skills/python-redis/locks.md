# Locks

`client.lock()` is the same efficiency lock as the cache's `add` marker — it saves work and
guarantees nothing; correctness comes from the resource (`python-caching`).

### `lock()` is always given `timeout` and `blocking_timeout`

**Why:** both default to `None`. `timeout=None` writes a lock key with no expiry, held forever by a
holder that dies (*measured*: `ttl` answers `-1`); `blocking_timeout=None` waits forever to
acquire. Used as `async with`, a lock not acquired within `blocking_timeout` raises `LockError`. A
holder learns its lock expired only at release, with `LockNotOwnedError`, after its writes
(*measured*: a 0.2-second lock was taken by a second client, and the first one's `release()`
raised) — which is why the write itself must be safe without the lock.

**Example:**
```python
# WRONG — no expiry and no wait limit: a crashed holder blocks every later caller for good
async def issue_once(
    enrollment_id: EnrollmentId, *, client: Redis, issuer: CertificateIssuer
) -> None:
    async with client.lock(_certificate_lock_key(enrollment_id)):
        await issuer.issue(enrollment_id)


# CORRECT — the lock expires, and a caller gives up waiting
async def issue_once(
    enrollment_id: EnrollmentId, *, client: Redis, issuer: CertificateIssuer
) -> None:
    async with client.lock(
        _certificate_lock_key(enrollment_id),
        timeout=_CERTIFICATE_LOCK_SECONDS,
        blocking_timeout=_CERTIFICATE_LOCK_WAIT_SECONDS,
    ):
        await issuer.issue(enrollment_id)
```

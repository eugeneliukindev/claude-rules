# A Lock in the Cache

### A lock held in a cache spares duplicate work; the resource itself guarantees correctness

**Why:** a lock in a cache expires, and must — one without an expiry is held forever by a holder
that died. So it also expires under a holder that is still working — a long pause, a slow call —
and a second process takes it while the first is mid-write; and a cache that cannot answer grants it
to everyone, as `add` does. Correctness — exactly one recording per headword, no lost update — comes
from the resource: a unique constraint, a version column, an idempotency key, or a fencing token the
resource checks. The marker is never deleted by its holder, only expired, so a slow holder cannot
delete the next holder's marker.

**Example:**
```python
# WRONG — the check-then-insert is safe only while the marker holds, and it can expire mid-way
async def record_pronunciation(
    headword: Headword,
    *,
    cache: Cache,
    pronunciations: PronunciationStore,
    lock_ttl: timedelta = _PRONUNCIATION_LOCK_TTL,
) -> None:
    if not await cache.add(_pronunciation_lock_key(headword), b"", ttl=lock_ttl):
        return
    if not await pronunciations.exists_for(headword):
        await pronunciations.synthesize_for(headword)


# CORRECT — the unique constraint on the headword decides; the marker only spares the work
async def record_pronunciation(
    headword: Headword,
    *,
    cache: Cache,
    pronunciations: PronunciationStore,
    lock_ttl: timedelta = _PRONUNCIATION_LOCK_TTL,
) -> None:
    if not await cache.add(_pronunciation_lock_key(headword), b"", ttl=lock_ttl):
        return
    try:
        await pronunciations.synthesize_for(headword)
    except DuplicatePronunciationError:
        logger.info("pronunciation already recorded", extra={"headword": headword})
```

# A Lock in the Cache

redis-py's own `lock()` and its traps are in `python-redis`.

### A lock held in a cache spares duplicate work; the resource itself guarantees correctness

**Why:** a lock in a cache expires, and must — one without an expiry is held forever by a holder
that died. So it also expires under a holder that is still working — a long pause, a slow call —
and a second process takes it while the first is mid-write; and a cache that cannot answer grants it
to everyone, as `add` does. Correctness — exactly one certificate, no lost update — comes from the
resource: a unique constraint, a version column (`python-persistence`), an idempotency key
(`python-boundaries`), or a fencing token the resource checks. The marker is never deleted by its
holder, only expired, so a slow holder cannot delete the next holder's marker.

**Example:**
```python
# WRONG — the check-then-insert is safe only while the marker holds, and it can expire mid-way
async def issue_certificate(
    enrollment_id: EnrollmentId, *, cache: Cache, certificates: CertificateRegistry
) -> None:
    if not await cache.add(_certificate_lock_key(enrollment_id), b"", ttl=_CERTIFICATE_LOCK_TTL):
        return
    if not await certificates.exists_for(enrollment_id):
        await certificates.add_for(enrollment_id)


# CORRECT — the unique constraint on enrollment_id decides; the marker only spares the work
async def issue_certificate(
    enrollment_id: EnrollmentId, *, cache: Cache, certificates: CertificateRegistry
) -> None:
    if not await cache.add(_certificate_lock_key(enrollment_id), b"", ttl=_CERTIFICATE_LOCK_TTL):
        return
    try:
        await certificates.add_for(enrollment_id)
    except DuplicateCertificateError:
        logger.info("certificate already issued", extra={"enrollment_id": str(enrollment_id)})
```

# Time

## Contents

- Aware UTC, local time only at the presentation edge
- Offsets required at the boundary; ISO-8601 when stored
- Elapsed time added in UTC; a calendar day is a `date`
- "Now" from an injected `Clock`
- Deadlines on the monotonic clock; durations as `timedelta`

How asyncpg stores a naive `datetime` is in `python-asyncpg`.

### A datetime is timezone-aware UTC; local time exists only at the presentation edge

**Why:** a naive `datetime.now()` shifts with the server's zone and cannot be ordered against an
aware value; `datetime.utcnow()` is naive too, and deprecated. Conversion to local time uses
`zoneinfo.ZoneInfo`, never a hand-written offset. `datetime.now(UTC)` appears in exactly one place:
the system clock.

### A boundary rejects a datetime without an offset, and stores it as ISO-8601

**Why:** `"2026-03-01T09:00:00"` is an instant in no zone at all, and whichever zone the reader
assumes is a guess. A driver may not reject one — one writes a naive `datetime` into
`timestamptz` as the client machine's local time. Stored and serialized, an
instant is `.isoformat()` and `datetime.fromisoformat`; epoch numbers are for machine-to-machine
metrics.

**Example:**
```python
# WRONG — accepts an instant in no zone
def parse_arrival(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


# CORRECT — a value without an offset is refused where it enters
def parse_arrival(raw: str) -> datetime:
    arrived_at = datetime.fromisoformat(raw)
    if arrived_at.tzinfo is None:
        raise NaiveDatetimeError(raw)
    return arrived_at.astimezone(UTC)
```

### Elapsed time is added in UTC; a calendar day is a `date`

**Why:** wall-clock arithmetic on local times is wrong on the nights the clocks change — a token
meant to live a day lives 23 hours or 25. Naive and aware values are never compared or mixed. A
birthday or a due date is a `date`; stored as a midnight `datetime`, it invents a timezone bug.

**Example:**
```python
# WRONG — the lifetime is added on the user's wall clock
def access_expiry(issued_at: datetime, *, user_zone: ZoneInfo) -> datetime:
    return issued_at.astimezone(user_zone) + _ACCESS_LIFETIME


# CORRECT — elapsed time in UTC; the user's zone is for display
def access_expiry(issued_at: datetime) -> datetime:
    return issued_at.astimezone(UTC) + _ACCESS_LIFETIME
```

### "Now" comes from an injected `Clock`

**Why:** code that reads the clock inside cannot be told when it is, so no test can fix the time.
One abstract `now()`, the system clock above in production, a fixed or manual one in tests
(`testing.md`), injected from the composition root (`python-wiring`).

### A deadline or an elapsed time is measured on the monotonic clock

**Why:** NTP steps the wall clock and an operator sets it: a step back stretches the wait, a step
forward ends it early. `time.monotonic()` — `loop.time()` in async code — only moves forward;
`datetime` is for the instants a person or a record reads. A duration is a `timedelta`, and one
stored as a number is an integer of an explicit unit, never a float of ambiguous unit.

**Example:**
```python
# WRONG — the wall clock: a clock step moves the deadline under the running loop
def wait_until_ready(job: ExportJob, *, jobs: ExportJobs) -> bool:
    deadline = datetime.now(UTC) + _READY_BUDGET
    while datetime.now(UTC) < deadline:
        if jobs.status(job.job_id) is ExportJobStatus.DONE:
            return True
        time.sleep(_POLL_INTERVAL_SECONDS)
    return False


# CORRECT — the monotonic clock only moves forward
def wait_until_ready(job: ExportJob, *, jobs: ExportJobs) -> bool:
    deadline_seconds = time.monotonic() + _READY_BUDGET_SECONDS
    while time.monotonic() < deadline_seconds:
        if jobs.status(job.job_id) is ExportJobStatus.DONE:
            return True
        time.sleep(_POLL_INTERVAL_SECONDS)
    return False
```

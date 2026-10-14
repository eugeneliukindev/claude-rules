# Time

How asyncpg stores a naive `datetime` is in `python-asyncpg`.

### A datetime is timezone-aware UTC; local time exists only at the presentation edge

**Why:** a naive `datetime.now()` shifts with the server's zone and cannot be ordered against an
aware value; `datetime.utcnow()` is naive too, and deprecated. Conversion to local time uses
`zoneinfo.ZoneInfo`, never a hand-written offset. `datetime.now(UTC)` appears in exactly one place,
the system clock; everything else asks an injected `Clock` (`testing.md`).

### A boundary rejects a datetime without an offset, and stores it as ISO-8601

**Why:** `"2026-03-01T09:00:00"` is an instant in no zone at all, and whichever zone the reader
assumes is a guess. A driver may not reject one — one writes a naive `datetime` into
`timestamptz` as the client machine's local time. Stored and serialized, an instant is
`.isoformat()` and `datetime.fromisoformat`; epoch numbers are for machine-to-machine metrics.

**Example:**
```python
# WRONG — accepts an instant in no zone
def parse_berthed_at(raw: str) -> datetime:
    return datetime.fromisoformat(raw)


# CORRECT — a value without an offset is refused where it enters
def parse_berthed_at(raw: str) -> datetime:
    berthed_at = datetime.fromisoformat(raw)
    if berthed_at.tzinfo is None:
        raise MissingUtcOffsetError(raw)
    return berthed_at.astimezone(UTC)
```

### Elapsed time is added in UTC; a calendar day is a `date`

**Why:** wall-clock arithmetic on local times is wrong on the nights the clocks change — a crossing
of six hours lands at five or seven. Naive and aware values are never compared or mixed. A
timetable's service day is a `date`; stored as a midnight `datetime`, it invents a timezone bug.

**Example:**
```python
# WRONG — the crossing time is added on the destination's wall clock
def estimated_arrival(departed_at: datetime, *, destination_zone: ZoneInfo) -> datetime:
    return departed_at.astimezone(destination_zone) + _CROSSING_DURATION


# CORRECT — elapsed time in UTC; the destination's zone is for display
def estimated_arrival(departed_at: datetime) -> datetime:
    return departed_at.astimezone(UTC) + _CROSSING_DURATION
```

### A deadline or an elapsed time is measured on the monotonic clock

**Why:** NTP steps the wall clock and an operator sets it: a step back stretches the wait, a step
forward ends it early. `time.monotonic()` — `loop.time()` in async code — only moves forward;
`datetime` is for the instants a person or a record reads. A duration is a `timedelta`, and one
stored as a number is an integer of an explicit unit, never a float of ambiguous unit.

**Example:**
```python
# WRONG — the wall clock: a clock step moves the deadline under the running loop
def wait_until_berth_clear(
    berth_id: BerthId,
    *,
    berths: BerthBoard,
    budget: timedelta = _CLEARANCE_BUDGET,
    poll_seconds: float = _CLEARANCE_POLL_SECONDS,
) -> bool:
    deadline = datetime.now(UTC) + budget
    while datetime.now(UTC) < deadline:
        if berths.status(berth_id) is BerthStatus.CLEAR:
            return True
        time.sleep(poll_seconds)
    return False


# CORRECT — the monotonic clock only moves forward
def wait_until_berth_clear(
    berth_id: BerthId,
    *,
    berths: BerthBoard,
    budget_seconds: float = _CLEARANCE_BUDGET_SECONDS,
    poll_seconds: float = _CLEARANCE_POLL_SECONDS,
) -> bool:
    deadline_seconds = time.monotonic() + budget_seconds
    while time.monotonic() < deadline_seconds:
        if berths.status(berth_id) is BerthStatus.CLEAR:
            return True
        time.sleep(poll_seconds)
    return False
```

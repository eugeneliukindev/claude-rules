# Locks and Invalidation

A lock in a cache saves work and guarantees nothing; correctness comes from the resource — a unique
constraint, a version column.

### `@cache.locked` is given `wait=False`, and a `ttl`

**Why:** it waits by spinning, with no deadline — `check_interval=0` and no blocking timeout;
*measured*, one waiter sent 1,647 `SET NX` in half a second. Without `ttl` it raises `TypeError` on
the first call against redis. And when redis is down the function runs unlocked (*measured*).

**Example:**
```python
# WRONG — a second worker spins against redis for as long as the first one runs
@box_office_cache.locked(ttl=_LAYOUT_IMPORT_LOCK_SECONDS, key="auditorium-layouts")
async def import_auditorium_layouts(*, layouts: LayoutImporter) -> None:
    await layouts.import_all()


# CORRECT — a second worker gets LockedError at once, and its caller skips the run
@box_office_cache.locked(ttl=_LAYOUT_IMPORT_LOCK_SECONDS, key="auditorium-layouts", wait=False)
async def import_auditorium_layouts(*, layouts: LayoutImporter) -> None:
    await layouts.import_all()
```

### `@cache.invalidate` decorates the method whose return means committed

**Why:** it deletes after the decorated function returns (*measured*), so on a repository method
inside a transaction it deletes before the commit, and a concurrent miss re-caches the old seat map.
A template with `*` scans the keyspace on every call. Tags keep a redis set per tag, written beside
every tagged value; `client_side=True` keeps a bounded in-process copy — 10,000 entries — that
redis invalidates by broadcast and clears when the connection breaks, the one in-process cache a
write reaches in every worker.

**Example:**
```python
# WRONG — the repository's method returns inside the transaction, so the delete comes first
@final
class SeatHolds:
    def __init__(self, *, connection: BoxOfficeConnection) -> None:
        self._connection = connection

    @box_office_cache.invalidate("seat-map:v2:{screening_id}")
    async def hold(self, screening_id: ScreeningId, seat_label: str) -> None:
        await self._connection.execute(_HOLD_SEAT, screening_id, seat_label)


# CORRECT — the service method closes the transaction, so its return means committed
@final
class SeatSelection:
    def __init__(self, *, box_office: BoxOfficeDatabase, holds: SeatHolds) -> None:
        self._box_office = box_office
        self._holds = holds

    @box_office_cache.invalidate("seat-map:v2:{screening_id}")
    async def hold(self, screening_id: ScreeningId, seat_label: str) -> None:
        async with self._box_office.transaction():
            await self._holds.hold(screening_id, seat_label)
```

---
name: python-persistence
description: >-
  Designs persistence whatever the ORM: a transaction per use case committed by the service,
  repositories returning domain objects, N+1, keyset pagination, optimistic locking, upserts and
  SKIP LOCKED. Use when deciding where a transaction begins and ends, writing a repository,
  paginating a query, or guarding against lost updates. Not for the ORM's own API
  (python-sqlalchemy).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Persistence

These rules hold for any ORM or query builder. How to spell them in SQLAlchemy is
`python-sqlalchemy`, in raw asyncpg `python-asyncpg`; a DataLoader for GraphQL is
`python-strawberry`; schema changes are `python-migrations`; why a repeated write must be harmless,
and the client's own deadline, are `python-boundaries`; the consumer of an outbox is
`python-workers`.

## Transactions

### One use case is one transaction: the edge opens it, repositories share it, the service commits

**Why:** a repository that commits its own write leaves the first write of a use case committed
when the second fails. The edge that receives the work — a request, a message — opens one
transaction per request or message it receives and closes it in an `async with`, which rolls back
whatever was not committed; the repositories are built on that transaction and never commit; the
service commits as its last step, so the use case decides its boundary and its return means
committed. A transaction kept past the request holds a pooled connection and serves what it read
earlier to the next one. `DatabaseTransaction` is a `Protocol` with `commit` and `rollback`: the
driver's session or connection fits it as it is, and it cannot be made to inherit.

**Example:**
```python
# WRONG — each repository commits its own write: a failed queen update leaves the inspection
@final
class InspectionLog:
    def __init__(self, *, inspections: InspectionRepository, colonies: ColonyRepository) -> None:
        self._inspections = inspections
        self._colonies = colonies

    async def record(self, report: InspectionReport) -> HiveInspectionId:
        inspection_id = await self._inspections.add_and_commit(HiveInspection.from_report(report))
        await self._colonies.set_queen_status_and_commit(report.colony_id, report.queen_status)
        return inspection_id


# CORRECT — both repositories write in the request's transaction, and the service commits it
@final
class InspectionLog:
    def __init__(
        self,
        *,
        inspections: InspectionRepository,
        colonies: ColonyRepository,
        transaction: DatabaseTransaction,
    ) -> None:
        self._inspections = inspections
        self._colonies = colonies
        self._transaction = transaction

    async def record(self, report: InspectionReport) -> HiveInspectionId:
        inspection_id = await self._inspections.add(HiveInspection.from_report(report))
        await self._colonies.set_queen_status(report.colony_id, report.queen_status)
        await self._transaction.commit()
        return inspection_id
```

### Nothing slow or irreversible runs before the commit

**Why:** a slow call holds row locks for its whole duration, and a rollback cannot unsend a message.
Side effects run after the commit; one that must be atomic with the data is an outbox row written in
the same transaction and published separately.

**Example:**
```python
# WRONG — the pager's latency holds row locks, and a rollback cannot unsend the swarm warning
@final
class InspectionLog:
    def __init__(
        self,
        *,
        inspections: InspectionRepository,
        transaction: DatabaseTransaction,
        pager: BeekeeperPager,
    ) -> None:
        self._inspections = inspections
        self._transaction = transaction
        self._pager = pager

    async def record(self, report: InspectionReport) -> HiveInspectionId:
        inspection_id = await self._inspections.add(HiveInspection.from_report(report))
        await self._pager.warn_of_swarm(report.colony_id)
        await self._transaction.commit()
        return inspection_id


# CORRECT — the warning goes after the commit, when the inspection it reports exists
@final
class InspectionLog:
    def __init__(
        self,
        *,
        inspections: InspectionRepository,
        transaction: DatabaseTransaction,
        pager: BeekeeperPager,
    ) -> None:
        self._inspections = inspections
        self._transaction = transaction
        self._pager = pager

    async def record(self, report: InspectionReport) -> HiveInspectionId:
        inspection_id = await self._inspections.add(HiveInspection.from_report(report))
        await self._transaction.commit()
        await self._pager.warn_of_swarm(report.colony_id)
        return inspection_id
```

### A deadlock or serialization failure rolls back and re-runs the whole use case

**Why:** the database has already aborted the transaction, so retrying the statement inside it is
meaningless; the service rolls back and runs the use case again from the start, which is safe only
because side effects run after the commit. This is the one retry above the adapter. A
serialization failure exists only under `REPEATABLE READ` or `SERIALIZABLE` — under the default
`READ COMMITTED` the second of two read-then-update transactions overwrites the first without an
error, and the retry never fires — so the edge opens the transaction of a use case that relies on
it at the stricter level.

**Example:**
```python
# WRONG — the failed statements are retried inside a transaction the database has already aborted
@final
class InspectionLog:
    def __init__(
        self,
        *,
        inspections: InspectionRepository,
        colonies: ColonyRepository,
        transaction: DatabaseTransaction,
        conflict_attempts: int = _CONFLICT_ATTEMPTS,
    ) -> None:
        self._inspections = inspections
        self._colonies = colonies
        self._transaction = transaction
        self._conflict_attempts = conflict_attempts

    async def record(self, report: InspectionReport) -> HiveInspectionId:
        for _ in range(self._conflict_attempts):
            try:
                inspection_id = await self._inspections.add(HiveInspection.from_report(report))
                await self._colonies.set_queen_status(report.colony_id, report.queen_status)
            except SerializationConflictError:
                continue
            await self._transaction.commit()
            return inspection_id
        raise InspectionConflictError(report.colony_id)


# CORRECT — each attempt rolls back, then runs the whole use case and its commit again
@final
class InspectionLog:
    def __init__(
        self,
        *,
        inspections: InspectionRepository,
        colonies: ColonyRepository,
        transaction: DatabaseTransaction,
        conflict_attempts: int = _CONFLICT_ATTEMPTS,
    ) -> None:
        self._inspections = inspections
        self._colonies = colonies
        self._transaction = transaction
        self._conflict_attempts = conflict_attempts

    async def record(self, report: InspectionReport) -> HiveInspectionId:
        for _ in range(self._conflict_attempts):
            try:
                inspection_id = await self._inspections.add(HiveInspection.from_report(report))
                await self._colonies.set_queen_status(report.colony_id, report.queen_status)
                await self._transaction.commit()
            except SerializationConflictError:
                await self._transaction.rollback()
                continue
            return inspection_id
        raise InspectionConflictError(report.colony_id)
```

### Every database connection carries server-side timeouts

**Why:** `statement_timeout` bounds a query, `lock_timeout` a wait for a lock, and
`idle_in_transaction_session_timeout` a transaction the application opened and abandoned, which
otherwise holds its locks until someone kills it. They are set once — on the pool or the database
role — never per query by memory.

## Repositories

### A repository takes and returns domain objects; the ORM row stops at it

**Why:** an ORM row handed to a service carries change tracking — an attribute set "just for this
calculation" is written back at the next flush — and a detached row that lazy-loads after its
transaction closed fails far from the cause. The repository holds query construction only: no
business rules, no commits. A rule computable from loaded data is a pure function over domain
objects that the service loads, calls and saves, so it is tested with plain values and no fake.

**Example:**
```python
# WRONG — the service gets a tracked row: any attribute it sets is written at the next flush
@final
class SqlColonyRepository(ColonyRepository):
    def __init__(self, *, rows: ColonyRows) -> None:
        self._rows = rows

    @override
    async def find(self, colony_id: ColonyId) -> ColonyRow | None:
        return await self._rows.get(colony_id)


# CORRECT — the row stops at the repository; the service gets a frozen Colony
@final
class SqlColonyRepository(ColonyRepository):
    def __init__(self, *, rows: ColonyRows) -> None:
        self._rows = rows

    @override
    async def find(self, colony_id: ColonyId) -> Colony | None:
        row = await self._rows.get(colony_id)
        if row is None:
            return None
        return Colony(
            colony_id=ColonyId(row.id),
            apiary_id=ApiaryId(row.apiary_id),
            queen_status=row.queen_status,
        )
```

### Every relationship is loaded explicitly, and a test pins the statements per use case

**Why:** lazy loading switched off makes an N+1 an error at the first test instead of a page that
quietly runs a hundred queries. It does not catch an explicit query inside a loop — a repository
call per colony is an N+1 the ORM never sees — so an integration test asserts the number of
statements a use case runs, and fails the day it grows.

**Example:**
```python
# WRONG — one query per colony: a hundred colonies are a hundred and one statements
@final
class ApiaryRoster:
    def __init__(self, *, colonies: ColonyRepository, queens: QueenRepository) -> None:
        self._colonies = colonies
        self._queens = queens

    async def queens_of(self, apiary_id: ApiaryId) -> list[Queen]:
        colonies = await self._colonies.in_apiary(apiary_id)
        return [await self._queens.get(colony.queen_id) for colony in colonies]


# CORRECT — one query for the queens of every colony at once
@final
class ApiaryRoster:
    def __init__(self, *, colonies: ColonyRepository, queens: QueenRepository) -> None:
        self._colonies = colonies
        self._queens = queens

    async def queens_of(self, apiary_id: ApiaryId) -> list[Queen]:
        colonies = await self._colonies.in_apiary(apiary_id)
        return await self._queens.get_many([colony.queen_id for colony in colonies])
```

## Idempotent Inserts

**Before inserting a row that a repeat — a redelivery, a retry, a double click — may insert again,
read [upserts.md](upserts.md)** — one `INSERT … ON CONFLICT` on the unique key, `DO NOTHING
RETURNING` to tell a repeat apart.

## A Table Used as a Queue

**Before claiming rows from a table that several workers poll, read
[queue-tables.md](queue-tables.md)** — `FOR UPDATE SKIP LOCKED`.

## Pagination

**Before paginating a query, read [pagination.md](pagination.md)** — keyset from the last key seen,
with a unique tiebreaker and a matching index; offset only for a small bounded list.

## Lost Updates

**Before writing a read-modify-write that spans a user's think time or concurrent requests, read
[optimistic-locking.md](optimistic-locking.md)** — a version column, zero rows updated as a
conflict, re-read instead of retried.

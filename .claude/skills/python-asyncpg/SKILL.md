---
name: python-asyncpg
description: >-
  asyncpg mechanics for PostgreSQL without an ORM: the pool, transactions, Records to domain
  objects, parameters and batching, errors, JSONB codecs, PgBouncer, timeouts. Use when code
  imports asyncpg, creates a pool or connection, or runs raw SQL on PostgreSQL from async code.
  Not for asyncpg under SQLAlchemy (python-sqlalchemy).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# asyncpg

Checked against asyncpg 0.32, asyncpg-stubs 0.32 and PostgreSQL 17. One use case is one transaction
and a repository returns domain objects (`python-persistence`). asyncpg fits async code that talks
only to PostgreSQL and writes its own SQL; psycopg 3 fits sync code, or one API for both. Under
SQLAlchemy the engine owns the pool whatever driver sits below (`python-sqlalchemy`).

## Typing

### `asyncpg-stubs` is a dev dependency, and a repository annotates the pool's connection proxy

**Why:** asyncpg ships no `py.typed`, so `mypy --strict` stops at `import asyncpg`; without stubs
every result is `Any`, and a missing row reaches production as `TypeError: 'NoneType' object is not
subscriptable`. With them `fetchrow` returns `Record | None` and every caller handles the `None`;
the stubs pin the asyncpg minor they describe, so an upgrade of one forces the other. What
`pool.acquire()` yields is a `PoolConnectionProxy` (`asyncpg.pool`), not an `asyncpg.Connection`,
and a column read from a `Record` is `Any` — so one function per type names each column once.

## The Pool

### One pool per database, sized, with a statement limit and verified TLS, entered with `async with`

**Why:** the defaults are `min_size=10`, `max_size=10` and `command_timeout=None` — nothing to do
with the server's `max_connections` divided among the replicas, and no statement limit at all. The
pool is its own async context manager: entering it opens `min_size` connections, so an unreachable
server fails the deploy instead of the first request, and leaving it is `close()`, which waits for
every acquired connection — one leaked connection hangs shutdown, and a cancelled `close()`
terminates the pool. The default `ssl="prefer"` falls back to plaintext and verifies nothing.

**Example:**
```python
# WRONG — ten connections per replica, no statement limit, and TLS that verifies nothing
def tournament_pool(dsn: str) -> asyncpg.Pool:
    return asyncpg.create_pool(dsn)


# CORRECT — the root enters it: `async with tournament_pool(dsn) as pool:`
def tournament_pool(
    dsn: str,
    *,
    max_connections: int = _MAX_CONNECTIONS,
    command_timeout_seconds: float = _COMMAND_TIMEOUT_SECONDS,
) -> asyncpg.Pool:
    return asyncpg.create_pool(
        dsn,
        min_size=1,
        max_size=max_connections,
        command_timeout=command_timeout_seconds,
        ssl="verify-full",
    )
```

### A use case's statements share one connection and one transaction

**Why:** `pool.fetch` and `pool.execute` acquire a connection per statement and give it back, so
statements that must commit together share one connection and its `transaction()`. A
`transaction()` inside another is a `SAVEPOINT` that commits nothing, so repositories never open
one; `transaction(isolation="serializable")` or `readonly=True` is the use case's choice. The
pool's `max_size` is the number of use cases in flight, and `command_timeout` bounds statements,
not the wait for a free connection — `pool.acquire(timeout=...)` or the request's deadline bounds
that.

**Example:**
```python
# WRONG — no transaction: each write commits on its own, and a failed second leaves the first
async def record_result(
    result: GameResult,
    *,
    pool: asyncpg.Pool,
    acquire_timeout_seconds: float = _ACQUIRE_TIMEOUT_SECONDS,
) -> None:
    async with pool.acquire(timeout=acquire_timeout_seconds) as connection:
        await PostgresGameRepository(connection=connection).record(result)
        await PostgresStandingRepository(connection=connection).award(result)


# CORRECT — one connection, one transaction: committed on a clean exit, rolled back on an
# exception or a cancellation, and the connection returned either way
async def record_result(
    result: GameResult,
    *,
    pool: asyncpg.Pool,
    acquire_timeout_seconds: float = _ACQUIRE_TIMEOUT_SECONDS,
) -> None:
    async with (
        pool.acquire(timeout=acquire_timeout_seconds) as connection,
        connection.transaction(),
    ):
        await PostgresGameRepository(connection=connection).record(result)
        await PostgresStandingRepository(connection=connection).award(result)
```

## Records and Parameters

### A `Record` stops at the repository, and a missing row is decided there

**Why:** a `Record` handed outward makes every caller index columns typed `Any`, and `dict(row)`
splatted into a dataclass trusts the column list to match the fields. `fetchrow` returns `None`
for no row: a `find` passes it on, a `get` raises the package's not-found error. What comes back:
`numeric` as `Decimal`, `timestamptz` as an aware UTC `datetime`, `uuid` as asyncpg's own
`uuid.UUID` subclass, `json` and `jsonb` as `str` until a codec says otherwise. What goes in is
checked for type but not meaning: `"42"` for a `bigint` raises `DataError`, while a `float` into
`numeric` and a naive `datetime` into `timestamptz` are accepted.

**Example:**
```python
# WRONG — the Record leaves the repository, and every caller indexes columns typed Any
@final
class PostgresTournamentRepository(TournamentRepository):
    def __init__(self, *, connection: PoolConnectionProxy) -> None:
        self._connection = connection

    @override
    async def find(self, tournament_id: TournamentId) -> asyncpg.Record | None:
        return await self._connection.fetchrow(_SELECT_TOURNAMENT, tournament_id)


# CORRECT — None is handled here, and the service gets a frozen Tournament
@final
class PostgresTournamentRepository(TournamentRepository):
    def __init__(self, *, connection: PoolConnectionProxy) -> None:
        self._connection = connection

    @override
    async def find(self, tournament_id: TournamentId) -> Tournament | None:
        row = await self._connection.fetchrow(_SELECT_TOURNAMENT, tournament_id)
        return None if row is None else _to_tournament(row)


def _to_tournament(row: asyncpg.Record) -> Tournament:
    return Tournament(
        tournament_id=TournamentId(row["id"]), name=row["name"], round_count=row["round_count"]
    )
```

### An `UPDATE` asks with `RETURNING` whether it matched

**Why:** `execute` returns the command tag, and `"UPDATE 0"` is no error to PostgreSQL — an update
of a missing row "succeeds". `RETURNING` with `fetchval` answers `None` when nothing matched, which
the repository raises as not-found; parsing the tag is the brittle alternative.

**Example:**
```python
# WRONG — an UPDATE that matched nothing is silent: postponing a missing round "succeeds"
async def postpone_round(
    round_id: RoundId, starts_at: datetime, *, connection: PoolConnectionProxy
) -> None:
    await connection.execute(_POSTPONE_ROUND, starts_at, round_id)


# CORRECT — no returned id is this package's not-found error
async def postpone_round(
    round_id: RoundId, starts_at: datetime, *, connection: PoolConnectionProxy
) -> None:
    postponed_id = await connection.fetchval(_POSTPONE_ROUND_RETURNING_ID, starts_at, round_id)
    if postponed_id is None:
        raise RoundNotFoundError(round_id)
```

### Parameters are `$1`, `$2`, and a list is one array parameter

**Why:** positional `$n` is the only placeholder asyncpg knows — no `%s`, no `:name`.
`WHERE id = ANY($1)` with a `list` is the fix for an N+1 — one statement whatever the length. The
cast `$1::bigint[]` is optional where a column fixes the type and required where nothing does:
`unnest($1)` without it fails as ambiguous.

**Example:**
```python
# WRONG — one round trip per round: a tournament of eleven rounds is eleven statements
async def pairings_of(
    round_ids: Sequence[RoundId], *, connection: PoolConnectionProxy
) -> list[asyncpg.Record]:
    rows: list[asyncpg.Record] = []
    for round_id in round_ids:
        rows.extend(await connection.fetch(_SELECT_ROUND_PAIRINGS, round_id))
    return rows


# CORRECT — the ids travel as one array parameter, and the tournament is one statement
_SELECT_PAIRINGS_OF_ROUNDS: Final = """
    SELECT round_id, board, white_id, black_id FROM pairings
    WHERE round_id = ANY($1::bigint[])
"""


async def pairings_of(
    round_ids: Sequence[RoundId], *, connection: PoolConnectionProxy
) -> list[asyncpg.Record]:
    return await connection.fetch(_SELECT_PAIRINGS_OF_ROUNDS, list(round_ids))
```

## Bulk Writes

**Before writing many rows at once, read [bulk-writes.md](bulk-writes.md)** —
`copy_records_to_table` for plain rows, `executemany` when each row needs SQL.

- Many plain rows go through `copy_records_to_table`; rows that need SQL, `executemany`

## Errors

**Before catching an asyncpg error or classifying one for a retry, read [errors.md](errors.md)** —
the SQLSTATE class and the constraint name, a rollback that arrives at `COMMIT`, which errors are
transient.

- A database error is caught by its class and its constraint name, never its message
- A rollback raised at `COMMIT` is translated where the transaction closes, not in a repository

## JSON and Other Codecs

**Before reading or writing a `json` or `jsonb` column, or registering a type codec, read
[codecs.md](codecs.md)** — a codec in the pool's `init`, on `pg_catalog`.

- A type codec is registered in the pool's `init`, on `pg_catalog`

## PgBouncer

**Before running behind PgBouncer, read [pgbouncer.md](pgbouncer.md)** — the prepared-statement
cache in transaction mode, `max_prepared_statements` or `statement_cache_size=0`.

- Behind PgBouncer in transaction mode, prepared statements are tracked by PgBouncer or not cached

## Timeouts and Cancellation

**Before setting a timeout on a query, or a deadline around a use case that runs queries, read
[timeouts.md](timeouts.md)** — the three timeouts, what cancellation does to a query and a
transaction, `QueryCanceledError`.

- A client timeout and a cancellation both stop the query on the server
- A server-side `statement_timeout` is set through `server_settings` or the role

## Tests

**Before testing a repository against PostgreSQL, read [testing.md](testing.md)** — testcontainers
with the right URL, a transaction per test rolled back.

- Repositories are tested against a real PostgreSQL, each test inside a transaction rolled back

## With Other Libraries

**Before building a SQLAlchemy engine on `postgresql+asyncpg`, read
[asyncpg-sqlalchemy.md](../python-integrations/asyncpg-sqlalchemy.md)** — the engine's pool instead
of asyncpg's, and the statement timeout through `server_settings`.

- On `postgresql+asyncpg`, the engine owns the pool, and the statement timeout is a server setting

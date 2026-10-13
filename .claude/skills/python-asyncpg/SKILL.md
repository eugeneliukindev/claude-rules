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

Checked against asyncpg 0.32, asyncpg-stubs 0.32 and PostgreSQL 17. One use case is one transaction,
a repository returns domain objects, and an N+1 is an error (`python-persistence`); every value is a
bound parameter (`python-security`); every await has a deadline (`python-async`). asyncpg fits async
code that talks only to PostgreSQL and writes its own SQL; psycopg 3 fits sync code, or one API for
both. Under SQLAlchemy the engine owns the pool whatever driver sits below, and `python-sqlalchemy`
applies instead. A one-off script opens one `asyncpg.connect(..., command_timeout=...)` and closes
it in `finally` (`python-scripts`).

## Typing

### `asyncpg-stubs` is a dev dependency, and a repository annotates the pool's connection proxy

**Why:** asyncpg ships no `py.typed`, so `mypy --strict` stops at `import asyncpg`; without stubs
every result is `Any`, and a missing row reaches production as `TypeError: 'NoneType' object is not
subscriptable`. With them `fetchrow` returns `Record | None` and every caller handles the `None`;
the stubs pin the asyncpg minor they describe, so an upgrade of one forces the other. What
`pool.acquire()` yields is a `PoolConnectionProxy` (`asyncpg.pool`), not an `asyncpg.Connection`,
and a column read from a `Record` is `Any` — so one function per type names each column once.

## The Pool

### One pool per database, sized and bounded from settings, built and closed by the root

**Why:** the defaults are `min_size=10`, `max_size=10` and `command_timeout=None` — nothing to do
with the server's `max_connections` divided among the replicas, and no statement limit at all.
`create_pool` opens `min_size` connections eagerly, so an unreachable server fails the deploy
instead of the first request. `close()` waits for every acquired connection, so one leaked
connection hangs shutdown; under `asyncio.timeout` a cancelled `close()` terminates the pool. TLS
is `ssl="verify-full"` or an `ssl.SSLContext` — the default `prefer` falls back to plaintext and
verifies nothing (`python-security`).

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
# WRONG — each repository acquires its own connection, so each write commits on its own
async def add_track(playlist_id: PlaylistId, track: Track, *, pool: asyncpg.Pool) -> None:
    await PostgresTrackRepository(pool).add(track)
    await PostgresPlaylistRepository(pool).append(playlist_id, track.track_id)


# CORRECT — one connection, one transaction: committed on a clean exit, rolled back on an
# exception or a cancellation, and the connection returned either way
async def add_track(playlist_id: PlaylistId, track: Track, *, pool: asyncpg.Pool) -> None:
    async with (
        pool.acquire(timeout=_ACQUIRE_TIMEOUT_SECONDS) as connection,
        connection.transaction(),
    ):
        await PostgresTrackRepository(connection).add(track)
        await PostgresPlaylistRepository(connection).append(playlist_id, track.track_id)
```

## Records and Parameters

### A `Record` stops at the repository, and a missing row is decided there

**Why:** a `Record` handed outward makes every caller index columns typed `Any`; `dict(row)`
splatted into a dataclass is the splat `python-boundaries` forbids. `fetchrow` returns `None` for no
row: a `find` passes it on, a `get` raises the package's not-found error. What comes back:
`numeric` as `Decimal`, `timestamptz` as an aware UTC `datetime`, `uuid` as asyncpg's own
`uuid.UUID` subclass, `json` and `jsonb` as `str` until a codec says otherwise. What goes in is
checked for type but not meaning: `"42"` for a `bigint` raises `DataError`, while a `float` into
`numeric` and a naive `datetime` into `timestamptz` are accepted.

**Example:**
```python
# WRONG — the Record leaves the repository, and every caller indexes columns typed Any
@final
class PostgresPlaylistRepository(PlaylistRepository):
    def __init__(self, connection: PoolConnectionProxy) -> None:
        self._connection = connection

    @override
    async def find(self, playlist_id: PlaylistId) -> Any:
        return await self._connection.fetchrow(_SELECT_PLAYLIST, playlist_id)


# CORRECT — None is handled here, and the service gets a frozen Playlist
@final
class PostgresPlaylistRepository(PlaylistRepository):
    def __init__(self, connection: PoolConnectionProxy) -> None:
        self._connection = connection

    @override
    async def find(self, playlist_id: PlaylistId) -> Playlist | None:
        row = await self._connection.fetchrow(_SELECT_PLAYLIST, playlist_id)
        return None if row is None else _to_playlist(row)


def _to_playlist(row: asyncpg.Record) -> Playlist:
    return Playlist(
        playlist_id=PlaylistId(row["id"]), title=row["title"], owner_id=UserId(row["owner_id"])
    )
```

### An `UPDATE` asks with `RETURNING` whether it matched

**Why:** `execute` returns the command tag, and `"UPDATE 0"` is no error to PostgreSQL — an update
of a missing row "succeeds". `RETURNING` with `fetchval` answers `None` when nothing matched, which
the repository raises as not-found; parsing the tag is the brittle alternative.

**Example:**
```python
# WRONG — an UPDATE that matched nothing is silent: renaming a missing playlist "succeeds"
async def rename_playlist(
    connection: PoolConnectionProxy, playlist_id: PlaylistId, title: str
) -> None:
    await connection.execute(_RENAME_PLAYLIST, title, playlist_id)


# CORRECT — no returned id is this package's not-found error
async def rename_playlist(
    connection: PoolConnectionProxy, playlist_id: PlaylistId, title: str
) -> None:
    renamed_id = await connection.fetchval(_RENAME_PLAYLIST_RETURNING_ID, title, playlist_id)
    if renamed_id is None:
        raise PlaylistNotFoundError(playlist_id)
```

### Parameters are `$1`, `$2`, and a list is one array parameter

**Why:** positional `$n` is the only placeholder asyncpg knows, and values never enter the SQL text;
a sort column or a table name comes from an allowlist (`python-security`). `WHERE id = ANY($1)`
with a `list` is the fix for an N+1 — one statement whatever the length. The cast `$1::bigint[]` is
optional where a column fixes the type and required where nothing does: `unnest($1)` without it
fails as ambiguous.

**Example:**
```python
# WRONG — one round trip per playlist: a page of fifty playlists is fifty statements
async def tracks_of(
    connection: PoolConnectionProxy, playlist_ids: Sequence[PlaylistId]
) -> list[asyncpg.Record]:
    rows: list[asyncpg.Record] = []
    for playlist_id in playlist_ids:
        rows.extend(await connection.fetch(_SELECT_PLAYLIST_TRACKS, playlist_id))
    return rows


# CORRECT — the ids travel as one array parameter, and the page is one statement
_SELECT_TRACKS_OF_PLAYLISTS: Final = """
    SELECT playlist_id, track_id, position FROM playlist_tracks
    WHERE playlist_id = ANY($1::bigint[])
"""


async def tracks_of(
    connection: PoolConnectionProxy, playlist_ids: Sequence[PlaylistId]
) -> list[asyncpg.Record]:
    return await connection.fetch(_SELECT_TRACKS_OF_PLAYLISTS, list(playlist_ids))
```

## Bulk Writes

**Before writing many rows at once, read [bulk-writes.md](bulk-writes.md)** —
`copy_records_to_table` for plain rows, `executemany` when each row needs SQL.

## Errors

**Before catching an asyncpg error or classifying one for a retry, read [errors.md](errors.md)** —
the SQLSTATE class and the constraint name, a rollback that arrives at `COMMIT`, which errors are
transient.

## JSON and Other Codecs

**Before reading or writing a `json` or `jsonb` column, or registering a type codec, read
[codecs.md](codecs.md)** — a codec in the pool's `init`, on `pg_catalog`.

## PgBouncer

**Before running behind PgBouncer, read [pgbouncer.md](pgbouncer.md)** — the prepared-statement
cache in transaction mode, `max_prepared_statements` or `statement_cache_size=0`.

## Timeouts and Cancellation

**Before setting a timeout on a query, or a deadline around a use case that runs queries, read
[timeouts.md](timeouts.md)** — the three timeouts, what cancellation does to a query and a
transaction, `QueryCanceledError`.

## Tests

**Before testing a repository against PostgreSQL, read [testing.md](testing.md)** — testcontainers
with the right URL, a transaction per test rolled back.

## With Other Libraries

**Before building a SQLAlchemy engine on `postgresql+asyncpg`, read
[asyncpg-sqlalchemy.md](../python-integrations/asyncpg-sqlalchemy.md)** — the engine's pool instead
of asyncpg's, and the statement timeout through `server_settings`.

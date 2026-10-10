---
name: python-asyncpg
description: >-
  asyncpg practice for PostgreSQL without an ORM: one asyncpg pool with explicit min_size,
  max_size and command_timeout owned by the composition root, asyncpg-stubs for mypy,
  pool.acquire() and connection.transaction() per unit of work, Records converted to domain
  objects at the repository and fetchrow's None handled, $1 parameters and = ANY($1) with a list
  instead of N+1, executemany versus copy_records_to_table, asyncpg.exceptions caught by class and
  constraint name, JSONB codecs in the pool's init, PgBouncer and statement_cache_size, per-call
  timeout versus command_timeout versus statement_timeout, and cancellation. Use when Python code
  imports asyncpg, creates an asyncpg pool or connection, or runs raw SQL on PostgreSQL from async
  code.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# asyncpg

Checked against asyncpg 0.32, asyncpg-stubs 0.32 and PostgreSQL 17. One use case is one
transaction, a repository returns domain objects, and an N+1 is an error (why: `python-persistence`);
every value is a bound parameter (why: `python-security`); every await has a deadline (why:
`python-async`). This file is how asyncpg carries them out.

## asyncpg, psycopg or SQLAlchemy

**asyncpg for async code that talks only to PostgreSQL and writes its own SQL.** It is async-only,
speaks PostgreSQL's binary protocol, and prepares every statement. **psycopg 3** is the better fit
when the code is synchronous, when one codebase needs both sync and async access through one API,
or as SQLAlchemy's driver. Under SQLAlchemy the engine owns the pool, whichever driver sits below
it, and `python-sqlalchemy` applies instead of this file. A one-off script opens one
`asyncpg.connect(..., command_timeout=...)` and closes it in `finally`; what still holds there is
in `python-scripts`.

## Typing

- **asyncpg ships no `py.typed`**, so `mypy --strict` stops at `import asyncpg` with
  `import-untyped`. Add **`asyncpg-stubs`** to the dev dependency group: it pins the asyncpg minor
  version it describes, so an upgrade of one forces the other. With the stubs, `fetchrow` returns
  `Record | None`, and the checker makes every caller handle the `None`. Without them every result
  is `Any`, and the `None` reaches production as `TypeError: 'NoneType' object is not
  subscriptable`.
- **What `pool.acquire()` yields is a `PoolConnectionProxy`** (`asyncpg.pool`), which the stubs
  do not type as an `asyncpg.Connection`. A repository built on the unit of work's connection
  annotates the proxy, or `asyncpg.Connection | PoolConnectionProxy` when something also hands it a
  connection from `asyncpg.connect`.
- **A column read from a `Record` is `Any`.** That is why the conversion to a domain object names
  each column once, in one function, and nothing else touches a `Record`.

## The Pool

```python
# WRONG — ten connections whatever the server allows, and no statement ever times out
async def main() -> None:
    settings = Settings()
    async with asyncpg.create_pool(settings.database_url) as pool:
        await serve(pool)

# CORRECT — sized from settings; every statement is bounded unless a call says otherwise
async def main() -> None:
    settings = Settings()
    async with asyncpg.create_pool(
        settings.database_url,
        min_size=settings.database_min_connections,
        max_size=settings.database_max_connections,
        command_timeout=settings.database_command_timeout_seconds,
    ) as pool:
        await serve(pool)
```

- **One pool per database, built by the composition root** (`python-wiring`) or the lifespan
  (`python-fastapi`), passed down, and closed there. The defaults are `min_size=10`,
  `max_size=10` and `command_timeout=None` — none of them has anything to do with the server's
  `max_connections` divided among the replicas, and the last one means no limit at all.
- **The pool connects eagerly**: `create_pool` opens `min_size` connections, so an unreachable
  server fails the deploy instead of the first request. `min_size=0` gives up that check.
- **`close()` waits for every acquired connection to come back**, so one leaked connection hangs
  shutdown. Under a deadline (`asyncio.timeout`) a cancelled `close()` terminates the pool instead.
- **TLS is `ssl="verify-full"` or an `ssl.SSLContext`.** The default, `prefer`, falls back to
  plaintext when TLS fails and verifies no certificate when it succeeds (`python-security`).

## A Connection per Unit of Work

`pool.fetch`, `pool.fetchrow` and `pool.execute` acquire a connection for one statement and give
it back — right for one independent read. Statements that must commit together share a connection
and a transaction, opened by the unit of work:

```python
# WRONG — each repository acquires its own connection, so each write commits on its own
@asynccontextmanager
async def open_unit_of_work(pool: asyncpg.Pool) -> AsyncIterator[UnitOfWork]:
    yield UnitOfWork(orders=PostgresOrderRepository(pool), stock=PostgresStockRepository(pool))

# CORRECT — one connection, one transaction: committed on a clean exit, rolled back on an
# exception or a cancellation, and the connection returned either way
@asynccontextmanager
async def open_unit_of_work(pool: asyncpg.Pool) -> AsyncIterator[UnitOfWork]:
    async with pool.acquire() as connection, connection.transaction():
        yield UnitOfWork(
            orders=PostgresOrderRepository(connection), stock=PostgresStockRepository(connection)
        )
```

- **A `connection.transaction()` inside another is a `SAVEPOINT`.** A repository that opens its own
  commits nothing — the outer transaction decides — so repositories never open one.
- **`transaction(isolation="serializable")`** for a use case that needs it; **`readonly=True`** for
  a read path that needs a consistent snapshot across statements.
- **The pool's `max_size` is the number of use cases in flight.** A connection held across an HTTP
  call or a mail is a slot nobody else can use; that work runs after the transaction
  (`python-persistence`).
- **`command_timeout` bounds statements, not the wait for a free connection.** With the pool
  exhausted, `pool.acquire()` and `pool.fetch()` wait indefinitely. Bound the wait with
  `pool.acquire(timeout=...)` or with the request's deadline (`python-async`).

## Records Stop at the Repository

```python
# WRONG — the Record leaves the repository, and every caller indexes columns typed Any
@override
async def find(self, order_id: OrderId) -> asyncpg.Record | None:
    return await self._connection.fetchrow(_SELECT_ORDER, order_id)

# CORRECT — None is handled here, and the service gets a frozen Order
@override
async def find(self, order_id: OrderId) -> Order | None:
    row = await self._connection.fetchrow(_SELECT_ORDER, order_id)
    if row is None:
        return None
    return _to_order(row)


def _to_order(row: asyncpg.Record) -> Order:
    return Order(order_id=OrderId(row["id"]), status=OrderStatus(row["status"]), total=row["total"])
```

- **`fetchrow` returns `None` for no row**: a `find` passes it on as `Order | None`, a `get` raises
  `OrderNotFoundError` — never a `None` behind a signature that promises an `Order` (`errors.md`).
- **`dict(row)` splatted into a dataclass is the splat `python-boundaries` forbids**: a renamed
  column passes the checker and fails at runtime.
- **What comes back**: `numeric` as `Decimal`, `timestamptz` as an aware UTC `datetime`, `uuid` as
  asyncpg's own `uuid.UUID` subclass, `json` and `jsonb` as `str` until a codec says otherwise.
- **What goes in is checked, but not for meaning.** `"42"` for a `bigint` raises `DataError` —
  asyncpg never coerces text. A `float` into `numeric` is accepted, and so is a naive `datetime`
  into `timestamptz`, read as the client machine's local time. `Decimal` money and aware datetimes
  are the caller's job (`python-boundaries`).
- **`execute` returns the command tag** — `"UPDATE 0"` for a statement that matched nothing, which
  PostgreSQL does not treat as an error. Ask with `RETURNING` instead of parsing the tag:

```python
# WRONG — an UPDATE that matched nothing is no error to PostgreSQL: a missing order "succeeds"
@override
async def set_status(self, order_id: OrderId, status: OrderStatus) -> None:
    await self._connection.execute(_UPDATE_STATUS, status, order_id)

# CORRECT — RETURNING says whether a row matched; no row is this package's not-found error
@override
async def set_status(self, order_id: OrderId, status: OrderStatus) -> None:
    updated_id = await self._connection.fetchval(_UPDATE_STATUS_RETURNING_ID, status, order_id)
    if updated_id is None:
        raise OrderNotFoundError(order_id)
```

## Parameters

- **`$1`, `$2` — positional, and the only placeholder asyncpg knows.** Values never enter the SQL
  text; a sort column or a table name is chosen from an allowlist of constants (`python-security`).
- **A list is one parameter**: `WHERE id = ANY($1::bigint[])` with a `list` or `tuple`. That is
  the fix for N+1, and one statement whatever the length. The cast is optional where a column fixes
  the type and required where nothing does — `unnest($1)` without it fails as ambiguous.

```python
# WRONG — one round trip per order: a page of fifty orders is fifty statements
rows = [await self._connection.fetch(_SELECT_ORDER_LINES, order_id) for order_id in order_ids]

# CORRECT — the ids travel as one array parameter, and the page is one statement
_SELECT_LINES_OF_ORDERS: Final = """
    SELECT order_id, sku, quantity FROM order_lines WHERE order_id = ANY($1::bigint[])
"""

rows = await self._connection.fetch(_SELECT_LINES_OF_ORDERS, order_ids)
```

## Bulk Writes

- **`copy_records_to_table` for thousands of plain rows** — `COPY`, far faster than inserts,
  inside the unit of work's transaction when it must be all or nothing. It cannot upsert or return
  rows; asyncpg quotes the table and column names itself.
- **`executemany` when each row needs SQL** — `ON CONFLICT`, an expression, a lookup. One prepared
  statement, the rows pipelined, and atomic since 0.22: a failing row leaves none of the others.

```python
# WRONG — one round trip per line: ten thousand lines are ten thousand statements
for line in lines:
    await connection.execute(_INSERT_ORDER_LINE, line.order_id, line.sku, line.quantity)

# CORRECT — one COPY streams every line
await connection.copy_records_to_table(
    "order_lines",
    records=[(line.order_id, line.sku, line.quantity) for line in lines],
    columns=_ORDER_LINE_COLUMNS,
)
```

## Errors

**Every SQLSTATE is a class** in `asyncpg.exceptions`, re-exported as `asyncpg.UniqueViolationError`
and the like, carrying `sqlstate`, `constraint_name`, `table_name` and `detail`. The repository
translates them into its package's errors with `raise … from`:

```python
# WRONG — the message is for people: lc_messages translates it, and new versions reword it
@override
async def add(self, email: str) -> None:
    try:
        await self._connection.execute(_INSERT_USER, email)
    except asyncpg.PostgresError as error:
        if "duplicate key" in str(error):
            raise EmailTakenError(email) from error
        raise

# CORRECT — the class is the SQLSTATE, and the constraint says which unique key it was
@override
async def add(self, email: str) -> None:
    try:
        await self._connection.execute(_INSERT_USER, email)
    except asyncpg.UniqueViolationError as error:
        if error.constraint_name == _USERS_EMAIL_KEY:
            raise EmailTakenError(email) from error
        raise
```

- **A serialization failure or a deadlock** — `SerializationError`, `DeadlockDetectedError`, both
  `asyncpg.TransactionRollbackError` — can arrive at `COMMIT`, which is the unit of work's exit,
  not a repository call. So the unit of work translates it into the transient conflict that retries
  the whole use case (`python-persistence`):

```python
@asynccontextmanager
async def open_unit_of_work(pool: asyncpg.Pool) -> AsyncIterator[UnitOfWork]:
    try:
        async with pool.acquire() as connection, connection.transaction(isolation="serializable"):
            yield UnitOfWork(
                orders=PostgresOrderRepository(connection),
                stock=PostgresStockRepository(connection),
            )
    except asyncpg.TransactionRollbackError as error:
        raise ConcurrentUpdateError(
            f"Transaction rolled back by a concurrent one: SQLSTATE {error.sqlstate}"
        ) from error
```

- **Transient for the retry policy** (`python-boundaries`): `TimeoutError`, `OSError` from the
  connect, `asyncpg.PostgresConnectionError`, `asyncpg.TooManyConnectionsError`. Integrity
  violations and `DataError` are permanent.

## JSON and Other Codecs

`json` and `jsonb` arrive as `str`, and a `dict` passed for one raises `DataError`. A codec
converts both ways, and it is registered per connection — so in the pool's `init`, which runs on
every connection the pool opens, replacements included. The types live in `pg_catalog`; the
default `schema="public"` fails with `unknown type: public.jsonb`.

```python
async def _register_json_codecs(connection: asyncpg.Connection) -> None:
    await connection.set_type_codec(
        "jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads
    )

# WRONG — registered on one connection at startup: the others still return jsonb as str
async with pool.acquire() as connection:
    await _register_json_codecs(connection)

# CORRECT — every connection the pool opens is initialised the same way
async with asyncpg.create_pool(
    settings.database_url,
    min_size=settings.database_min_connections,
    max_size=settings.database_max_connections,
    command_timeout=settings.database_command_timeout_seconds,
    init=_register_json_codecs,
) as pool:
    await serve(pool)
```

The default codec is text, so the encoder returns `str`; `orjson.dumps` needs `.decode()` here,
one of the places `python-orjson` says it is genuinely required. `setup=` is the hook for every
acquire, not for codecs.

## PgBouncer and the Statement Cache

asyncpg prepares every statement as a named, protocol-level prepared statement and keeps up to
`statement_cache_size=100` of them per connection. **Behind PgBouncer in transaction mode** the
next transaction may run on another server connection, where the statement does not exist:
`InvalidSQLStatementNameError` or `DuplicatePreparedStatementError`, under load only — never in
development, where there is no PgBouncer. Two fixes, in order of preference:

- **PgBouncer 1.21+ with `max_prepared_statements` above zero** (the default from 1.24): PgBouncer
  tracks protocol-level prepares and re-prepares them where needed, and the cache keeps working.
- **`statement_cache_size=0`** on the pool otherwise. The cost: every call parses and plans its
  statement again, and pays an extra round trip to prepare it.

A session-level `SET`, `LISTEN` and an advisory lock do not survive between transactions there
either. For a single application server, asyncpg's own pool does PgBouncer's job.

## Timeouts and Cancellation

| | bounds | set |
|---|---|---|
| `timeout=` on a call | that call | a named constant, where one statement is known to be slow |
| `command_timeout` | every statement on the pool's connections | `create_pool`, from settings |
| `statement_timeout` | the query on the server, whatever the client does | `server_settings=` or the role |

- **A client timeout raises the builtin `TimeoutError`** and asyncpg sends PostgreSQL a cancel
  request, so the query stops on the server too. `timeout=None` on a call means "use
  `command_timeout`", not "no limit".
- **Task cancellation does the same**: a cancelled `await` cancels the query, and inside
  `connection.transaction()` the transaction rolls back. An `asyncio.timeout` around a use case is
  therefore safe; never shield a query, and never swallow the `CancelledError` (`python-async`).
- **A server `statement_timeout` arrives as `asyncpg.QueryCanceledError`** (`57014`), not as
  `TimeoutError`; the adapter classifies both as transient.
- **`server_settings={"statement_timeout": ...}` survives the pool's `RESET ALL`** on release; a
  `SET` on an acquired connection does not, and `SET LOCAL` inside a transaction covers exactly one
  use case. Behind PgBouncer set it on the role (`ALTER ROLE … SET statement_timeout`) — PgBouncer
  refuses or drops startup parameters it does not track.

## Tests

- **Repositories are tested against a real PostgreSQL** started by `testcontainers` — one
  container per session, migrations in the session fixture (`python-pytest`). asyncpg rejects a
  `postgresql+psycopg2://` URL, which is what the container returns by default; ask for
  `get_connection_url(driver=None)`.
- **Each test runs in a transaction that is rolled back.** The unit of work's own transaction then
  nests as a savepoint, and nothing a test writes reaches the next one:

```python
@pytest_asyncio.fixture(loop_scope="session")
async def connection(pool: asyncpg.Pool) -> AsyncIterator[PoolConnectionProxy]:
    async with pool.acquire() as connection:
        transaction = connection.transaction()
        await transaction.start()
        try:
            yield connection
        finally:
            await transaction.rollback()
```

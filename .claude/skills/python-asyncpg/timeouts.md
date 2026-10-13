# Timeouts and Cancellation

| | bounds | set |
|---|---|---|
| `timeout=` on a call | that call | a named constant, where one statement is known to be slow |
| `command_timeout` | every statement on the pool's connections | `create_pool`, from settings |
| `statement_timeout` | the query on the server, whatever the client does | `server_settings=` or the role |

### A client timeout and a cancellation both stop the query on the server

**Why:** a client timeout raises the builtin `TimeoutError` and asyncpg sends PostgreSQL a cancel
request; a cancelled `await` does the same, and inside `connection.transaction()` the transaction
rolls back — so an `asyncio.timeout` around a use case is safe, a shielded query is not, and a
swallowed `CancelledError` breaks it (`python-async`). `timeout=None` on a call means "use
`command_timeout`", not "no limit". A server `statement_timeout` arrives as
`asyncpg.QueryCanceledError` (`57014`), not `TimeoutError`, and the adapter classifies both as
transient.

**Example:**
```python
# WRONG — shielded: a timed-out caller leaves the query running and holding its locks
async def rebuild_stats(connection: PoolConnectionProxy) -> None:
    await asyncio.shield(connection.execute(_REFRESH_PLAY_COUNTS))


# CORRECT — the deadline cancels the query on the server, and the transaction rolls back
async def rebuild_stats(connection: PoolConnectionProxy) -> None:
    async with asyncio.timeout(_REFRESH_DEADLINE_SECONDS), connection.transaction():
        await connection.execute(_REFRESH_PLAY_COUNTS)
```

### A server-side `statement_timeout` is set through `server_settings` or the role

**Why:** `server_settings={"statement_timeout": ...}` survives the pool's `RESET ALL` on release; a
`SET` on an acquired connection does not, and `SET LOCAL` covers exactly one transaction. Behind
PgBouncer it goes on the role — PgBouncer refuses or drops startup parameters it does not track.

**Example:**
```python
# WRONG — reset the moment the connection goes back to the pool
async def apply_statement_timeout(connection: PoolConnectionProxy) -> None:
    await connection.execute("SET statement_timeout = '5s'")


# CORRECT — a startup parameter every connection of the pool keeps
@asynccontextmanager
async def managed_pool(config: PoolConfig) -> AsyncIterator[asyncpg.Pool]:
    async with asyncpg.create_pool(
        config.url,
        min_size=config.min_connections,
        max_size=config.max_connections,
        command_timeout=config.command_timeout_seconds,
        server_settings={"statement_timeout": str(config.statement_timeout_ms)},
    ) as pool:
        yield pool
```

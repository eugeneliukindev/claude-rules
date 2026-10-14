# Timeouts and Cancellation

| | bounds | set |
|---|---|---|
| `timeout=` on a call | that call | a named constant, where one statement is known to be slow |
| `command_timeout` | every statement on the pool's connections | `create_pool`, a factory parameter with a default |
| `statement_timeout` | the query on the server, whatever the client does | `server_settings=` or the role |

### A client timeout and a cancellation both stop the query on the server

**Why:** a client timeout raises the builtin `TimeoutError` and asyncpg sends PostgreSQL a cancel
request; a cancelled `await` does the same, and inside `connection.transaction()` the transaction
rolls back — so an `asyncio.timeout` around a use case is safe, a shielded query is not, and a
swallowed `CancelledError` breaks it. `timeout=None` on a call means "use
`command_timeout`", not "no limit". A server `statement_timeout` arrives as
`asyncpg.QueryCanceledError` (`57014`), not `TimeoutError`, and the adapter classifies both as
transient.

**Example:**
```python
# WRONG — shielded: a timed-out caller leaves the query running and holding its locks
async def refresh_standings(*, connection: PoolConnectionProxy) -> None:
    await asyncio.shield(connection.execute(_REFRESH_STANDINGS))


# CORRECT — the deadline cancels the query on the server, and the transaction rolls back
async def refresh_standings(
    *, connection: PoolConnectionProxy, deadline_seconds: float = _STANDINGS_DEADLINE_SECONDS
) -> None:
    async with asyncio.timeout(deadline_seconds), connection.transaction():
        await connection.execute(_REFRESH_STANDINGS)
```

### A server-side `statement_timeout` is set through `server_settings` or the role

**Why:** `server_settings={"statement_timeout": ...}` survives the pool's `RESET ALL` on release; a
`SET` on an acquired connection does not, and `SET LOCAL` covers exactly one transaction. Behind
PgBouncer it goes on the role — PgBouncer refuses or drops startup parameters it does not track.

**Example:**
```python
# WRONG — reset the moment the connection goes back to the pool
async def limit_statements(*, connection: PoolConnectionProxy) -> None:
    await connection.execute("SET statement_timeout = '5s'")


# CORRECT — a startup parameter every connection of the pool keeps
def tournament_pool(
    dsn: str, *, statement_timeout_ms: int = _STATEMENT_TIMEOUT_MS
) -> asyncpg.Pool:
    return asyncpg.create_pool(
        dsn, server_settings={"statement_timeout": str(statement_timeout_ms)}
    )
```

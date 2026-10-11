# Errors

Every SQLSTATE is a class in `asyncpg.exceptions`, re-exported as `asyncpg.UniqueViolationError`
and the like, carrying `sqlstate`, `constraint_name`, `table_name` and `detail`. Which errors the
retry policy treats as transient is `python-boundaries`: `TimeoutError`, `OSError` from the connect,
`asyncpg.PostgresConnectionError` and `asyncpg.TooManyConnectionsError` are; integrity violations
and `DataError` are permanent.

### A database error is caught by its class and its constraint name, never its message

**Why:** the message is for people — `lc_messages` translates it, and new versions reword it. The
class is the SQLSTATE, and `constraint_name` says which unique key was violated; the repository
translates it into its package's error with `raise … from`.

**Example:**
```python
# WRONG — the message is matched, and a translated server breaks it
async def add_user(connection: PoolConnectionProxy, email: str) -> None:
    try:
        await connection.execute(_INSERT_USER, email)
    except asyncpg.PostgresError as error:
        if "duplicate key" in str(error):
            raise EmailTakenError(email) from error
        raise


# CORRECT — the class is the SQLSTATE, and the constraint says which unique key it was
async def add_user(connection: PoolConnectionProxy, email: str) -> None:
    try:
        await connection.execute(_INSERT_USER, email)
    except asyncpg.UniqueViolationError as error:
        if error.constraint_name == _USERS_EMAIL_KEY:
            raise EmailTakenError(email) from error
        raise
```

### A rollback raised at `COMMIT` is translated by the unit of work, not a repository

**Why:** `SerializationError` and `DeadlockDetectedError`, both `asyncpg.TransactionRollbackError`,
can arrive at `COMMIT` — the unit of work's exit, after every repository call returned. So the unit
of work turns it into the transient conflict that retries the whole use case
(`python-persistence`).

**Example:**
```python
# WRONG — the rollback escapes as a driver error the retry policy does not know
@asynccontextmanager
async def open_unit_of_work(pool: asyncpg.Pool) -> AsyncIterator[UnitOfWork]:
    async with pool.acquire() as connection, connection.transaction(isolation="serializable"):
        yield UnitOfWork(playlists=PostgresPlaylistRepository(connection))


# CORRECT — the conflict becomes the package's transient error, wherever it was raised
@asynccontextmanager
async def open_unit_of_work(pool: asyncpg.Pool) -> AsyncIterator[UnitOfWork]:
    try:
        async with pool.acquire() as connection, connection.transaction(isolation="serializable"):
            yield UnitOfWork(playlists=PostgresPlaylistRepository(connection))
    except asyncpg.TransactionRollbackError as error:
        raise ConcurrentUpdateError(
            f"transaction rolled back by a concurrent one: SQLSTATE {error.sqlstate}"
        ) from error
```

# Errors

Every SQLSTATE is a class in `asyncpg.exceptions`, re-exported as `asyncpg.UniqueViolationError`
and the like, carrying `sqlstate`, `constraint_name`, `table_name` and `detail`. To a retry policy
`TimeoutError`, `OSError` from the connect, `asyncpg.PostgresConnectionError` and
`asyncpg.TooManyConnectionsError` are transient; integrity violations and `DataError` are permanent.

### A database error is caught by its class and its constraint name, never its message

**Why:** the message is for people — `lc_messages` translates it, and new versions reword it. The
class is the SQLSTATE, and `constraint_name` says which unique key was violated; the repository
translates it into its package's error with `raise … from`.

**Example:**
```python
# WRONG — the message is matched, and a translated server breaks it
async def register_player(player: Player, *, connection: PoolConnectionProxy) -> None:
    try:
        await connection.execute(_INSERT_PLAYER, player.fide_id, player.name)
    except asyncpg.PostgresError as error:
        if "duplicate key" in str(error):
            raise FideIdTakenError(player.fide_id) from error
        raise


# CORRECT — the class is the SQLSTATE, and the constraint says which unique key it was
async def register_player(player: Player, *, connection: PoolConnectionProxy) -> None:
    try:
        await connection.execute(_INSERT_PLAYER, player.fide_id, player.name)
    except asyncpg.UniqueViolationError as error:
        if error.constraint_name == _PLAYERS_FIDE_ID_KEY:
            raise FideIdTakenError(player.fide_id) from error
        raise
```

### A rollback raised at `COMMIT` is translated where the transaction closes, not in a repository

**Why:** `SerializationError` and `DeadlockDetectedError`, both `asyncpg.TransactionRollbackError`,
can arrive at `COMMIT` — the transaction's exit, after every repository call returned. So the code
that closes the transaction turns it into the package's transient error, and the retry runs the
whole use case again.

**Example:**
```python
# WRONG — the rollback escapes as a driver error the retry policy does not know
@asynccontextmanager
async def serializable_transaction(pool: asyncpg.Pool) -> AsyncIterator[PoolConnectionProxy]:
    async with pool.acquire() as connection, connection.transaction(isolation="serializable"):
        yield connection


# CORRECT — the conflict becomes the package's transient error, wherever it was raised
@asynccontextmanager
async def serializable_transaction(pool: asyncpg.Pool) -> AsyncIterator[PoolConnectionProxy]:
    try:
        async with pool.acquire() as connection, connection.transaction(isolation="serializable"):
            yield connection
    except asyncpg.TransactionRollbackError as error:
        raise PairingConflictError(
            f"transaction rolled back by a concurrent one: SQLSTATE {error.sqlstate}"
        ) from error
```

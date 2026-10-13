# Tests

The container fixtures and the session event loop are `python-pytest`.

### Repositories are tested against a real PostgreSQL, each test inside a transaction rolled back

**Why:** a fake cannot show a constraint, a cast or a codec. One `testcontainers` container per
session runs the migrations once; asyncpg rejects the `postgresql+psycopg2://` URL the container
returns by default, so it asks for `get_connection_url(driver=None)`. Each test runs in a
transaction that is rolled back, so the code's own transaction nests as a savepoint and
nothing a test writes reaches the next one.

**Example:**
```python
# WRONG — every test commits into the shared database, and the next one sees its rows
@pytest_asyncio.fixture(loop_scope="session")
async def connection(pool: asyncpg.Pool) -> AsyncIterator[PoolConnectionProxy]:
    async with pool.acquire() as connection:
        yield connection


# CORRECT — the test's writes are rolled back when it ends
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

# asyncpg and SQLAlchemy

The seam between `python-asyncpg` and `python-sqlalchemy`, linked from both skills.

### On `postgresql+asyncpg`, the engine owns the pool, and the statement timeout is a server setting

**Why:** the engine builds and sizes the pool, so asyncpg's own pool rules do not apply here.
asyncpg takes no `options` parameter: the `-c statement_timeout=…` that psycopg passes is refused,
and the timeout goes through `server_settings`, sent when each connection opens.

**Example:**
```python
# WRONG — psycopg's options string: asyncpg refuses it when the first connection opens
def build_engine(database_url: str, *, pool_size: int, statement_timeout_ms: int) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        pool_pre_ping=True,
        connect_args={"options": f"-c statement_timeout={statement_timeout_ms}"},
    )


# CORRECT — the timeout as a server setting, applied to every connection the engine opens
def build_engine(database_url: str, *, pool_size: int, statement_timeout_ms: int) -> AsyncEngine:
    return create_async_engine(
        database_url,
        pool_size=pool_size,
        pool_pre_ping=True,
        connect_args={"server_settings": {"statement_timeout": str(statement_timeout_ms)}},
    )
```

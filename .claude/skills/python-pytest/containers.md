# Containers

### Integration tests start the production image from `testcontainers.community`, once per session

**Why:** the real database or broker is what the integration level exists to exercise
(`testing.md`), from the image production runs. In 4.x the modules are
`testcontainers.community.postgres` and the like — the top-level `testcontainers.postgres` is
deprecated, and with warnings as errors its import fails. Each module needs its extra —
`testcontainers[rabbitmq]` pulls `pika` — or the import fails with `ModuleNotFoundError`. Starting a
container costs seconds, so there is one per session and one transaction or schema reset per test;
migrations run in the session fixture, which also proves the chain. `get_connection_url()` returns
`postgresql+psycopg2://` unless told otherwise — `driver=None` for asyncpg, `driver="asyncpg"` for
SQLAlchemy's async engine. Integration tests carry a registered marker, so the unit suite runs
without Docker.

**Example:**
```python
# WRONG — function scope, the deprecated module: every test waits for a fresh database
@pytest.fixture
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer(_POSTGRES_IMAGE) as container:
        yield container


# CORRECT — one container for the session, migrated once, with a URL the driver accepts
@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer(_POSTGRES_IMAGE) as container:
        url = container.get_connection_url(driver=None)
        run_migrations(url)
        yield url
```

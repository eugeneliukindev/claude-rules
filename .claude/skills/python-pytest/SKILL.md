---
name: python-pytest
description: >-
  pytest mechanics beyond the testing rules: pytest-asyncio and anyio, hypothesis,
  pytest-httpserver and respx, testcontainers, conftest layering, markers, coverage. Use when test
  code imports pytest_asyncio, hypothesis, pytest_httpserver, respx or testcontainers, writes an
  async test or fixture, edits conftest.py, or configures coverage.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# pytest

Checked against pytest 9.1, pytest-asyncio 1.4, hypothesis 6.168, pytest-httpserver 1.2, respx 0.23
and testcontainers 4.15. What to test, the three levels, fakes over mocks and the shape of a test
are in `testing.md`. Configuration lives in `[tool.pytest]` (`python-project`); an ASGI app in an
async test is `python-fastapi`.

## Async Tests

### One async plugin per project, in auto mode, with the fixture loop scope stated

**Why:** `pytest-asyncio` fits code written against `asyncio`, anyio's own plugin —
`@pytest.mark.anyio` and an `anyio_backend` fixture — code written against `anyio`; two plugins both
claim `async def` tests. `asyncio_mode = "auto"` lets an `async def test_…` and an async fixture run
without a marker, and `asyncio_default_fixture_loop_scope = "function"` is stated rather than left
to the plugin's warning.

### A shared loop is a `loop_scope`, never an `event_loop` fixture

**Why:** the `event_loop` fixture is gone in 1.0, and an override of it is silently ignored — 1.x
never requests it. A session-scoped async fixture says `loop_scope="session"`, and so does every
test using it, or the test runs on its own loop and a pool created on the fixture's loop fails
there with "attached to a different loop". A module whose tests share a loop takes
`pytestmark = pytest.mark.asyncio(loop_scope="module")` once.

**Example:**
```python
# WRONG — the 0.x override, ignored by 1.x; the test then runs on a loop the pool never saw
@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def test_reservation_is_saved_and_read_back(pool: DatabasePool) -> None:
    reservations = PostgresReservationRepository(pool=pool)

    await reservations.add(_RESERVATION)

    assert await reservations.find(_RESERVATION.reservation_id) == _RESERVATION


# CORRECT — the fixture and the test name the same loop
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def pool() -> AsyncIterator[DatabasePool]:
    pool = open_database_pool(_DATABASE_URL)
    yield pool
    await pool.close()


@pytest.mark.asyncio(loop_scope="session")
async def test_reservation_is_saved_and_read_back(pool: DatabasePool) -> None:
    reservations = PostgresReservationRepository(pool=pool)

    await reservations.add(_RESERVATION)

    assert await reservations.find(_RESERVATION.reservation_id) == _RESERVATION
```

## `conftest.py`

### A fixture lives in the nearest `conftest.py` above its users; a helper, in a module

**Why:** a fixture is visible downward only, so factories every level shares go in
`tests/conftest.py`, fakes in the unit tree's, containers in the integration tree's. Fakes and
factories are ordinary modules — `tests/fakes.py`, `tests/factories.py` — imported by name: a
`conftest.py` is not meant to be imported, and an import of it that works today breaks under
`--import-mode=importlib`. `pytest_plugins` goes only in the root `conftest.py`; deeper, pytest
refuses to start.

## Property-Based Tests

**Before writing a test with `hypothesis` — a round trip, an invariant, a parser that must not
crash — read [hypothesis.md](hypothesis.md)** — strategies from the domain's constraints, failures
pinned with `@example`, a CI profile without the deadline.

## HTTP Adapters

**Before testing an adapter that calls an HTTP API, read [http-adapters.md](http-adapters.md)** — a
real local server through the adapter's real client, never a patched `get`; `respx` only for
`httpx`.

## Containers

**Before starting a database or a broker for integration tests, read
[containers.md](containers.md)** — `testcontainers.community`, the extras, `get_connection_url`, one
container per session, migrations in the fixture, the integration marker.

## Coverage

**Before setting up or judging coverage, read [coverage.md](coverage.md)** — branch coverage, a
floor that only ratchets up, never a target.
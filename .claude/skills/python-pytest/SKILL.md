---
name: python-pytest
description: >-
  pytest mechanics beyond testing.md: async tests with pytest-asyncio 1.x — auto mode, loop scope
  for session fixtures, no event_loop fixture — or anyio's plugin; property-based tests with
  hypothesis for round trips and invariants; testing an HTTP adapter against a real local server
  with pytest-httpserver, or respx for httpx; integration tests on testcontainers; conftest.py
  layering and markers. Use when Python test code imports pytest, pytest_asyncio, hypothesis,
  pytest_httpserver, respx or testcontainers, writes an async test or fixture, edits conftest.py,
  or sets up or judges coverage.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# pytest

Checked against pytest 9.1, pytest-asyncio 1.4, hypothesis 6.168, pytest-httpserver 1.2 and
testcontainers 4.15. What to test, the three levels, fakes over mocks and the shape of a test are
in `testing.md`; this file is how the libraries do it. Configuration lives in `[tool.pytest]`
(`python-project`).

## Async Tests

- **One plugin per project.** `pytest-asyncio` for code written against `asyncio`; anyio's own
  plugin — `@pytest.mark.anyio` and an `anyio_backend` fixture — for code written against `anyio`
  (`python-async`). Two plugins both claim `async def` tests.
- **`asyncio_mode = "auto"`**, so an `async def test_…` and an async fixture need no marker; and
  `asyncio_default_fixture_loop_scope = "function"`, stated rather than left to the plugin's
  warning.
- **The `event_loop` fixture is gone** in 1.0, and so is overriding it to share a loop. A loop's
  lifetime is the `loop_scope` argument.

```python
# WRONG — the 0.x override: 1.x never requests it, so it is silently ignored
@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

# CORRECT — no loop fixture; the async fixture names the loop it lives on
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine() -> AsyncIterator[AsyncEngine]: ...
```

- **A session-scoped async fixture needs `loop_scope="session"` — and so does every test using
  it.** The test otherwise runs on its own loop, and an engine or a client created on the
  fixture's loop fails there with "attached to a different loop".

```python
# conftest.py
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_DATABASE_URL)
    yield engine
    await engine.dispose()


# WRONG — test_orders.py: the test gets a loop of its own, and the engine's connections fail on it
async def test_order_is_saved_and_read_back(engine: AsyncEngine) -> None: ...

# CORRECT — test_orders.py: the test runs on the loop the engine was created on
@pytest.mark.asyncio(loop_scope="session")
async def test_order_is_saved_and_read_back(engine: AsyncEngine) -> None: ...
```

- **Several tests sharing a loop** take `pytestmark = pytest.mark.asyncio(loop_scope="module")` at
  the top of the module, rather than the marker on each.
- **An ASGI app in an async test goes through an async client**, never the sync `TestClient`, which
  runs the app on a loop of its own; run the lifespan with `LifespanManager` and send through
  `ASGITransport(app=manager.app)`, since `ASGITransport` alone runs none (how: `python-fastapi`).
  Both collect the whole body before returning, so a streaming endpoint is tested with a stream
  that ends (`python-streaming`).

## Property-Based Tests With `hypothesis`

An example test checks the cases its author thought of; a property test states what holds for
every input and lets the library look for the counterexample.

- **Round trips first.** `python-boundaries` requires `from_dict(to_dict(x)) == x` for every
  serialized type; a property test is that requirement, over every value the strategy can build
  instead of one.
- **Invariants of value objects and parsers**: a constructor either returns a valid object or
  raises the package's error, never another exception; a parser never crashes on arbitrary text.
- **A failure found once is pinned with `@example`**, so it is rerun on every run even when the
  example database is gone.
- **Strategies are built once, at module level**, from the domain's own constraints —
  `st.decimals(places=2, allow_nan=False, allow_infinity=False)` for money, never `st.floats()`.

```python
# WRONG — floats bring NaN, which never equals itself, and fractions no price was written as
_MONEY: Final = st.builds(
    Money,
    amount=st.floats().map(Decimal),
    currency=st.sampled_from(Currency),
)

# CORRECT — the values money can actually hold
_MONEY: Final = st.builds(
    Money,
    amount=st.decimals(places=2, allow_nan=False, allow_infinity=False),
    currency=st.sampled_from(Currency),
)


@given(_MONEY)
@example(Money(amount=Decimal("-0.00"), currency=Currency.EUR))
def test_money_round_trips_through_dict(money: Money) -> None:
    assert Money.from_dict(money.to_dict()) == money
```

- **The deadline is a CI hazard, not a performance test.** A shared runner trips the 200 ms
  default at random; register a profile with `deadline=None` for CI with
  `settings.register_profile` and load it by environment in the root `conftest.py`.
- `.hypothesis/` is the example database — in `.gitignore`.

## HTTP Adapters

The service behind an adapter is tested with a fake of the contract (`testing.md`). The adapter
itself — the request it builds, the errors it translates, its timeouts — is tested against HTTP:

- **`pytest-httpserver` runs a real server on localhost**, so the adapter is exercised through its
  real client, session and error translation, whichever library that is. Point the adapter's base
  URL at `httpserver.url_for("/")`, declare each expected request, and assert the domain result.
- **Never patch the client library's functions** — a patched `get` proves the code calls `get`, not
  that the adapter handles a `503`.

```python
# WRONG — proves the adapter calls get, not that it turns a real 404 into OrderNotFoundError
def test_fetch_order_translates_missing_order(mocker: MockerFixture) -> None:
    response = mocker.Mock(spec=niquests.Response, status_code=HTTPStatus.NOT_FOUND)
    mocker.patch.object(niquests.Session, "get", return_value=response)
    client = OrderClient(base_url="https://orders.example.com", timeout_seconds=_TIMEOUT_SECONDS)

    with pytest.raises(OrderNotFoundError, match="42") as excinfo:
        client.fetch_order(OrderId(42))

    assert excinfo.value.order_id == OrderId(42)

# CORRECT — a real server answers 404, through the adapter's real session and error translation
def test_fetch_order_translates_missing_order(httpserver: HTTPServer) -> None:
    httpserver.expect_request("/orders/42").respond_with_json(
        {"detail": "not found"}, status=HTTPStatus.NOT_FOUND
    )
    client = OrderClient(base_url=httpserver.url_for("/"), timeout_seconds=_TIMEOUT_SECONDS)

    with pytest.raises(OrderNotFoundError, match="42") as excinfo:
        client.fetch_order(OrderId(42))

    assert excinfo.value.order_id == OrderId(42)
```

- **`respx` patches `httpx`'s transport**, and only `httpx`'s; a codebase on `httpx` may use it.
  It does not see `niquests`.

## Integration Tests on Containers

- **`testcontainers` starts the real database for the integration level**, from the image
  production runs: `from testcontainers.community.postgres import PostgresContainer` in 4.x — the
  top-level `testcontainers.postgres` is deprecated. The same holds for a broker:
  `testcontainers.community.rabbitmq.RabbitMqContainer`, not `testcontainers.rabbitmq`
  (`python-faststream`).
- **`get_connection_url()` returns a `postgresql+psycopg2://` URL** unless told otherwise:
  `driver=None` for a plain URL that asyncpg accepts (`python-asyncpg`), `driver="asyncpg"` for
  SQLAlchemy's async engine.
- **One container per session, one transaction or one schema reset per test.** Starting a
  container costs seconds; a test that leaves rows behind makes the next one order-dependent, which
  `pytest-randomly` will find.

```python
# WRONG — function scope: every test waits seconds for a fresh database to start
@pytest.fixture
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer(_POSTGRES_IMAGE) as container:
        yield container

# CORRECT — one container, started once for the whole session
@pytest.fixture(scope="session")
def postgres() -> Iterator[PostgresContainer]:
    with PostgresContainer(_POSTGRES_IMAGE) as container:
        yield container
```

- **Migrations run in the session fixture**, so the suite also proves the migration chain
  (`python-migrations`).
- **Integration tests carry a marker** — `@pytest.mark.integration`, registered under `markers` —
  so the unit suite runs without Docker and CI runs both.

## `conftest.py` Layering

- **A fixture lives in the nearest `conftest.py` above every test that uses it**: factories every
  level shares in `tests/conftest.py`, fakes in the unit tree's, containers in the integration
  tree's. A fixture is visible downward only.
- **`conftest.py` holds fixtures and hooks, not helpers.** Fakes and factories are ordinary modules
  — `tests/fakes.py`, `tests/factories.py` — imported by name. A `conftest.py` is not meant to be
  imported, and an import of it that works today breaks under `--import-mode=importlib`.

```python
# WRONG — works only while pytest puts this directory on sys.path, which importlib mode does not
from conftest import make_order

# CORRECT — the factories are an ordinary module of the tests package
from tests.factories import make_order
```

- **`pytest_plugins` only in the root `conftest.py`**; anywhere deeper, pytest refuses to start.

## Coverage

- **Branch coverage, no single magic number.** Line coverage hides untested `else` arms. Domain
  and services aim at ~100%, adapters mainly through integration tests; generated code and
  migrations are excluded in configuration. The floor (`--cov-fail-under`) only ratchets up.
- **Coverage detects untested code; it is never a target.** A test that exists to colour lines green
  converts an honest unknown into false confidence, which is worse than the gap it hides.

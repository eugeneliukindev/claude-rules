---
name: python-pytest
description: >-
  pytest mechanics beyond the testing rules: pytest-asyncio and anyio, hypothesis, pytest-httpserver
  and respx, testcontainers, conftest layering, markers, coverage. Use when test code imports
  pytest_asyncio, hypothesis, pytest_httpserver, respx or testcontainers, writes a property-based or
  async test or fixture, edits conftest.py, or configures coverage.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# pytest

Checked against pytest 9.1, pytest-asyncio 1.4, hypothesis 6.168, pytest-httpserver 1.2, respx 0.23
and testcontainers 4.15. What to test, the three levels, fakes over mocks and the shape of a test
are in `testing.md`. Configuration lives in `[tool.pytest]` (`python-project`).

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
test using it, or the test runs on its own loop and a connection opened on the fixture's loop
fails there with "attached to a different loop". A module whose tests share a loop takes
`pytestmark = pytest.mark.asyncio(loop_scope="module")` once.

**Example:**
```python
# WRONG — the 0.x override, ignored by 1.x; the test then runs on a loop the store never saw
@pytest.fixture(scope="session")
def event_loop() -> Iterator[asyncio.AbstractEventLoop]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


async def test_card_is_saved_and_read_back(deck_store: DeckStore) -> None:
    await deck_store.add(_CARD)

    stored = await deck_store.find(_CARD.card_id)

    assert stored == _CARD


# CORRECT — the fixture and the test name the same loop
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def deck_store() -> AsyncIterator[DeckStore]:
    async with DeckStore.connect(_DECK_DATABASE_URL) as store:
        yield store


@pytest.mark.asyncio(loop_scope="session")
async def test_card_is_saved_and_read_back(deck_store: DeckStore) -> None:
    await deck_store.add(_CARD)

    stored = await deck_store.find(_CARD.card_id)

    assert stored == _CARD
```

## `conftest.py`

### A `conftest.py` is never imported, and `pytest_plugins` sits only in the root one

**Why:** pytest loads a `conftest.py` itself; an `import conftest` that works today under the
default import mode breaks under `--import-mode=importlib`. What a test imports by name — the fakes,
a helper — is an ordinary module (`testing.md`). `pytest_plugins` in a deeper `conftest.py` makes
pytest refuse to start.

## Property-Based Tests

**Before writing a test with `hypothesis` — a round trip, an invariant, a parser that must not
crash — read [hypothesis.md](hypothesis.md)** — strategies from the domain's constraints, failures
pinned with `@example`, a CI profile without the deadline.

- A strategy is built once, from the domain's own bounds, and a found failure is pinned
- CI loads a profile without the deadline

## HTTP Adapters

**Before testing an adapter that calls an HTTP API, read [http-adapters.md](http-adapters.md)** — a
real local server through the adapter's real client, never a patched `get`; `respx` only for
`httpx`; a request no handler matched fails the test.

- An adapter is tested against a real local server, never a patched client method
- A test that expects a server error ends with `httpserver.check_assertions()`

## Containers

**Before starting a database or a broker for integration tests, read
[containers.md](containers.md)** — `testcontainers.community`, the extras, `get_connection_url`, one
container per session, migrations in the fixture, the integration marker.

- Integration tests start the production image from `testcontainers.community`, once per session

## Coverage

**Before setting up or judging coverage, read [coverage.md](coverage.md)** — branch coverage, a
floor that only ratchets up, never a target.

- Coverage measures branches, with a floor that only ratchets up, and is never a target
# Testing a FastAPI App

## Contents

- `TestClient` as a context manager, on `httpx2`
- An async test uses an async client and `LifespanManager`
- The test root is the factory or `dependency_overrides`

Routes are tested through HTTP, asserting the status and the body; the service behind them is tested
directly, without FastAPI, as the testing rules ask.

### `TestClient` is entered with `with`, and `httpx2` is in the test dependencies

**Why:** without the `with`, the lifespan never runs, nothing it builds exists, and the first
dependency fails. `TestClient` is built on `httpx2`; Starlette 1.7 still falls back to `httpx` with
a `StarletteDeprecationWarning`, which `filterwarnings = ["error"]` turns into a collection error.

**Example:**
```python
# WRONG — no with: the lifespan never runs, and request.state has no task_service
def test_get_task_returns_404_for_unknown_task(app: FastAPI) -> None:
    client = TestClient(app)

    response = client.get("/tasks/42")

    assert response.status_code == HTTPStatus.NOT_FOUND


# CORRECT — the with block runs the lifespan on entry and closes what it built on exit
def test_get_task_returns_404_for_unknown_task(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/tasks/42")

    assert response.status_code == HTTPStatus.NOT_FOUND
```

### An async test uses an async client through `LifespanManager`

**Why:** the sync `TestClient` runs the app on an event loop of its own, and a connection an async
fixture opened on the test's loop fails there. `asgi-lifespan`'s `LifespanManager` runs the
lifespan, and `manager.app` carries its state; `ASGITransport` alone runs no lifespan.

**Example:**
```python
# WRONG — ASGITransport alone: the lifespan never ran, so the first dependency fails
async def test_get_task_returns_404_for_unknown_task() -> None:
    app = create_app(_TEST_SETTINGS)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/tasks/42")

    assert response.status_code == HTTPStatus.NOT_FOUND


# CORRECT — the lifespan runs, and requests go through the app that carries its state
async def test_get_task_returns_404_for_unknown_task() -> None:
    app = create_app(_TEST_SETTINGS)
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as client,
    ):
        response = await client.get("/tasks/42")

    assert response.status_code == HTTPStatus.NOT_FOUND
```

### The test root is the factory or `dependency_overrides`, never a patched module

**Why:** an override returns a service built on in-memory fakes, the same graph the root builds; a
patch reaches past the seam. When the overrides multiply, `create_app` takes the lifespan's builder
as a parameter and the tests pass the fakes' builder.

**Example:**
```python
# WRONG — the service module is patched, and the app still builds its real engine
def test_close_task_closes_it(mocker: MockerFixture, app: FastAPI) -> None:
    mocker.patch("tracker.api.tasks.PostgresTaskRepository", InMemoryTaskRepository)
    with TestClient(app) as client:
        response = client.post("/tasks/42/close")

    assert response.status_code == HTTPStatus.OK


# CORRECT — the accessor is overridden with a service on fakes
def test_close_task_closes_it(app: FastAPI) -> None:
    repository = InMemoryTaskRepository([make_task(task_id=TaskId(42))])
    app.dependency_overrides[get_task_service] = lambda: TaskService(repository)
    with TestClient(app) as client:
        response = client.post("/tasks/42/close")

    assert response.status_code == HTTPStatus.OK
```

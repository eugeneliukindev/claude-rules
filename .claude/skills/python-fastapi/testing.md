# Testing a FastAPI App

Routes are tested through HTTP, asserting the status and the body; the service behind them is tested
directly, without FastAPI.

### `TestClient` is entered with `with`, and `httpx2` is in the test dependencies

**Why:** without the `with`, the lifespan never runs, nothing it builds exists, and the first
dependency fails. `TestClient` is built on `httpx2`; Starlette 1.8 still falls back to `httpx` with
a `StarletteDeprecationWarning`, which `filterwarnings = ["error"]` turns into a collection error.

**Example:**
```python
# WRONG — no with: the lifespan never runs, and request.state has no bike_share
def test_get_ride_returns_404_for_unknown_ride(app: FastAPI) -> None:
    client = TestClient(app)

    response = client.get("/rides/42")

    assert response.status_code == HTTPStatus.NOT_FOUND


# CORRECT — the with block runs the lifespan on entry and closes what it built on exit
def test_get_ride_returns_404_for_unknown_ride(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/rides/42")

    assert response.status_code == HTTPStatus.NOT_FOUND
```

### An async test uses an async client through `LifespanManager`

**Why:** the sync `TestClient` runs the app on an event loop of its own, and a connection an async
fixture opened on the test's loop fails there. `asgi-lifespan`'s `LifespanManager` runs the
lifespan, and `manager.app` carries its state; `ASGITransport` alone runs no lifespan.

**Example:**
```python
# WRONG — ASGITransport alone: the lifespan never ran, so the first dependency fails
async def test_get_ride_returns_404_for_unknown_ride() -> None:
    app = build_bike_share_api(database_url=_TEST_DATABASE_URL)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/rides/42")

    assert response.status_code == HTTPStatus.NOT_FOUND


# CORRECT — the lifespan runs, and requests go through the app that carries its state
async def test_get_ride_returns_404_for_unknown_ride() -> None:
    app = build_bike_share_api(database_url=_TEST_DATABASE_URL)
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as client,
    ):
        response = await client.get("/rides/42")

    assert response.status_code == HTTPStatus.NOT_FOUND
```

### The test root is the factory or `dependency_overrides`, never a patched module

**Why:** an override returns a service built on in-memory fakes, the same graph the lifespan
builds; a patch reaches past the seam. When the overrides multiply, the factory takes the
lifespan's builder as a parameter and the tests pass the fakes' builder.

**Example:**
```python
# WRONG — the repository module is patched, and the app still opens its real store
def test_end_ride_docks_the_bike(mocker: MockerFixture, app: FastAPI) -> None:
    mocker.patch("bike_share.api.rides.PostgresRideRepository", InMemoryRideRepository)
    with TestClient(app) as client:
        response = client.post("/rides/42/end", json={"station_id": _STATION_ID})

    assert response.status_code == HTTPStatus.OK


# CORRECT — the accessor is overridden with a service on fakes
def test_end_ride_docks_the_bike(app: FastAPI) -> None:
    rides = InMemoryRideRepository(
        rides=[make_ride(ride_id=RideId(42))], stations=[make_station(station_id=_STATION_ID)]
    )
    app.dependency_overrides[get_bike_share] = lambda: BikeShareService(rides=rides)
    with TestClient(app) as client:
        response = client.post("/rides/42/end", json={"station_id": _STATION_ID})

    assert response.status_code == HTTPStatus.OK
```

---
name: python-fastapi
description: >-
  FastAPI mechanics: the app factory and lifespan, Depends as an accessor, routers, error
  mapping, SSE and WebSocket routes, uvicorn, tests. Use when code imports fastapi, starlette or
  uvicorn, defines a route, router, dependency, lifespan, exception handler or WebSocket, or tests
  an ASGI app. Not for what a stream must guarantee whatever the framework (python-streaming).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# FastAPI

Checked against FastAPI 0.143, Starlette 1.8 and uvicorn 0.54. Where an object is built and how
long it lives is `python-wiring`; request and response models are `python-pydantic` — a strict body
model relaxes its `datetime`, `UUID` and `Decimal` fields by name, or every valid payload is a 422;
work that must survive a restart is `python-workers`. `Depends` looks like dependency injection and
is used, in most tutorials, as a service locator.

## The Factory and the Lifespan

### A factory builds the app from plain values, and its lifespan enters every resource

**Why:** a module-level `app = FastAPI()` with a pool beside it runs at import (`modules.md`), and
the documentation's `@lru_cache` settings getter is the same global with extra steps — a test
that needs another value has to clear a cache. The factory takes plain values (`functions.md`),
which the entry point unpacks from its settings (`serving.md`). The lifespan enters each resource
through the resource's own `async with`, builds the services inside, and yields what requests
need — Starlette puts it on `request.state` — and the exits run in reverse on shutdown.
`@app.on_event("startup")` is deprecated, and a startup and shutdown pair releases in registration
order, apart from the acquire.

**Example:**
```python
# WRONG — a cached global for the settings, and a connection opened on every request
@lru_cache
def _cached_settings() -> Settings:
    return Settings()


def _bike_share(settings: Annotated[Settings, Depends(_cached_settings)]) -> BikeShareService:
    return BikeShareService(rides=PostgresRideRepository(connect_rides(settings.database_url)))


# CORRECT — the lifespan opens the store once; a dependency only hands the service over
def build_bike_share_api(*, database_url: str) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with RideStore.connect(database_url) as rides:
            yield {"bike_share": BikeShareService(rides=rides)}

    app = FastAPI(lifespan=lifespan)
    app.include_router(rides_router)
    app.add_exception_handler(BikeShareError, _bike_share_error_response)
    return app
```

## `Depends`

### A dependency is an `async def` accessor to what the lifespan built, named once as an alias

**Why:** a dependency that constructs a pool or a client constructs it per request; it reads, holds
no business logic and reads no settings — the seam between FastAPI and the service. A plain `def`
runs in the thread pool on every request, so an accessor that only reads `request.state` is
`async def`; one that blocks — a verifier fetching a key set — stays a `def`. `request.state` is
untyped: the accessor states the type once on an annotated local — returning the attribute directly
is `no-any-return` — and the `Annotated` alias gives every route a real class. A request-scoped
object — the caller's locale, a scratch directory — may be built here from those parts.

**Example:**
```python
# WRONG — the dependency builds the service, and returns an Any the checker cannot see through
def get_bike_share(request: Request) -> BikeShareService:
    return BikeShareService(rides=PostgresRideRepository(request.state.connection))


# CORRECT — an async accessor to what the lifespan built, typed once, named once
async def get_bike_share(request: Request) -> BikeShareService:
    service: BikeShareService = request.state.bike_share
    return service


type BikeShareDep = Annotated[BikeShareService, Depends(get_bike_share)]
```

### A dependency with `yield` releases in `finally`

**Why:** without `try`/`finally` the release after `yield` is skipped when the route raises, and
whatever the dependency acquired — a scratch directory, a lease — is never released. A dependency
cached for the life of the app is a lazy singleton — it belongs in the lifespan.

## Routers

### A route parses, calls one service method, and builds the response

**Why:** anything else in a route's body is a service method not yet written, and a rule there is
reachable only through HTTP. The domain and the services never import `fastapi`. Authentication is
declared once, on the router holding the protected routes, with the public ones — the health probes
among them — on a router of their own.

**Example:**
```python
# WRONG — the route decides: the full-station rule is reachable only through HTTP
@rides_router.post("/rides/{ride_id}/end")
async def end_ride(ride_id: RideId, dock: DockRequest, bike_share: BikeShareDep) -> RideResponse:
    station = await bike_share.get_station(dock.station_id)
    if station.free_docks == 0:
        raise HTTPException(status.HTTP_409_CONFLICT, f"station {dock.station_id} is full")
    return RideResponse.from_domain(await bike_share.end_ride(ride_id, station_id=dock.station_id))


# CORRECT — parse, call one service method, build the response; the rule lives in the service
@rides_router.post("/rides/{ride_id}/end")
async def end_ride(ride_id: RideId, dock: DockRequest, bike_share: BikeShareDep) -> RideResponse:
    return RideResponse.from_domain(await bike_share.end_ride(ride_id, station_id=dock.station_id))
```

### ruff's `runtime-evaluated-decorators` names every route decorator in use

**Why:** FastAPI reads a route's annotations at runtime to build its parameters, so ruff's `TC`
fix that moves their imports under `TYPE_CHECKING` breaks the route on import, wherever
annotations are not evaluated at definition.

**Example:**
```toml
# WRONG — the fix moves a parameter type's import out of the route's runtime reach
[tool.ruff.lint]
select = ["ALL"]

# CORRECT — every router method the project uses
[tool.ruff.lint.flake8-type-checking]
runtime-evaluated-decorators = [
  "fastapi.APIRouter.get",
  "fastapi.APIRouter.post",
  "fastapi.APIRouter.put",
  "fastapi.APIRouter.patch",
  "fastapi.APIRouter.delete",
]
```

### Domain errors map to statuses in one handler, and only a classified error gets a 4xx

**Why:** a service that raises `HTTPException` has learned about the transport, and a CLI or a
worker calling it gets an HTTP error. The factory registers one handler on the package's root
error; an error classified as the client's gets its status and message, and everything else — an
upstream that failed, a bug — re-raises into a 500 with a fixed body, its detail in the log: an
unclassified message carries hostnames, ids and internals. The handler takes `Exception` because
Starlette's signature does, and walks the MRO so a subclass of a mapped error is mapped too.

**Example:**
```python
# WRONG — every unclassified failure becomes a 409 that tells the client what broke inside
async def _bike_share_error_response(request: Request, error: Exception) -> JSONResponse:
    status_code = HTTPStatus.NOT_FOUND if isinstance(error, LookupError) else HTTPStatus.CONFLICT
    return JSONResponse({"detail": str(error)}, status_code=status_code)


# CORRECT — the classified errors map to a status; the rest re-raise and the server answers 500
_CLIENT_STATUS_BY_ERROR: Final[Mapping[type[BikeShareError], HTTPStatus]] = MappingProxyType({
    RideNotFoundError: HTTPStatus.NOT_FOUND,
    StationFullError: HTTPStatus.CONFLICT,
})


async def _bike_share_error_response(request: Request, error: Exception) -> JSONResponse:
    for error_class in type(error).__mro__:
        status_code = _CLIENT_STATUS_BY_ERROR.get(error_class)
        if status_code is not None:
            return JSONResponse({"detail": str(error)}, status_code=status_code)
    raise error
```

### `BackgroundTasks` carry only work whose loss nobody notices

**Why:** they run in the same process after the response is sent; a restart loses them and nothing
retries them. Work that must happen is written by the service, in the same transaction, to an
outbox a worker drains.

**Example:**
```python
# WRONG — the repair crew is never told whenever the process restarts after the response
@rides_router.post("/bikes/{bike_id}/damage-reports")
async def report_damage(
    bike_id: BikeId,
    report: DamageReportRequest,
    bike_share: BikeShareDep,
    background: BackgroundTasks,
) -> DamageReportResponse:
    damage = await bike_share.report_damage(bike_id, description=report.description)
    background.add_task(bike_share.alert_repair_crew, damage)
    return DamageReportResponse.from_domain(damage)


# CORRECT — the service writes the repair request to its outbox with the report
@rides_router.post("/bikes/{bike_id}/damage-reports")
async def report_damage(
    bike_id: BikeId, report: DamageReportRequest, bike_share: BikeShareDep
) -> DamageReportResponse:
    damage = await bike_share.report_damage(bike_id, description=report.description)
    return DamageReportResponse.from_domain(damage)
```

## Authentication

**Before writing the dependency that verifies a bearer token, setting a session cookie, or testing
a protected route, read [authentication.md](authentication.md)** — one fixed 401 body, 503 for an
unreachable key set, `set_cookie` flags, tests through the app.

## Streaming and WebSockets

**Before writing a route that streams — a generator under `EventSourceResponse`, a
`StreamingResponse`, a WebSocket — read [streaming.md](streaming.md)** — the response classes, how a
disconnect arrives, the WebSocket handler, uvicorn's flags, the tests.

## Testing

**Before testing a FastAPI app, read [testing.md](testing.md)** — `TestClient` as a context manager,
`httpx2`, an async client with `LifespanManager`, the test root through the factory or
`dependency_overrides`.

## Serving

**Before writing the entry point that runs uvicorn, read [serving.md](serving.md)** — the settings
built there and unpacked into the factory, the drain bounded below the grace period, and
`forwarded_allow_ips` set to the proxy's network behind one.

## With Other Libraries

**Before caching with cashews in a FastAPI app, read
[cashews-fastapi.md](../python-integrations/cashews-fastapi.md)** — the cache entered in the
lifespan, no middleware that lets a client clear it, decorators on the service and not the route,
and 429 and 503 for its rate limit and circuit breaker.

**Before publishing a FastStream message from a FastAPI app, read
[fastapi-faststream.md](../python-integrations/fastapi-faststream.md)** — the event written to the
outbox by the service, never published from the route.

**Before running a gRPC server beside a FastAPI app, read
[fastapi-grpc.md](../python-integrations/fastapi-grpc.md)** — the server entered in the lifespan,
under one worker.

**Before declaring a FastAPI request or response model, or answering a validation error, read
[fastapi-pydantic.md](../python-integrations/fastapi-pydantic.md)** — `input` dropped from the 422,
the response built from the domain and named by the return annotation.

**Before using SQLAlchemy in a FastAPI app, read
[fastapi-sqlalchemy.md](../python-integrations/fastapi-sqlalchemy.md)** — the engine and a `partial`
service factory in the lifespan, a session per request on `scope="function"`, the service commits.

**Before mounting a strawberry GraphQL app in FastAPI, read
[fastapi-strawberry.md](../python-integrations/fastapi-strawberry.md)** — the context getter as an
authenticating dependency, on `HTTPConnection`.

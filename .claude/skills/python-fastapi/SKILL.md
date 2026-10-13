---
name: python-fastapi
description: >-
  FastAPI mechanics under the composition-root rules: the factory and lifespan, Depends as an
  accessor, routers, error mapping, response models, sync and async routes, streaming and
  WebSockets, tests. Use when code imports fastapi or starlette, defines a route, router,
  dependency, lifespan, exception handler or WebSocket, or tests an ASGI app.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# FastAPI

Checked against FastAPI 0.143 and Starlette 1.7. Construction, lifetime and layering are
`python-wiring`; request and response models are `python-pydantic` — and a strict body model relaxes
its `datetime`, `UUID` and `Decimal` fields by name, or every valid payload is a 422. `Depends`
looks like dependency injection and is used, in most tutorials, as a service locator.

## The Factory and the Lifespan

### `create_app(settings)` builds the app, and its lifespan builds and closes every resource

**Why:** a module-level `app = FastAPI()` with a pool beside it is the global singleton
`python-wiring` forbids, and the documentation's `@lru_cache def get_settings()` is one with extra
steps — a test that needs another value has to clear a cache. The factory takes the settings its
caller built; the server runs it with `uvicorn --factory`. The lifespan holds one `async with` with
an item per resource, builds the services inside, and yields what requests need — Starlette puts it
on `request.state` — closing everything in reverse on shutdown. `@app.on_event("startup")` is the
deprecated shape, and a startup and shutdown pair releases in registration order, apart from the
acquire. Every worker runs the lifespan, so a server it starts on a port of its own needs one
worker.

**Example:**
```python
# WRONG — a cached global for settings, and a pool built on every request
@lru_cache
def get_settings() -> Settings:
    return Settings()


def task_service(settings: Annotated[Settings, Depends(get_settings)]) -> TaskService:
    return TaskService(PostgresTaskRepository(open_database_pool(settings.database_url)))


# CORRECT — the factory's lifespan builds once; the dependency only hands it over
def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_pool(settings.database_url) as pool:
            yield {"task_service": TaskService(PostgresTaskRepository(pool))}

    app = FastAPI(lifespan=lifespan)
    app.include_router(tasks_router)
    app.add_exception_handler(TrackerError, _tracker_error_response)
    return app
```

## `Depends`

### A dependency is an `async def` accessor to what the lifespan built, named once as an alias

**Why:** a dependency that constructs a pool or a client constructs it per request; it
reads, holds no business logic and reads no settings — three lines at most, the seam between
FastAPI and the service. A plain `def` runs in the thread pool on every request, so an accessor that
only reads `request.state` is `async def`; one that blocks — a verifier fetching a key set — stays a
`def`. `request.state` is untyped: the accessor states the type once on an annotated local —
returning the attribute directly is `no-any-return` — and the `Annotated` alias gives every route a
real class to read. A request-scoped object — the caller's locale, a scratch directory — may be
built here from those parts.

**Example:**
```python
# WRONG — the dependency builds the service, and returns an Any the checker cannot see through
def get_task_service(request: Request) -> TaskService:
    return TaskService(PostgresTaskRepository(request.state.pool))


# CORRECT — an async accessor to what the lifespan built, typed once, named once
async def get_task_service(request: Request) -> TaskService:
    service: TaskService = request.state.task_service
    return service


type TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
```

### A dependency with `yield` releases in `finally`

**Why:** without `try`/`finally` the release after `yield` is skipped when the route raises, and
whatever the dependency acquired — a scratch directory, a lease — is never released. A dependency
cached for the life of the app is a lazy singleton — it belongs in the lifespan.

## Routers

### A route parses, calls one service method, and builds the response

**Why:** anything else in a route's body is a service method that has not been written yet, and a
rule there is reachable only through HTTP. The domain and the services never import `fastapi`.
Authentication is declared once, on the router holding the protected routes, with the public ones —
the health probes among them (`python-container`) — on a router of their own.

**Example:**
```python
# WRONG — the route decides: the closing rule is reachable only through HTTP
@tasks_router.post("/tasks/{task_id}/close")
async def close_task(task_id: TaskId, tasks: TaskServiceDep) -> TaskResponse:
    task = await tasks.get_task(task_id)
    if task.open_subtasks:
        raise HTTPException(status.HTTP_409_CONFLICT, f"task {task_id} has open subtasks")
    closed = await tasks.save_task(replace(task, status=TaskStatus.CLOSED))
    return TaskResponse.from_domain(closed)


# CORRECT — parse, call one service method, build the response; the rule lives in the service
@tasks_router.post("/tasks/{task_id}/close")
async def close_task(task_id: TaskId, tasks: TaskServiceDep) -> TaskResponse:
    return TaskResponse.from_domain(await tasks.close_task(task_id))
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

### The response is an explicit model built from the domain object

**Why:** a route annotated `-> Task` makes the domain type the response model, and every field it
has is published — one added attribute is one leaked field (`python-boundaries`). An explicit
`response_model=` over a returned domain object drops extras, but maps by attribute name, out of
sight; `from_domain` states the mapping.

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
async def _tracker_error_response(request: Request, error: Exception) -> JSONResponse:
    status_code = HTTPStatus.NOT_FOUND if isinstance(error, LookupError) else HTTPStatus.CONFLICT
    return JSONResponse({"detail": str(error)}, status_code=status_code)


# CORRECT — the classified errors map to a status; the rest re-raise and the server answers 500
_CLIENT_STATUS_BY_ERROR: Final[Mapping[type[TrackerError], HTTPStatus]] = MappingProxyType(
    {
        TaskNotFoundError: HTTPStatus.NOT_FOUND,
        TaskHasOpenSubtasksError: HTTPStatus.CONFLICT,
    }
)


async def _tracker_error_response(request: Request, error: Exception) -> JSONResponse:
    for error_type in type(error).__mro__:
        status_code = _CLIENT_STATUS_BY_ERROR.get(error_type)
        if status_code is not None:
            return JSONResponse({"detail": str(error)}, status_code=status_code)
    raise error
```

### `BackgroundTasks` carry only work whose loss nobody notices

**Why:** they run in the same process after the response is sent; a restart loses them and nothing
retries them. Work that must happen goes through an outbox or a queue (`python-persistence`,
`python-workers`).

**Example:**
```python
# WRONG — the assignment email is lost whenever the worker restarts after the response
@tasks_router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: TaskId, assignee: AssigneeRequest, tasks: TaskServiceDep, background: BackgroundTasks
) -> TaskResponse:
    task = await tasks.assign(task_id, assignee.user_id)
    background.add_task(tasks.notify_assignee, task)
    return TaskResponse.from_domain(task)


# CORRECT — the service writes the notification to its outbox in the same transaction
@tasks_router.post("/tasks/{task_id}/assign")
async def assign_task(
    task_id: TaskId, assignee: AssigneeRequest, tasks: TaskServiceDep
) -> TaskResponse:
    return TaskResponse.from_domain(await tasks.assign(task_id, assignee.user_id))
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

**Before writing the uvicorn command, read [serving.md](serving.md)** — the drain bounded below the
grace period, and `--forwarded-allow-ips` set to the proxy's network behind one.

## With Other Libraries

**Before using SQLAlchemy in a FastAPI app, read [with-sqlalchemy.md](with-sqlalchemy.md)** — the
engine and a `partial` service factory in the lifespan, a session per request on
`scope="function"`, the service commits.

**Before running a gRPC server beside a FastAPI app, read [with-grpc.md](with-grpc.md)** — the
server entered in the lifespan, under one worker.

**Before mounting a strawberry GraphQL app in FastAPI, read
[with-strawberry.md](with-strawberry.md)** — the context getter as an authenticating dependency, on
`HTTPConnection`.

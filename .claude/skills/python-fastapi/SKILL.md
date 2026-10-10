---
name: python-fastapi
description: >-
  FastAPI practice reconciled with the composition-root rules: an application factory and a lifespan
  that build and close every shared resource, Depends as a thin accessor to what the lifespan built
  rather than a service locator or a per-request constructor, settings passed to the factory instead
  of an lru_cache getter, Annotated dependency aliases, routers that translate HTTP and nothing
  more, authentication declared once on the protected router, only classified domain errors answered
  as 4xx and everything else as a bare 500, explicit response models, sync def versus async def
  routes, BackgroundTasks limits, and testing with the lifespan running — through TestClient, or an
  async client and LifespanManager in async tests. Use when Python code imports fastapi or
  starlette, defines a route, a router, a dependency, a lifespan or an exception handler, or tests
  an ASGI app.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# FastAPI

Checked against FastAPI 0.143 and Starlette 1.7. Construction, lifetime and layering are in
`python-wiring`; request and response models are `python-pydantic` — and a strict body model
relaxes its `datetime`, `UUID` and `Decimal` fields by name, or every valid payload is a 422 (why
and how: `python-pydantic`). This file is where FastAPI's own mechanisms meet those rules —
chiefly `Depends`, which looks like dependency injection and is used, in most tutorials, as a
service locator.

## The Factory Is the Composition Root, the Lifespan Owns Lifetime

- **`create_app(settings) -> FastAPI`, and nothing built at import time.** A module-level
  `app = FastAPI()` whose engine is created beside it is the global singleton `python-wiring`
  forbids. Serve the factory: `uvicorn --factory shop.api:create_app`, or an `asgi.py` whose one
  statement is `app = create_app(Settings())`.
- **The `lifespan` builds every shared resource once and closes it**: one `async with` with an
  item per resource — the engine, the HTTP client — the services built from them inside, and a
  mapping of what requests need yielded; Starlette puts it on `request.state`. The items close in
  reverse order on shutdown.
  `@app.on_event("startup")` is the deprecated shape of the same thing, and a startup and shutdown
  hook pair is the fragile one: the release sits apart from the acquire and runs in registration
  order, not in reverse. A plugin that put its engine into app state at construction and deleted it
  at shutdown failed the second test that ran the same app's lifespan, with a `KeyError`.
- **A gRPC server beside the app is started and drained in the same lifespan**, and the app then
  runs one worker: every worker runs the lifespan, so a second server fails to bind — or, with
  grpc's reuse-port default, silently shares the port (`python-grpc`).
- **Settings are built once, by whoever calls the factory, and passed in.** The documentation's
  `@lru_cache def get_settings()` behind `Depends` is a module-level singleton with extra steps: the
  test that needs another value has to clear a cache.

## `Depends` Is an Accessor, Not a Constructor

`python-wiring` allows request-scoped objects built per request by an explicitly passed factory.
`Depends` is that factory, under three conditions:

- **It reads, it does not build what outlives the request.** A dependency returns what the lifespan
  built, or builds a request-scoped object — a unit of work — from those parts. An engine, a pool or
  a client constructed inside a dependency is constructed per request.
- **A dependency with `yield` wraps the `yield` in `try`/`finally`**, so the release runs when the
  route raises too; and a dependency cached for the life of the app is a lazy singleton — it belongs
  in the lifespan.
- **It holds no business logic and reads no settings.** It is the seam between FastAPI and the
  service, three lines at most.
- **An accessor is `async def`.** A plain `def` dependency runs in the thread pool on every request,
  and an accessor that only reads `request.state` pays a thread hop for an attribute lookup. A
  dependency that blocks is not an accessor and stays a plain `def` — a token verifier whose key
  set fetch is blocking `urllib` is the usual one (`python-pyjwt`).
- **It is named once, as an `Annotated` alias**, so every route states the type it receives and the
  checker sees a real class rather than the result of a call.

`request.state` is untyped, and FastAPI does not accept a `Request` parameterised with a typed
state. The accessor states the type once, on an annotated local — returning the attribute directly
is `no-any-return` under `mypy --strict` — and nothing past it sees `Any`. No runtime check: the
lifespan a few lines away is what put the service there.

```python
# WRONG — a cached global for settings, and an engine built on every request
@lru_cache
def get_settings() -> Settings:
    return Settings()


def order_service(settings: Annotated[Settings, Depends(get_settings)]) -> OrderService:
    return OrderService(PostgresOrderRepository(create_async_engine(settings.database_url)))


# CORRECT — the factory's lifespan builds once; the dependency only hands it over
def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_engine(settings.database_url) as engine:
            yield {"order_service": OrderService(PostgresOrderRepository(engine))}

    app = FastAPI(lifespan=lifespan)
    app.include_router(orders_router)
    app.add_exception_handler(ShopError, _shop_error_response)
    return app


async def get_order_service(request: Request) -> OrderService:
    service: OrderService = request.state.order_service
    return service


type OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
```

## Routers Translate, Services Decide

- **Authentication is declared once, on the router that holds the protected routes** —
  `APIRouter(dependencies=[Depends(require_user)])` — and the public routes live on a router of
  their own, which is the allowlist a review reads — the health probes among them, whose liveness
  and readiness questions are in `python-container`. A dependency added route by route is forgotten
  on the one route that mattered. That dependency answers every rejected token 401 with one fixed
  body, and an unreachable key set 503, never 401 (why and how: `python-auth`).

- **A route parses, calls one service method, and builds the response.** Anything else in its body
  is a service method that has not been written yet. The domain and the services never import
  `fastapi`.

```python
# WRONG — the route decides: the refund rule is reachable only through HTTP
@orders_router.post("/orders/{order_id}/refund")
async def refund_order(order_id: OrderId, orders: OrderServiceDep) -> OrderResponse:
    order = await orders.get_order(order_id)
    if order.status is not OrderStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Order {order_id} is not paid")
    refunded = await orders.save_order(replace(order, status=OrderStatus.REFUNDED))
    return OrderResponse.from_domain(refunded)


# CORRECT — parse, call one service method, build the response; the rule lives in the service
@orders_router.post("/orders/{order_id}/refund")
async def refund_order(order_id: OrderId, orders: OrderServiceDep) -> OrderResponse:
    return OrderResponse.from_domain(await orders.refund_order(order_id))
```

- **The response is an explicit model built from the domain object** —
  `OrderResponse.from_domain(order)` — with the return annotation as the response model. A route
  annotated `-> Order` makes the domain type the response model, and then every field it has is
  published — one added attribute is one leaked field, the accidental serialization
  `python-boundaries` forbids. Returning the domain object under an explicit
  `response_model=OrderResponse` does drop the extra fields, but the mapping then happens by
  attribute name, out of sight; `from_domain` states it.

```python
# WRONG — the domain dataclass is the response model: every field added to Order is published
@orders_router.get("/orders/{order_id}")
async def get_order(order_id: OrderId, orders: OrderServiceDep) -> Order:
    return await orders.get_order(order_id)


# CORRECT — an explicit response model, built from the domain object
@orders_router.get("/orders/{order_id}")
async def get_order(order_id: OrderId, orders: OrderServiceDep) -> OrderResponse:
    return OrderResponse.from_domain(await orders.get_order(order_id))
```

- **A route that streams** — a generator under `EventSourceResponse`, a `StreamingResponse`, a
  WebSocket — lives for minutes instead of milliseconds: it releases what it holds in `finally` and
  never holds a database session while it waits (why and how: `python-streaming`).
- **A GraphQL endpoint** — strawberry's `GraphQLRouter` — is `python-strawberry`.
- **Domain errors are mapped to status codes in one exception handler**, registered by the factory
  on the package's root error. `HTTPException` is raised by routes only, for failures that exist
  only in HTTP; a service that raises it has learned about the transport.

```python
# WRONG — the service imports fastapi, and a CLI or a worker calling it gets an HTTP error
@final
class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def get_order(self, order_id: OrderId) -> Order:
        order = await self._repository.find(order_id)
        if order is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Order {order_id} not found")
        return order


# CORRECT — the service raises the domain error, and the one handler below maps it to 404
@final
class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    async def get_order(self, order_id: OrderId) -> Order:
        order = await self._repository.find(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order
```

- **Only an error classified as the client's gets a 4xx and its message.** Everything else —
  an upstream that failed, a bug — is a 500 with a fixed body, and its detail goes to the log, never
  to the client: an unclassified message carries hostnames, ids and internals.

```python
# WRONG — every unclassified failure becomes a 409 that tells the client what broke inside
async def _shop_error_response(request: Request, error: Exception) -> JSONResponse:
    is_missing = isinstance(error, LookupError)
    status_code = HTTPStatus.NOT_FOUND if is_missing else HTTPStatus.CONFLICT
    return JSONResponse({"detail": str(error)}, status_code=status_code)


# CORRECT — the classified errors map to a status; the rest re-raise and the server answers 500
_CLIENT_STATUS_BY_ERROR: Final[Mapping[type[ShopError], HTTPStatus]] = MappingProxyType(
    {
        OrderNotFoundError: HTTPStatus.NOT_FOUND,
        OrderAlreadyShippedError: HTTPStatus.CONFLICT,
    }
)


async def _shop_error_response(request: Request, error: Exception) -> JSONResponse:
    for error_type in type(error).__mro__:
        status_code = _CLIENT_STATUS_BY_ERROR.get(error_type)
        if status_code is not None:
            return JSONResponse({"detail": str(error)}, status_code=status_code)
    raise error
```

The handler takes `Exception` because Starlette's signature does, and walks the error's MRO so a
subclass of a mapped error is mapped too. A handler that recognised its own errors by a
`status_code` attribute once put any third-party exception's message into the response.

## `def` and `async def` Routes

- **`async def` only when everything inside is awaited.** One blocking call — a sync driver, a
  `requests` call, a large file read — inside an `async def` route stops every other request on
  the worker (`python-async`).

```python
# WRONG — a blocking call inside async def: every other request on the worker waits for it
@reports_router.get("/reports/{report_id}")
async def get_report(report_id: ReportId, reports: ReportServiceDep) -> ReportResponse:
    return ReportResponse.from_domain(reports.build_report(report_id))


# CORRECT — a plain def runs in the thread pool, and the event loop keeps serving
@reports_router.get("/reports/{report_id}")
def get_report(report_id: ReportId, reports: ReportServiceDep) -> ReportResponse:
    return ReportResponse.from_domain(reports.build_report(report_id))
```

- **A plain `def` route or dependency runs in a thread pool**, which is correct for blocking code
  and bounded: under load, requests queue for a thread. Pick per route by what it calls, not by
  habit. A strawberry `def` resolver gets no thread pool: it runs on the event loop
  (`python-strawberry`).
- **`BackgroundTasks` run in the same process after the response is sent.** A restart loses them
  and nothing retries them, so they suit work whose loss nobody notices. Anything that must happen
  goes through an outbox or a queue (`python-persistence`, `python-workers`).

## Testing

- **Use `TestClient` as a context manager.** `with TestClient(app) as client:` runs the lifespan;
  without the `with`, nothing the lifespan builds exists and the first dependency fails.

```python
# WRONG — no with: the lifespan never runs, and request.state has no order_service
def test_get_order_returns_404_for_unknown_order(app: FastAPI) -> None:
    client = TestClient(app)

    response = client.get("/orders/42")

    assert response.status_code == HTTPStatus.NOT_FOUND


# CORRECT — the with block runs the lifespan on entry and closes what it built on exit
def test_get_order_returns_404_for_unknown_order(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/orders/42")

    assert response.status_code == HTTPStatus.NOT_FOUND
```

- **`TestClient` is built on `httpx2`, which goes in the test dependencies.** Starlette 1.7 still
  falls back to `httpx`, with a `StarletteDeprecationWarning` that `filterwarnings = ["error"]`
  turns into a collection error; `httpx2` also has the `AsyncClient` and `ASGITransport` below.
- **An async test uses an async client.** The sync `TestClient` runs the app on an event loop of
  its own, and a connection an async fixture opened on the test's loop fails there. Run the
  lifespan with `asgi-lifespan`'s `LifespanManager` and send requests through `manager.app`, which
  carries the lifespan state; `ASGITransport` alone runs no lifespan.

```python
async def test_get_order_returns_404_for_unknown_order() -> None:
    app = create_app(_TEST_SETTINGS)
    async with (
        LifespanManager(app) as manager,
        AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as client,
    ):
        response = await client.get("/orders/42")

    assert response.status_code == HTTPStatus.NOT_FOUND
```

- **The test root is the factory or `app.dependency_overrides`.** Override the accessor with one
  returning a service built on in-memory fakes — `app.dependency_overrides[get_order_service] =
  lambda: OrderService(InMemoryOrderRepository())` — never patch a module. When the overrides
  multiply, let `create_app` take the lifespan's builder as a parameter, and pass the fakes'
  builder from the tests.
- **Routes are tested through HTTP**, asserting the status and the body; the service behind them is
  tested directly, without FastAPI.

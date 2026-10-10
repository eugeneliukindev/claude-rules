---
name: python-grpc
description: >-
  gRPC in Python with grpcio's asyncio API: grpc.aio servers and channels, stubs from grpcio-tools
  typed by mypy-protobuf and types-grpcio, protobuf messages kept at the edge behind explicit
  converters, proto3 presence and HasField, the UNSPECIFIED enum zero, Timestamp to an aware
  datetime, domain errors mapped to status codes in one interceptor and everything else INTERNAL,
  a deadline on every call, retryPolicy in the service config, the server built and drained by the
  composition root in FastAPI's lifespan or its own process, health checking, reflection, message
  size, TLS and call credentials, grpcio-observability and OpenTelemetry, streaming cancellation,
  tests on an in-process server, reserved field numbers and buf breaking, and which protobuf and
  pydantic bridges exist. Use when Python code imports grpc, grpc.aio, grpc_tools or a _pb2 or
  _pb2_grpc module, implements a servicer, calls a gRPC service, or edits a .proto file.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/*.proto"
---

# gRPC

Checked against grpcio, grpcio-tools, grpcio-health-checking, grpcio-status, grpcio-reflection and
grpcio-observability 1.84, protobuf 7.36, mypy-protobuf 5.1, types-grpcio 1.84, buf 1.73, FastAPI
0.143 and uvicorn 0.54, on Python 3.13. Validate at the edge, give every call a deadline, retry only
transient failures and only idempotent writes, keep time aware UTC and money `Decimal` (why:
`python-boundaries`); the composition root builds and closes every resource (`python-wiring`);
shutdown drains with a deadline, then closes in reverse (`python-async`); the grace period and the
probes are `python-container`. A script that calls a gRPC service once still sets a deadline and
verifies TLS (`python-scripts`).

## FastAPI, pydantic and the Libraries Between Them

No maintained library joins `grpc.aio` to FastAPI, or messages to pydantic models, in a way these
rules can use. What exists:

| Library | What it does | Why it is not used here |
|---|---|---|
| `protobuf-to-pydantic` 0.3.3.1, last release June 2025 | pydantic models generated from messages | its runtime mode raises `AttributeError` on protobuf 7; its plugin defaults a missing `Timestamp` to the naive `datetime.now` and an `optional` string to `""` |
| `betterproto2` 0.10 | its own message runtime, optionally pydantic dataclasses | async clients and servers run on `grpclib`, not `grpc.aio`; its README says it is still subject to breaking changes |
| `pydantic-rpc` 0.15 | a gRPC or Connect service built from pydantic models, with no `.proto` | the schema is derived from Python code, so the contract other languages compile has no file of its own to review or check with buf |
| `connectrpc` 0.12 | Connect, gRPC and gRPC-Web as an ASGI app beside FastAPI | in beta by its own documentation; its gRPC protocol needs an HTTP/2 server, and uvicorn speaks HTTP/1.1 |
| `grpc-gateway`, `fastgrpc` on PyPI | REST-to-gRPC bridges | one release each, in 2023 and 2021 |

The maintained REST-to-gRPC gateway is the Go project `grpc-ecosystem/grpc-gateway`, run as a
process of its own. Inside one Python service, the answer is plainer:

- **A FastAPI route and a gRPC servicer are two adapters over the same service.** The route parses
  with pydantic (`python-fastapi`), the servicer with the generated message; each converts to the
  same domain objects and calls the same method. Neither calls the other: a servicer that calls
  the route, or a route that calls the stub of its own process, serializes twice and fails twice.
- **pydantic has no job on the gRPC side.** The message already parses the wire. What it does not
  check — a UUID's format, a positive quantity, a known enum value — the converter checks, raising
  an error the interceptor answers `INVALID_ARGUMENT`. When the same constraints must hold in every
  language that compiles the schema, declare them in the `.proto` with `protovalidate` (2.0):
  `protovalidate.validate(message)` raises `ValidationError`.
- **Never reach a pydantic model through `MessageToDict`.** It renames fields to lowerCamelCase,
  drops every field at its default and writes `int64` as a string; a strict model rejects the
  result, and a lax one guesses.

```python
# WRONG — the HTTP model reused through a dict: camelCase keys, defaults dropped, int64 as strings
order_id = GetOrderQuery.model_validate(MessageToDict(request)).order_id
# CORRECT — the field read from the message; the converter checks it is a UUID
order_id = order_id_from_wire(request.order_id)
```

## Generated Code Is the Wire Layer

- **Messages never reach the service.** The servicer converts the request into domain values, calls
  one service method and converts the result; a service that takes `GetOrderRequest` has learned
  the transport, and a worker or a test must build a message to call it.

```python
# WRONG — the service receives the wire message, and every other caller must build one
@override
async def GetOrder(
    self, request: orders_pb2.GetOrderRequest, context: _GetOrderContext
) -> orders_pb2.GetOrderResponse:
    return orders_pb2.GetOrderResponse(order=await self._orders.get_order(request))

# CORRECT — converted at the edge; the service sees an OrderId and returns an Order
@override
async def GetOrder(
    self, request: orders_pb2.GetOrderRequest, context: _GetOrderContext
) -> orders_pb2.GetOrderResponse:
    order = await self._orders.get_order(order_id_from_wire(request.order_id))
    return orders_pb2.GetOrderResponse(order=order_to_wire(order))
```

- **A converter names every field, in one function per direction** — the splat rule in
  `python-boundaries` holds for messages too. The servicer inherits the generated
  `OrderServiceServicer`, an ABC, so `@override` and `@final` apply as to any implementation.

What proto3 does with a value is not what Python does:

- **A scalar without `optional` has no presence.** An unset string reads `""` and an unset number
  `0`; nothing tells "not sent" from "sent empty". Declare the field `optional` when absence means
  something, and read it with `HasField`: `message.note if message.HasField("note") else None`.
  Passing `note=None` to the constructor leaves it unset.
- **A message field is never `None`.** An unset `placed_at` reads as an empty `Timestamp`, which
  converts to 1970-01-01. Ask `HasField` first.
- **`Timestamp.ToDatetime()` is naive**; `ToDatetime(tzinfo=UTC)` is aware. `FromDatetime` takes
  a naive value as UTC without complaint. `Duration` has `ToTimedelta` and `FromTimedelta`.

```python
# WRONG — an order sent without placed_at arrives as 1970-01-01, and naive
def _placed_at_from_wire(message: orders_pb2.Order) -> datetime:
    return message.placed_at.ToDatetime()

# CORRECT — absence is the upstream's error, and the instant is aware UTC
def _placed_at_from_wire(message: orders_pb2.Order) -> datetime:
    if not message.HasField("placed_at"):
        raise PermanentOrdersUpstreamError(f"Order {message.order_id} has no placed_at")
    return message.placed_at.ToDatetime(tzinfo=UTC)
```

- **An enum's zero is `*_UNSPECIFIED`** and means "not set", never a real state. Enums are open: a
  value this build does not know arrives as a plain `int` and is kept. Convert through a mapping
  from wire value to domain member, and reject what the mapping lacks.
- **`int64` is a Python `int`**, range-checked on assignment; its JSON mapping is a string. **Money
  is never `double`**: a decimal string, or units plus nanos as in `google.type.Money`; identifiers
  travel as their canonical string (`python-boundaries`).

## Generating and Typing the Code

```bash
uv run python -m grpc_tools.protoc -I proto \
    --python_out=src --grpc_python_out=src --mypy_out=src --mypy_grpc_out=src \
    proto/shopapis/orders/v1/orders.proto
```

- **mypy-protobuf, not `--pyi_out`.** `--pyi_out` types the messages only: no service stubs, and
  `HasField` accepts any string. mypy-protobuf's `--mypy_out` types `HasField` with the fields that
  have presence, and `--mypy_grpc_out` types servicers and stubs: `OrderServiceStub(channel)` on a
  `grpc.aio` channel is an `OrderServiceAsyncStub`. The dev group holds `mypy-protobuf`,
  `types-protobuf`, `types-grpcio` and, per companion package used, `types-grpcio-health-checking`
  or `types-grpcio-status`. `grpc-stubs` was archived in April 2025; mypy-protobuf 4 moved to
  typeshed's `types-grpcio`.
- **The stubs are ahead of the runtime and behind it.** `types-grpcio` makes `RpcMethodHandler`
  generic, which the runtime class is not: below Python 3.14 a signature that subscribes it raises
  `TypeError` at import unless the module has `from __future__ import annotations`. The health
  stubs lack `grpc_health.v1.health.aio` and every method of `HealthStub`: the one import or call
  carries `# type: ignore[attr-defined]` and its reason.
- **The directory below `-I` is the import path.** Generated modules import each other by it
  (`from shopapis.orders.v1 import orders_pb2`), and protoc writes no `__init__.py`. Give the tree a
  top-level name no hand-written package has: generated `shop/orders/v1` beside an application
  package `shop` is shadowed by it, and the import fails with `ModuleNotFoundError`.
- **Generated code pins its runtime floor.** `_pb2_grpc.py` raises `RuntimeError` on import when
  the installed `grpcio` is older than the `grpcio-tools` that generated it, and `_pb2.py` refuses
  a `protobuf` older than its generator. Declare `grpcio>=` and `protobuf>=` at the generator's
  versions, and bump the generator only with them.
- **Checked in or generated by the build — decided once.** Checked in, CI regenerates and fails on
  `git diff --exit-code`. Either way the files are never edited, and the linters skip them.

## The Server

**The composition root builds, starts, drains and stops it, in one context manager**
(`python-wiring`):

```python
_MAX_MESSAGE_BYTES: Final = 4 * 1024 * 1024
_ORDER_SERVICE_NAME: Final = orders_pb2.DESCRIPTOR.services_by_name["OrderService"].full_name


@asynccontextmanager
async def managed_grpc_server(
    orders: OrderService,
    *,
    address: str,
    credentials: grpc.ServerCredentials,
    grace_seconds: float,
) -> AsyncIterator[int]:
    server = grpc.aio.server(
        interceptors=[StatusInterceptor()],
        options=[
            ("grpc.so_reuseport", 0),
            ("grpc.max_receive_message_length", _MAX_MESSAGE_BYTES),
            ("grpc.max_send_message_length", _MAX_MESSAGE_BYTES),
        ],
    )
    orders_pb2_grpc.add_OrderServiceServicer_to_server(OrderServicer(orders), server)
    health = health_aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health, server)
    port = server.add_secure_port(address, credentials)
    await server.start()
    await health.set(_ORDER_SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
    try:
        yield port
    finally:
        await health.enter_graceful_shutdown()
        await server.stop(grace_seconds)
```

- **`stop` refuses new calls at once; the grace is what the calls in flight get.** With a grace it
  waits for them and then cancels the rest, which reach the client as `UNAVAILABLE` "Cancelling
  all calls" and the handler as `CancelledError`. `stop(None)` aborts them all immediately.
  Measured: a 0.3-second call finished under a 2-second grace, and failed under none. The grace
  fits inside the orchestrator's period with room to close the pools (`python-workers`).

```python
await server.stop(None)  # WRONG — every call in flight aborted the moment shutdown begins
await server.stop(grace_seconds)  # CORRECT — the calls in flight get the grace to finish
```

- **`grpc.so_reuseport` is on by default**, so a second server binds the same port without an
  error and the kernel splits connections between the two — a stale process keeps a share of the
  traffic. Measured both ways: on, the second bind succeeded; off, it raised `RuntimeError`.
- **Messages are capped at 4 MiB on the receiving side** in both directions, and a larger one fails
  as `RESOURCE_EXHAUSTED` "Received message larger than max". Set the limit as a named constant on
  the server and on the client's channel; past a few MiB, stream the payload in chunks.
- **`maximum_concurrent_rpcs=` bounds the calls in flight**; past it the server answers
  `RESOURCE_EXHAUSTED`. The default is no limit.
- **The port is TLS** — `grpc.ssl_server_credentials([(private_key, certificate_chain)])` — unless
  a mesh sidecar terminates TLS inside the pod; there `add_insecure_port` on the pod address is the
  one exception, and a setting names it. Tests use `grpc.local_server_credentials()`.

### Beside FastAPI, or on Its Own

- **In the lifespan**: one process, one deploy, one shutdown. Measured under uvicorn: on
  `SIGTERM`, new gRPC calls were refused with `UNAVAILABLE`, the call in flight finished inside the
  grace, and the process exited 0. **It needs one worker**: every uvicorn worker runs the lifespan,
  and with `--workers 2` the second failed to bind and uvicorn stopped — with the reuse-port default
  it would have shared the port silently.

```python
def create_app(settings: Settings) -> FastAPI:
    grpc_credentials = grpc.ssl_server_credentials(
        [(settings.grpc_private_key.get_secret_value(), settings.grpc_certificate_chain)]
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_engine(settings.database_url) as engine:
            orders = OrderService(PostgresOrderRepository(engine), PostgresOrderFeed(engine))
            async with managed_grpc_server(
                orders,
                address=settings.grpc_address,
                credentials=grpc_credentials,
                grace_seconds=settings.grpc_grace_seconds,
            ):
                yield {"order_service": orders}

    app = FastAPI(lifespan=lifespan)
    app.include_router(orders_router)
    return app
```

- **In a process of its own** when the gRPC side scales apart from HTTP, or HTTP runs several
  workers: a second entry point in the same image, `asyncio.run(main())` with `SIGTERM` and
  `SIGINT` handled so the server drains before it closes (why and how: `python-async`), run as a
  second container (`python-container`). The context manager above is the same in both.

### Health, Reflection, Telemetry

- **The health service is push, not pull.** `HealthServicer()` reports `""` as `SERVING` from
  construction, a named service as `NOT_FOUND` until `set`, and `enter_graceful_shutdown()` turns
  every one `NOT_SERVING` and ignores later `set`s. Nothing is computed per check: readiness that
  depends on a database is a task that sets the service's status; `""` answers liveness
  (`python-container`).
- **Kubernetes probes it natively** — `grpc: {port: 50051, service: ...}`, stable since 1.27 — with
  a numeric port only, in plaintext unless `mode: TLS`, which skips verification and needs a feature
  gate, against the pod's address, so the server listens there rather than on `127.0.0.1`.
- **Reflection publishes the whole schema to whoever connects.**
  `reflection.enable_server_reflection((_ORDER_SERVICE_NAME, reflection.SERVICE_NAME), server)`
  from `grpcio-reflection` goes behind a setting that is off wherever policy says so.
- **Traces come from `opentelemetry-instrumentation-grpc`** — `aio_server_interceptor()`,
  `aio_client_interceptors()` — which records no metrics. **Metrics come from
  `grpcio-observability`**: `OpenTelemetryPlugin(meter_provider=...)` and `register_global()` in the
  entry point, which recorded `grpc.server.call.duration` and `grpc.client.attempt.duration` with
  `grpc.method` and `grpc.status` attributes. It is process-wide, so only the entry point registers
  it (`python-observability`).
- **Cross-cutting work is an interceptor, declared once on the server.** A value an interceptor
  puts in a `ContextVar` — the request id from `invocation_metadata` — was visible in the handler.
  Authentication is the same: one interceptor that rejects with `UNAUTHENTICATED`, with health and
  reflection on its allowlist; verifying the token is `python-auth`.

## Errors

**An exception that escapes a handler reaches the client with its message**: `UNKNOWN`, details
`Unexpected <class 'ValueError'>: ` and whatever the message held — a hostname and a user name, in
the run that measured it. So one interceptor maps the classified errors to codes and turns
everything else into `INTERNAL` with a fixed text, logged once — the gRPC form of the exception
handler in `python-fastapi`. The servicer never calls `context.abort` itself, and a method added
next year is covered without anyone remembering to. The whole module, unary and streaming, is in
[interceptors.md](interceptors.md); the decision it carries is one table:

```python
_CODE_BY_ERROR: Final[Mapping[type[Exception], grpc.StatusCode]] = MappingProxyType(
    {
        InvalidRequestError: grpc.StatusCode.INVALID_ARGUMENT,
        OrderNotFoundError: grpc.StatusCode.NOT_FOUND,
        OrderAlreadyShippedError: grpc.StatusCode.FAILED_PRECONDITION,
    }
)
_INTERNAL_DETAILS: Final = "internal error"
```

- **`context.abort` raises `AbortError`, an `Exception`.** A boundary that catches `Exception` lets
  it through first; otherwise the client still gets the aborted code, but every deliberate abort is
  logged at `ERROR` as a failed RPC.
- **The mapping walks the error's MRO**, so a subclass of a mapped error is mapped too; anything
  unmapped is logged with its traceback and answered with the fixed text:

```python
# WRONG — the unclassified error's message is the client's to read
async def _abort_with_status(context: _Context, error: Exception) -> Never:
    for error_type in type(error).__mro__:
        code = _CODE_BY_ERROR.get(error_type)
        if code is not None:
            await context.abort(code, str(error))
    await context.abort(grpc.StatusCode.INTERNAL, str(error))

# CORRECT — the client gets a fixed text; the traceback goes to the log, once
async def _abort_with_status(context: _Context, error: Exception) -> Never:
    for error_type in type(error).__mro__:
        code = _CODE_BY_ERROR.get(error_type)
        if code is not None:
            await context.abort(code, str(error))
    logger.error("rpc failed", exc_info=error)
    await context.abort(grpc.StatusCode.INTERNAL, _INTERNAL_DETAILS)
```

- **The code says what the client can do about it.** `INVALID_ARGUMENT`: the request is wrong
  whatever the state. `FAILED_PRECONDITION`: the state forbids it — the order is already shipped.
  `NOT_FOUND`; `ALREADY_EXISTS` for a create that collides. `UNAUTHENTICATED` versus
  `PERMISSION_DENIED` as 401 versus 403 (`python-auth`). `UNAVAILABLE` only for "try again", since
  clients retry it — never for a domain error. `UNKNOWN` never on purpose.
- **Field-level detail travels as a `google.rpc.Status`** when a client acts on it: pack a
  `BadRequest` into `status_pb2.Status(...).details`, abort with
  `context.abort_with_status(rpc_status.to_status(status))`, and read it back with
  `rpc_status.from_call(error)` — `grpcio-status`, verified round trip.

## The Client

- **One channel per target, built by the root and closed with it** — `async with
  grpc.aio.secure_channel(target, credentials, options=...)` — shared by every stub. A channel per
  call pays a connection and a TLS handshake each time.
- **Every call carries `timeout=`.** gRPC has no default deadline: measured, a call to a stalled
  handler was still waiting after a second, with `time_remaining()` `None`. The deadline reaches
  the server, which cancelled the handler when it passed. Serving one call while making another,
  pass the smaller of your own timeout and `context.time_remaining()`, which is `None` when the
  caller set no deadline.
- **Status codes are translated at the adapter**, like any upstream error (`errors.md`):
  `NOT_FOUND` into the domain's error, `UNAVAILABLE` and `DEADLINE_EXCEEDED` into the transient
  type, everything else permanent — `RESOURCE_EXHAUSTED` included, which is also a message over the
  size limit. `AioRpcError.details()` is `str | None`.

```python
# WRONG — AioRpcError escapes, and every caller has to know gRPC to tell a 404 from an outage
@override
async def fetch_order(self, order_id: OrderId) -> Order:
    request = orders_pb2.GetOrderRequest(order_id=str(order_id))
    response = await self._stub.GetOrder(request, timeout=self._timeout_seconds)
    return _order_from_wire(response.order)

# CORRECT — the status is translated here, with the cause kept
@override
async def fetch_order(self, order_id: OrderId) -> Order:
    request = orders_pb2.GetOrderRequest(order_id=str(order_id))
    try:
        response = await self._stub.GetOrder(request, timeout=self._timeout_seconds)
    except grpc.aio.AioRpcError as error:
        raise _translate_status(error, order_id) from error
    return _order_from_wire(response.order)
```

- **Retries live in the service config, for the methods that are idempotent, on `UNAVAILABLE`.**
  Without a config nothing is retried; with one, the server saw attempts one to three and the
  deadline covered all of them. `DEADLINE_EXCEEDED` is never retryable: the budget is spent and the
  server may have done the work. This is the one retry layer for the call — no tenacity around it
  (`python-boundaries`, `python-tenacity`); the opposite choice turns it off with
  `("grpc.enable_retries", 0)`.

```python
# WRONG — every method, so a write cut off by a stopping server after its commit runs twice
_RETRIED_METHODS: Final = ({"service": "shopapis.orders.v1.OrderService"},)

# CORRECT — the reads, named one by one
_RETRIED_METHODS: Final = ({"service": "shopapis.orders.v1.OrderService", "method": "GetOrder"},)

_SERVICE_CONFIG: Final = json.dumps(
    {
        "methodConfig": [
            {
                "name": _RETRIED_METHODS,
                "retryPolicy": {
                    "maxAttempts": 3,
                    "initialBackoff": "0.2s",
                    "maxBackoff": "2s",
                    "backoffMultiplier": 2,
                    "retryableStatusCodes": ["UNAVAILABLE"],
                },
            }
        ]
    }
)
```

  The channel takes it as `options=[("grpc.service_config", _SERVICE_CONFIG)]`. It is also what
  absorbs the `UNAVAILABLE` a server answers between `SIGTERM` and its removal from the load
  balancer.
- **Keepalive is off on clients by default, and the server decides how often it may be pinged** —
  by default no more than every five minutes without data. A client that pings more often is sent
  `GOAWAY` with `too_many_pings`, as gRPC's keepalive guide documents. Set
  `grpc.keepalive_time_ms` no lower than about a minute, agreed with the service's owners.
- **TLS verifies the target's name.** `grpc.ssl_channel_credentials(root_certificates=ca_pem)` for
  a private CA; measured, the same certificate was accepted as `localhost` and refused as
  `127.0.0.1`. Never `grpc.ssl_target_name_override` to make it pass. `insecure_channel` is for
  loopback and tests; `grpc.local_channel_credentials()` covers both and allows call credentials.
- **Per-call credentials need a secure channel.** `grpc.access_token_call_credentials(token)`,
  composed with `grpc.composite_channel_credentials`, sends `authorization: Bearer ...`; on an
  insecure channel the call raised `UsageError`. The token is the service's own (`python-auth`).

## Streaming RPCs

The rules for long-lived responses are `python-streaming`'s; what gRPC adds:

- **A server-streaming handler suspended at `yield` is closed, not cancelled**, when the client
  cancels or the deadline passes: measured, its `except CancelledError` never ran and its `finally`
  did. Everything it holds is released in `finally` or by `async with`.

```python
# WRONG — on cancel the generator is closed at yield, and unsubscribe never runs
@override
async def WatchOrder(
    self, request: orders_pb2.WatchOrderRequest, context: _WatchOrderContext
) -> AsyncIterator[orders_pb2.WatchOrderResponse]:
    updates = self._orders.start_following(order_id_from_wire(request.order_id))
    async for order in updates:
        yield orders_pb2.WatchOrderResponse(order=order_to_wire(order))
    self._orders.stop_following(updates)

# CORRECT — the context manager removes the subscription however the stream ends
@override
async def WatchOrder(
    self, request: orders_pb2.WatchOrderRequest, context: _WatchOrderContext
) -> AsyncIterator[orders_pb2.WatchOrderResponse]:
    async with self._orders.follow_order(order_id_from_wire(request.order_id)) as updates:
        async for order in updates:
            yield orders_pb2.WatchOrderResponse(order=order_to_wire(order))
```

- **Flow control bounds one stream, not a fan-out.** A slow reader stalls `yield` once the HTTP/2
  windows fill — measured, the server stopped after 62 messages of 100 KB while the client slept.
  A publisher feeding many streams still gives each a bounded queue and never awaits one.
- **A stream's `timeout=` covers its whole life.** A watch that should last gets a maximum lifetime,
  and the client reopens it from its last position — never a stream with no deadline.
- **A client that leaves early cancels the call** — `call.cancel()`. Measured, a client that broke
  out of `async for` and dropped the call kept the server's stream running until its deadline.

## Testing

The whole module, with its fakes, is in [in-process-tests.md](in-process-tests.md).

- **A servicer method is a plain coroutine.** Call it with fakes behind the service and a context
  from `mocker.create_autospec(grpc.aio.ServicerContext, instance=True)` — grpc's object, a
  boundary the test does not own (`testing.md`).
- **The mapping, the translation and the deadlines are tested through one in-process server** on
  `127.0.0.1:0` — `add_secure_port` returns the port it got — with local credentials, a real channel
  and the real client adapter, never a patched stub:

```python
async def test_fetch_order_raises_not_found_for_unknown_order() -> None:
    async with _serving(_service()) as channel:
        lookup = GrpcOrderLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)

        with pytest.raises(OrderNotFoundError, match=str(_UNKNOWN_ORDER_ID)) as excinfo:
            await lookup.fetch_order(_UNKNOWN_ORDER_ID)

    assert excinfo.value.order_id == _UNKNOWN_ORDER_ID
```

- **A Unix socket lets the channel outlive the server.** The address — `unix:` and a path under
  `tmp_path` — is known before the server starts, so the channel opens first and the test can stop
  the server under a call in flight, with a grace and without one.
- **The lifespan variant runs under `LifespanManager`** (`python-fastapi`), with the channel on the
  socket address the factory was given.

## Changing the Schema

- **A field's number is its wire identity, and its name its JSON identity.** A field removed is
  `reserved` by number and by name in the same change, and a number is never reused: an old client
  still sending its notes as field 6 to a server that reads 6 as `comment` gets a successful call
  with the wrong meaning.

```protobuf
// WRONG — the deleted note's number reused: old clients' notes arrive as comments
message Order {
  string comment = 6;
}

// CORRECT — the number and the name reserved, the new field numbered after them
message Order {
  reserved 6;
  reserved "note";
  string comment = 7;
}
```

- **A new field is optional to every reader.** Old clients will not send it, so the converter
  treats it as absent until they all do.
- **A breaking change is a new package**, `shopapis.orders.v2`, served beside `v1` until the last
  client moves.
- **`buf breaking` runs in CI** — `buf breaking --against '.git#branch=main'`, with `main` fetched —
  and `buf lint` beside it. The default category, `FILE`, reported the deletion above even when
  reserved: right for a package whose generated modules other code imports. `WIRE_JSON` accepted it
  only once number and name were both reserved: right for a service whose clients generate their
  own code.

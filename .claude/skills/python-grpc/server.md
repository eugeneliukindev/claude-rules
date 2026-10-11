# The Server

## Contents

- One context manager in the composition root
- The shutdown grace
- `grpc.so_reuseport` off
- Message limits on both sides
- A bound on the calls in flight
- A TLS port
- Inside a FastAPI lifespan, under one worker

### The composition root builds, starts, drains and stops the server in one context manager

**Why:** a server started and left to `wait_for_termination` is never drained: on `SIGTERM` the
process exits with every call in flight cut off, and the health service never reports
`NOT_SERVING`. As a context manager (`python-wiring`) the same server serves a FastAPI lifespan, a
process of its own and the tests, and it yields the port it bound.

**Example:**
```python
# WRONG — started and waited on: nothing drains it, and nothing reports it going away
async def serve(
    *, flights: FlightService, address: str, credentials: grpc.ServerCredentials
) -> None:
    server = grpc.aio.server(interceptors=[StatusInterceptor()])
    flights_pb2_grpc.add_FlightServiceServicer_to_server(FlightServicer(flights), server)
    server.add_secure_port(address, credentials)
    await server.start()
    await server.wait_for_termination()


# CORRECT — started, marked serving, then marked not serving and drained however the block ends
_MAX_MESSAGE_BYTES: Final = 4 * 1024 * 1024
_FLIGHT_SERVICE_NAME: Final = flights_pb2.DESCRIPTOR.services_by_name["FlightService"].full_name


@asynccontextmanager
async def managed_grpc_server(
    *,
    flights: FlightService,
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
    flights_pb2_grpc.add_FlightServiceServicer_to_server(FlightServicer(flights), server)
    health = health_aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health, server)
    port = server.add_secure_port(address, credentials)
    await server.start()
    await health.set(_FLIGHT_SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
    try:
        yield port
    finally:
        await health.enter_graceful_shutdown()
        await server.stop(grace_seconds)
```

### `stop` gets a grace: new calls are refused at once, the calls in flight get that long

**Why:** with a grace, `stop` waits for the calls in flight and then cancels the rest, which reach
the client as `UNAVAILABLE` "Cancelling all calls" and the handler as `CancelledError`; `stop(None)`
aborts them all immediately. Measured: a 0.3-second call finished under a 2-second grace, and failed
under none. The grace fits inside the orchestrator's period with room to close the pools
(`python-workers`).

**Example:**
```python
# WRONG — every call in flight aborted the moment shutdown begins
await server.stop(None)

# CORRECT — the calls in flight get the grace to finish
await server.stop(grace_seconds)
```

### `grpc.so_reuseport` is turned off

**Why:** it is on by default, so a second server binds the same port without an error and the kernel
splits connections between the two — a stale process keeps a share of the traffic. Measured both
ways: on, the second bind succeeded; off, it raised `RuntimeError`.

**Example:**
```python
# WRONG — a stale server on the same port silently keeps half the connections
server = grpc.aio.server(interceptors=[StatusInterceptor()])

# CORRECT — a second bind of the port fails loudly
server = grpc.aio.server(interceptors=[StatusInterceptor()], options=[("grpc.so_reuseport", 0)])
```

### The message limit is one named constant, set on the server and on the client's channel

**Why:** the limit is enforced by the receiving side, 4 MiB by default in both directions, and a
larger message fails as `RESOURCE_EXHAUSTED` "Received message larger than max". Raised on the
server alone, a large response still fails at the client. Past a few MiB, the payload streams in
chunks instead.

**Example:**
```python
# WRONG — the server sends 16 MiB, and the client, still at its 4 MiB default, refuses it
server = grpc.aio.server(options=[("grpc.max_send_message_length", 16 * 1024 * 1024)])
channel = grpc.aio.secure_channel(target, channel_credentials)

# CORRECT — one constant, on both sides of the call
_MESSAGE_LIMIT_OPTIONS: Final = (
    ("grpc.max_receive_message_length", _MAX_MESSAGE_BYTES),
    ("grpc.max_send_message_length", _MAX_MESSAGE_BYTES),
)
server = grpc.aio.server(options=_MESSAGE_LIMIT_OPTIONS)
channel = grpc.aio.secure_channel(target, channel_credentials, options=_MESSAGE_LIMIT_OPTIONS)
```

### `maximum_concurrent_rpcs` bounds the calls in flight

**Why:** the default is no limit, so a burst queues without end in one process and every call slows
together; past the bound the server answers `RESOURCE_EXHAUSTED`, which the client sees at once.

**Example:**
```python
# WRONG — no bound: a burst is held in memory until every call is slow
server = grpc.aio.server(interceptors=[StatusInterceptor()])

# CORRECT — past the bound, a call is refused at once
server = grpc.aio.server(
    interceptors=[StatusInterceptor()], maximum_concurrent_rpcs=_MAX_CONCURRENT_CALLS
)
```

### The port is TLS, unless a mesh sidecar terminates TLS inside the pod

**Why:** plaintext carries every call's metadata, tokens included, in the clear. Behind a mesh
sidecar `add_insecure_port` on the pod's address is the one exception, and a setting names it;
tests use `grpc.local_server_credentials()`.

**Example:**
```python
# WRONG — plaintext on every interface, wherever it is deployed
port = server.add_insecure_port("[::]:50051")

# CORRECT — the service's key and certificate chain
credentials = grpc.ssl_server_credentials([(private_key, certificate_chain)])
port = server.add_secure_port(address, credentials)
```

### Beside FastAPI, the server lives in the lifespan, and the app runs one worker

**Why:** one process, one deploy, one shutdown. Measured under uvicorn: on `SIGTERM`, new gRPC calls
were refused with `UNAVAILABLE`, the call in flight finished inside the grace, and the process
exited 0. Every uvicorn worker runs the lifespan: with `--workers 2` the second failed to bind and
uvicorn stopped, and with the reuse-port default it would have shared the port silently. When the
gRPC side scales apart from HTTP, or HTTP needs several workers, the server runs as a second entry
point in the same image — `asyncio.run(main())`, with `SIGTERM` and `SIGINT` handled so it drains
before it closes (`python-async`) — in a second container (`python-container`); the context manager
is the same in both.

**Example:**
```python
# WRONG — started as a task the lifespan never stops: no drain, and an error in it goes unseen
def create_app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_engine(settings.database_url) as engine:
            flights = FlightService(PostgresFlightRepository(engine), PostgresFlightFeed(engine))
            asyncio.create_task(serve(flights=flights, address=settings.grpc_address))
            yield {"flight_service": flights}

    app = FastAPI(lifespan=lifespan)
    app.include_router(flights_router)
    return app


# CORRECT — the server is entered inside the engine and left before it, drained on the way out
def create_app(settings: Settings) -> FastAPI:
    grpc_credentials = grpc.ssl_server_credentials(
        [(settings.grpc_private_key.get_secret_value(), settings.grpc_certificate_chain)]
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[dict[str, object]]:
        async with managed_engine(settings.database_url) as engine:
            flights = FlightService(PostgresFlightRepository(engine), PostgresFlightFeed(engine))
            async with managed_grpc_server(
                flights=flights,
                address=settings.grpc_address,
                credentials=grpc_credentials,
                grace_seconds=settings.grpc_grace_seconds,
            ):
                yield {"flight_service": flights}

    app = FastAPI(lifespan=lifespan)
    app.include_router(flights_router)
    return app
```

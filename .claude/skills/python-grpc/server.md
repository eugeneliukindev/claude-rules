# The Server

## Contents

- One context manager in the composition root
- The shutdown grace
- `grpc.so_reuseport` off
- Message limits on both sides
- A bound on the calls in flight
- A TLS port

### The composition root builds, starts, drains and stops the server in one context manager

**Why:** a server started and left to `wait_for_termination` is never drained: on `SIGTERM` the
process exits with every call in flight cut off, and the health service never reports `NOT_SERVING`.
As a context manager (`python-wiring`) the same server serves any composition root and the tests,
and it yields the port it bound.

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
    max_message_bytes: int = _MAX_MESSAGE_BYTES,
) -> AsyncIterator[int]:
    server = grpc.aio.server(
        interceptors=[StatusInterceptor()],
        options=[
            ("grpc.so_reuseport", 0),
            ("grpc.max_receive_message_length", max_message_bytes),
            ("grpc.max_send_message_length", max_message_bytes),
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

### The port is TLS, unless a mesh sidecar terminates TLS inside the pod

**Why:** plaintext carries every call's metadata, tokens included, in the clear. Behind a mesh
sidecar `add_insecure_port` on the pod's address is the one exception, and a setting names it;
tests use `grpc.local_server_credentials()`.

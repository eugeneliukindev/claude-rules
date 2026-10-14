# The Server

## Contents

- One context manager around `start` and `stop(grace)`
- `so_reuseport`, limits, TLS
- One interceptor maps errors; what is unmapped; `AbortError`; which code
- Field-level detail as a `google.rpc.Status`
- The interceptor module
- A streaming handler, health, the probe, reflection, telemetry, authentication

### The root enters the server through one context manager that starts it and stops it with a grace

**Why:** a `serve()` that ends in `await server.wait_for_termination()` is never drained: on
`SIGTERM` the process exits with every call in flight cut off, and the health service never reports
`NOT_SERVING`. The context manager serves any composition root and the tests, and yields the port it
bound — `add_secure_port` returns it, so `127.0.0.1:0` works.

**Example:**
```python
# CORRECT — started, marked serving, then marked not serving and drained however the block ends
_MAX_MESSAGE_BYTES: Final = 4 * 1024 * 1024
_MAX_CONCURRENT_RPCS: Final = 200
_SHUTDOWN_GRACE_SECONDS: Final = 10.0
_FLIGHT_SERVICE_NAME: Final = flights_pb2.DESCRIPTOR.services_by_name["FlightService"].full_name


@asynccontextmanager
async def flight_server_port(
    *,
    flights: FlightService,
    address: str,
    credentials: grpc.ServerCredentials,
    shutdown_grace_seconds: float = _SHUTDOWN_GRACE_SECONDS,
    max_message_bytes: int = _MAX_MESSAGE_BYTES,
    max_concurrent_rpcs: int = _MAX_CONCURRENT_RPCS,
) -> AsyncIterator[int]:
    server = grpc.aio.server(
        interceptors=[StatusInterceptor()],
        options=[
            ("grpc.so_reuseport", 0),
            ("grpc.max_receive_message_length", max_message_bytes),
            ("grpc.max_send_message_length", max_message_bytes),
        ],
        maximum_concurrent_rpcs=max_concurrent_rpcs,
    )
    flights_pb2_grpc.add_FlightServiceServicer_to_server(FlightServicer(flights=flights), server)
    health = health_aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health, server)
    port = server.add_secure_port(address, credentials)
    await server.start()
    await health.set(_FLIGHT_SERVICE_NAME, health_pb2.HealthCheckResponse.SERVING)
    try:
        yield port
    finally:
        await health.enter_graceful_shutdown()
        await server.stop(shutdown_grace_seconds)
```

### `stop` gets a grace: new calls are refused at once, the calls in flight get that long

**Why:** with a grace, `stop` waits for the calls in flight and then cancels the rest, which reach
the client as `UNAVAILABLE` "Cancelling all calls" and the handler as `CancelledError`; `stop(None)`
or `stop(0)` aborts them all at once. Measured: a 0.3-second call finished under a 2-second grace,
and failed under none. The grace fits inside the orchestrator's period with room to close the pools.

### `grpc.so_reuseport` is turned off

**Why:** it is on by default, so a second server binds the same port without an error and the kernel
splits connections between the two — a stale process keeps a share of the traffic. Measured: on,
the second bind succeeded; off, it raised `RuntimeError`.

### The message limit is one named constant on the server and the client's channel, and the calls in flight are bounded

**Why:** the receiving side enforces the limit, 4 MiB by default in both directions, and a larger
message fails as `RESOURCE_EXHAUSTED` "Received message larger than max"; raised on the server
alone, a large response still fails at the client. Past a few MiB, the payload streams in chunks.
`maximum_concurrent_rpcs` defaults to no limit, so a burst queues without end and every call slows
together; past the bound the server answers `RESOURCE_EXHAUSTED` at once.

### The port is TLS, unless a mesh sidecar terminates TLS inside the pod

**Why:** plaintext carries every call's metadata, tokens included, in the clear. Behind a mesh
sidecar `add_insecure_port` on the pod's address is the one exception, and a setting names it;
tests use `grpc.local_server_credentials()`.

### One interceptor maps errors to status codes; the servicer never aborts itself

**Why:** an exception that escapes a handler reaches the client with its message: `UNKNOWN`, details
`Unexpected <class 'ValueError'>: ` and whatever the message held — a hostname and a user name, in
the run that measured it. Mapping in each method repeats the table and misses the method added next
year; `StatusInterceptor` below covers every method, unary and streaming, and the servicer only
raises.

### An unmapped error is logged once with its traceback and answered with a fixed text

**Why:** `_abort_with_status` walks the error's MRO, so a subclass of a mapped error is mapped too.
Anything else is a defect whose message may hold a hostname, a query or a user's data: the client
gets `INTERNAL` and `_INTERNAL_DETAILS`, the log gets the traceback.

### `AbortError` is re-raised before the boundary's `except Exception`

**Why:** `context.abort` raises `grpc.aio.AbortError`, an `Exception`. Caught by the boundary, the
client still gets the code the handler aborted with, but every deliberate abort is logged at
`ERROR` as a failed RPC, with its traceback — measured.

### The code says what the client can do about it

**Why:** clients act on the code, not the text. `INVALID_ARGUMENT`: the request is wrong whatever
the state. `FAILED_PRECONDITION`: the state forbids it — the flight has already departed.
`NOT_FOUND`; `ALREADY_EXISTS` for a create that collides. `UNAUTHENTICATED` versus
`PERMISSION_DENIED` as 401 versus 403. `UNAVAILABLE` only for "try again", since clients and the
retry policy retry it — never for a domain error. `UNKNOWN` never on purpose.

### Field-level detail a client acts on travels as a `google.rpc.Status`

**Why:** details joined into the text can only be shown, not acted on. A `BadRequest` packed into
the status is read back by the client with `rpc_status.from_call(error)` — `grpcio-status`,
verified round trip; a string of `"field: reason"` pairs joined into the text is not.

**Example:**
```python
# CORRECT — each violation a field the client can read back with rpc_status.from_call
async def _abort_with_violations(context: _Context, violations: Mapping[str, str]) -> Never:
    bad_request = error_details_pb2.BadRequest(
        field_violations=[
            error_details_pb2.BadRequest.FieldViolation(field=field, description=reason)
            for field, reason in violations.items()
        ]
    )
    detail = any_pb2.Any()
    detail.Pack(bad_request)
    status = status_pb2.Status(
        code=code_pb2.INVALID_ARGUMENT, message="invalid request", details=[detail]
    )
    await context.abort_with_status(rpc_status.to_status(status))
```

## The Interceptor Module

Passed as `grpc.aio.server(interceptors=[StatusInterceptor()])`; ran under grpcio 1.84 and passes
`mypy --strict` with `types-grpcio`. The `cast`s are there because the stubs type a handler's
behaviour as synchronous. Client-streaming and bidirectional methods would wrap `stream_unary` and
`stream_stream` the same way; unwrapped, their unclassified errors reach the client as `UNKNOWN`
with the message. A stream closed at `yield` gets `GeneratorExit`, a `BaseException` the
`except Exception` lets through.

```python
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Final, Never, cast, final, override

import grpc

from airline.errors import (
    FlightAlreadyDepartedError,
    FlightNotFoundError,
    InvalidFlightRequestError,
)

_CODE_BY_ERROR: Final[Mapping[type[Exception], grpc.StatusCode]] = MappingProxyType(
    {
        InvalidFlightRequestError: grpc.StatusCode.INVALID_ARGUMENT,
        FlightNotFoundError: grpc.StatusCode.NOT_FOUND,
        FlightAlreadyDepartedError: grpc.StatusCode.FAILED_PRECONDITION,
    }
)
_INTERNAL_DETAILS: Final = "internal error"

type _Context = grpc.aio.ServicerContext[object, object]
type _UnaryBehavior = Callable[[object, _Context], Awaitable[object]]
type _StreamBehavior = Callable[[object, _Context], AsyncIterator[object]]

logger = logging.getLogger(__name__)


@final
class StatusInterceptor(grpc.aio.ServerInterceptor):
    @override
    async def intercept_service[RequestT, ResponseT](
        self,
        continuation: Callable[
            [grpc.HandlerCallDetails], Awaitable[grpc.RpcMethodHandler[RequestT, ResponseT] | None]
        ],
        handler_call_details: grpc.HandlerCallDetails,
    ) -> grpc.RpcMethodHandler[RequestT, ResponseT] | None:
        handler = await continuation(handler_call_details)
        if handler is None:
            return None
        if handler.unary_unary is not None:
            return grpc.unary_unary_rpc_method_handler(
                _mapped_unary(cast("_UnaryBehavior", handler.unary_unary)),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        if handler.unary_stream is not None:
            return grpc.unary_stream_rpc_method_handler(
                _mapped_stream(cast("_StreamBehavior", handler.unary_stream)),
                request_deserializer=handler.request_deserializer,
                response_serializer=handler.response_serializer,
            )
        return handler


def _mapped_unary(behavior: _UnaryBehavior) -> _UnaryBehavior:
    async def call(request: object, context: _Context) -> object:
        try:
            return await behavior(request, context)
        except grpc.aio.AbortError:
            raise
        except Exception as error:  # noqa: BLE001 — the transport boundary
            await _abort_with_status(context, error)

    return call


def _mapped_stream(behavior: _StreamBehavior) -> _StreamBehavior:
    async def call(request: object, context: _Context) -> AsyncIterator[object]:
        try:
            async for response in behavior(request, context):
                yield response
        except grpc.aio.AbortError:
            raise
        except Exception as error:  # noqa: BLE001 — the transport boundary
            await _abort_with_status(context, error)

    return call


async def _abort_with_status(context: _Context, error: Exception) -> Never:
    for error_class in type(error).__mro__:
        code = _CODE_BY_ERROR.get(error_class)
        if code is not None:
            await context.abort(code, str(error))
    logger.error("rpc failed", exc_info=error)
    await context.abort(grpc.StatusCode.INTERNAL, _INTERNAL_DETAILS)
```

## Streaming, Health and Telemetry

### A server-streaming handler releases what it holds in `finally` or `async with`

**Why:** a handler suspended at `yield` is closed, not cancelled, when the client cancels or the
deadline passes: measured, its `except CancelledError` never ran and its `finally` did. Code after
the loop — a `stop_following(updates)` — runs only when the stream ends on its own, so the loop sits
inside `async with self._flights.follow_flight(flight_id) as updates:`. Flow control bounds one
stream — a slow reader stalled `yield` after 62 messages of 100 KB — so a publisher feeding many
streams gives each its own bounded queue and never awaits one.

### Health is pushed: a task sets each service's status, and nothing is computed per check

**Why:** `HealthServicer()` reports `""` as `SERVING` from construction, a named service as
`NOT_FOUND` until `set`, and `enter_graceful_shutdown()` turns every one `NOT_SERVING` and ignores
later `set`s. A `HealthServicer` subclass whose `Check` pings the database makes every probe wait
on it, and a hung database hangs the probe. Readiness is a task the root runs: it pings under
`asyncio.timeout`, once a period, and calls `health.set(service_name, ...)` with `SERVING` or
`NOT_SERVING`; `""` answers liveness.

### Kubernetes probes the health service natively, on a numeric port at the pod's address

**Why:** the `grpc` probe takes a numeric port only, speaks plaintext unless `mode: TLS` — which
skips verification and needs a feature gate — and connects to the pod's address, so a server
listening on `127.0.0.1` is never reached. A named port is rejected by the API. The probe's
`service` names what readiness asks about — `airapis.flights.v1.FlightService`; without it the
probe asks `""`, which is liveness.

### Reflection is behind a setting that is off wherever policy says so

**Why:** reflection publishes every service, method and field to whoever connects. It helps a
developer with `grpcurl`; in production it is a map for an attacker.

### Traces come from the instrumentation; metrics from a plugin the entry point registers

**Why:** `opentelemetry-instrumentation-grpc` — `aio_server_interceptor()`,
`aio_client_interceptors()` — records spans and no metrics. `grpcio-observability`'s
`OpenTelemetryPlugin(meter_provider=...).register_global()` recorded `grpc.server.call.duration` and
`grpc.client.attempt.duration` with `grpc.method` and `grpc.status`. It is process-wide, so only
`main()` registers it, before any server or channel exists.

### Cross-cutting work is a server interceptor, and authentication leaves health and reflection open

**Why:** an interceptor covers the method added next year; a value it puts in a `ContextVar` — the
request id from `invocation_metadata` — was visible in the handler. Authentication is one
interceptor that rejects with `UNAUTHENTICATED`; the kubelet's probe and a developer's reflection
client carry no token, so their methods are on its allowlist, or no pod gets ready:
`/grpc.health.v1.Health/Check`, `/grpc.health.v1.Health/Watch`, and
`/grpc.reflection.v1.ServerReflection/ServerReflectionInfo` with its `v1alpha` twin.

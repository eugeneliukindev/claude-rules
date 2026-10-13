# Errors and Status Codes

## Contents

- One interceptor maps errors for every method
- What is unmapped is logged once and answered with a fixed text
- `AbortError` passes through the boundary
- The code says what the client can do
- Field-level detail as a `google.rpc.Status`
- The interceptor module

### One interceptor maps errors to status codes; the servicer never aborts itself

**Why:** an exception that escapes a handler reaches the client with its message: `UNKNOWN`, details
`Unexpected <class 'ValueError'>: ` and whatever the message held — a hostname and a user name, in
the run that measured it. Mapping in each method repeats the table and misses the method added next
year; one interceptor on the server — the gRPC form of the exception handler in `python-fastapi` —
covers every method, unary and streaming.

**Example:**
```python
# WRONG — each method maps its own errors, and the next method added forgets to
@final
class FlightServicer(flights_pb2_grpc.FlightServiceServicer):
    def __init__(self, flights: FlightService) -> None:
        self._flights = flights

    @override
    async def GetFlight(
        self, request: flights_pb2.GetFlightRequest, context: _GetFlightContext
    ) -> flights_pb2.GetFlightResponse:
        try:
            flight = await self._flights.get_flight(flight_id_from_wire(request.flight_id))
        except FlightNotFoundError as error:
            await context.abort(grpc.StatusCode.NOT_FOUND, str(error))
        return flights_pb2.GetFlightResponse(flight=flight_to_wire(flight))

    @override
    async def WatchFlight(
        self, request: flights_pb2.WatchFlightRequest, context: _WatchFlightContext
    ) -> AsyncIterator[flights_pb2.WatchFlightResponse]:
        async with self._flights.follow_flight(flight_id_from_wire(request.flight_id)) as updates:
            async for flight in updates:
                yield flights_pb2.WatchFlightResponse(flight=flight_to_wire(flight))


# CORRECT — the servicer raises; StatusInterceptor on the server maps every method's errors
@final
class FlightServicer(flights_pb2_grpc.FlightServiceServicer):
    def __init__(self, flights: FlightService) -> None:
        self._flights = flights

    @override
    async def GetFlight(
        self, request: flights_pb2.GetFlightRequest, context: _GetFlightContext
    ) -> flights_pb2.GetFlightResponse:
        flight = await self._flights.get_flight(flight_id_from_wire(request.flight_id))
        return flights_pb2.GetFlightResponse(flight=flight_to_wire(flight))

    @override
    async def WatchFlight(
        self, request: flights_pb2.WatchFlightRequest, context: _WatchFlightContext
    ) -> AsyncIterator[flights_pb2.WatchFlightResponse]:
        async with self._flights.follow_flight(flight_id_from_wire(request.flight_id)) as updates:
            async for flight in updates:
                yield flights_pb2.WatchFlightResponse(flight=flight_to_wire(flight))
```

### An unmapped error is logged once with its traceback and answered with a fixed text

**Why:** the mapping walks the error's MRO, so a subclass of a mapped error is mapped too. Anything
else is a defect whose message may hold a hostname, a query or a user's data; the client gets
`INTERNAL` and a text that says nothing, and the log gets the traceback.

**Example:**
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

### `AbortError` is re-raised before the boundary's `except Exception`

**Why:** `context.abort` raises `grpc.aio.AbortError`, an `Exception`. Caught by the boundary, the
client still gets the code the handler aborted with, but every deliberate abort is logged at
`ERROR` as a failed RPC, with its traceback — measured.

**Example:**
```python
# WRONG — a deliberate abort is caught here and logged as a failure
def _mapped_unary(behavior: _UnaryBehavior) -> _UnaryBehavior:
    async def call(request: object, context: _Context) -> object:
        try:
            return await behavior(request, context)
        except Exception as error:  # noqa: BLE001 — the transport boundary
            await _abort_with_status(context, error)

    return call


# CORRECT — the abort passes through untouched
def _mapped_unary(behavior: _UnaryBehavior) -> _UnaryBehavior:
    async def call(request: object, context: _Context) -> object:
        try:
            return await behavior(request, context)
        except grpc.aio.AbortError:
            raise
        except Exception as error:  # noqa: BLE001 — the transport boundary
            await _abort_with_status(context, error)

    return call
```

### The code says what the client can do about it

**Why:** clients act on the code, not the text. `INVALID_ARGUMENT`: the request is wrong whatever
the state. `FAILED_PRECONDITION`: the state forbids it — the flight has already departed.
`NOT_FOUND`; `ALREADY_EXISTS` for a create that collides. `UNAUTHENTICATED` versus
`PERMISSION_DENIED` as 401 versus 403 (`python-auth`). `UNAVAILABLE` only for "try again", since
clients and the retry policy retry it — never for a domain error. `UNKNOWN` never on purpose.

### Field-level detail a client acts on travels as a `google.rpc.Status`

**Why:** details joined into the text can only be shown, not acted on. A `BadRequest` packed into
`status_pb2.Status(...).details` and sent with
`context.abort_with_status(rpc_status.to_status(...))` is read back by the client with
`rpc_status.from_call(error)` — `grpcio-status`, verified round trip.

**Example:**
```python
# WRONG — the violations flattened into one string the client can only display
async def _abort_with_violations(context: _Context, violations: Mapping[str, str]) -> Never:
    details = "; ".join(f"{field}: {reason}" for field, reason in violations.items())
    await context.abort(grpc.StatusCode.INVALID_ARGUMENT, details)


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

Passed to `grpc.aio.server(interceptors=[StatusInterceptor()])`, it wraps every unary and
server-streaming handler. It ran under grpcio 1.84 and passes `mypy --strict` with `types-grpcio`.

```python
"""Domain errors mapped to gRPC status codes, in one interceptor for every method."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Final, Never, cast, final, override

import grpc

from airline.errors import FlightAlreadyDepartedError, FlightNotFoundError, InvalidRequestError

_CODE_BY_ERROR: Final[Mapping[type[Exception], grpc.StatusCode]] = MappingProxyType(
    {
        InvalidRequestError: grpc.StatusCode.INVALID_ARGUMENT,
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
    for error_type in type(error).__mro__:
        code = _CODE_BY_ERROR.get(error_type)
        if code is not None:
            await context.abort(code, str(error))
    logger.error("rpc failed", exc_info=error)
    await context.abort(grpc.StatusCode.INTERNAL, _INTERNAL_DETAILS)
```

What the module leaves out, on purpose:

- **The `cast`s are there because the stubs type a handler's behaviour as synchronous**; under
  `grpc.aio` it is a coroutine function, or an async generator function for a streaming response.
- **Client-streaming and bidirectional methods pass through unwrapped** — this service has none. A
  service that has them wraps `stream_unary` and `stream_stream` the same way, through
  `stream_unary_rpc_method_handler` and `stream_stream_rpc_method_handler`; unwrapped, their
  unclassified errors reach the client as `UNKNOWN` with the message.
- **A stream closed at `yield` when the client leaves** gets `GeneratorExit` — a `BaseException`,
  which the `except Exception` lets through untouched.

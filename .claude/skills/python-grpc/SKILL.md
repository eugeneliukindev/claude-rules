---
name: python-grpc
description: >-
  grpcio asyncio mechanics: servers and channels, typed stubs, protobuf kept at the edge, status
  codes, deadlines and retries, health, TLS, observability, streaming, in-process tests, .proto
  evolution. Use when code imports grpc, grpc.aio or a _pb2 module, implements a servicer, calls a
  gRPC service, or edits a .proto file.
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
verifies TLS.

### The servicer converts at the edge: messages never reach the service

**Why:** a service that takes `GetFlightRequest` has learned the transport, and a worker or a test
must build a message to call it. The servicer converts the request into domain values, calls one
service method and converts the result. It inherits the generated `FlightServiceServicer` — an ABC
to mypy-protobuf, a plain class at runtime whose unimplemented methods answer `UNIMPLEMENTED` — so
`@override` and `@final` apply as to any implementation, and the checker catches a missing method.

**Example:**
```python
# WRONG — the service receives the wire message, and every other caller must build one
@final
class FlightServicer(flights_pb2_grpc.FlightServiceServicer):
    def __init__(self, flights: FlightService) -> None:
        self._flights = flights

    @override
    async def GetFlight(
        self, request: flights_pb2.GetFlightRequest, context: _GetFlightContext
    ) -> flights_pb2.GetFlightResponse:
        return flights_pb2.GetFlightResponse(flight=await self._flights.get_flight(request))

    @override
    async def WatchFlight(
        self, request: flights_pb2.WatchFlightRequest, context: _WatchFlightContext
    ) -> AsyncIterator[flights_pb2.WatchFlightResponse]:
        async with self._flights.follow_flight(flight_id_from_wire(request.flight_id)) as updates:
            async for flight in updates:
                yield flights_pb2.WatchFlightResponse(flight=flight_to_wire(flight))


# CORRECT — converted at the edge; the service sees a FlightId and returns a Flight
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

### A converter reads every field by name, one function per direction

**Why:** the splat rule in `python-boundaries` holds for messages too. `MessageToDict` renames
fields to lowerCamelCase, drops every field at its default and writes `int64` as a string, so a
constructor fed from it gets strings where datetimes go and loses the fields that were unset; a
strict model rejects the result, and a lax one guesses.

**Example:**
```python
# WRONG — through a dict: the departure a string, the fare a dict, an empty gate silently dropped
def flight_from_wire(message: flights_pb2.Flight) -> Flight:
    return Flight(**MessageToDict(message, preserving_proto_field_name=True))


# CORRECT — every field named, each converted by the function that knows its type
def flight_from_wire(message: flights_pb2.Flight) -> Flight:
    return Flight(
        flight_id=flight_id_from_wire(message.flight_id),
        status=_status_from_wire(message.status),
        fare=_money_from_wire(message.fare),
        departs_at=_departs_at_from_wire(message),
        gate=message.gate if message.HasField("gate") else None,
    )
```

### A scalar whose absence means something is declared `optional` and read through `HasField`

**Why:** a proto3 scalar without `optional` has no presence: an unset string reads `""` and an unset
number `0`, and nothing tells "not sent" from "sent empty". With `optional`, `HasField` answers, and
passing `gate=None` to the constructor leaves the field unset. A field added later is absent from
every client built before it, so the converter treats it as optional until they all send it.

**Example:**
```protobuf
// WRONG — no presence: a flight with no gate yet and one at gate "" read the same
message Flight {
  string gate = 5;
}

// CORRECT — presence: HasField("gate") tells an unassigned gate from every value
message Flight {
  optional string gate = 5;
}
```

### A message field is asked `HasField` before it is read, and a `Timestamp` becomes aware UTC

**Why:** a message field is never `None`: an unset `departs_at` reads as an empty `Timestamp`, which
converts to 1970-01-01. `Timestamp.ToDatetime()` is naive and `ToDatetime(tzinfo=UTC)` aware;
`FromDatetime` takes a naive value as UTC without complaint. `Duration` has `ToTimedelta` and
`FromTimedelta`.

**Example:**
```python
# WRONG — a flight sent without departs_at arrives as 1970-01-01, and naive
def _departs_at_from_wire(message: flights_pb2.Flight) -> datetime:
    return message.departs_at.ToDatetime()


# CORRECT — absence is the upstream's error, and the instant is aware UTC
def _departs_at_from_wire(message: flights_pb2.Flight) -> datetime:
    if not message.HasField("departs_at"):
        raise PermanentFlightsUpstreamError(f"Flight {message.flight_id} has no departs_at")
    return message.departs_at.ToDatetime(tzinfo=UTC)
```

### An enum converts through a mapping that rejects `*_UNSPECIFIED` and every value it lacks

**Why:** an enum's zero is `*_UNSPECIFIED` and means "not set", never a real state. Enums are open:
a value this build does not know arrives as a plain `int` and is kept, so a converter with a
fallback branch turns both into a real state without a word.

**Example:**
```python
# WRONG — UNSPECIFIED and any status added after this build are read as scheduled
def _status_from_wire(status: flights_pb2.FlightStatus.ValueType) -> FlightStatus:
    if status == flights_pb2.FLIGHT_STATUS_BOARDING:
        return FlightStatus.BOARDING
    if status == flights_pb2.FLIGHT_STATUS_DEPARTED:
        return FlightStatus.DEPARTED
    if status == flights_pb2.FLIGHT_STATUS_CANCELLED:
        return FlightStatus.CANCELLED
    return FlightStatus.SCHEDULED


# CORRECT — each wire value mapped once; what the mapping lacks is rejected
_STATUS_BY_WIRE: Final[Mapping[flights_pb2.FlightStatus.ValueType, FlightStatus]] = (
    MappingProxyType(
        {
            flights_pb2.FLIGHT_STATUS_SCHEDULED: FlightStatus.SCHEDULED,
            flights_pb2.FLIGHT_STATUS_BOARDING: FlightStatus.BOARDING,
            flights_pb2.FLIGHT_STATUS_DEPARTED: FlightStatus.DEPARTED,
            flights_pb2.FLIGHT_STATUS_CANCELLED: FlightStatus.CANCELLED,
        }
    )
)


def _status_from_wire(status: flights_pb2.FlightStatus.ValueType) -> FlightStatus:
    domain_status = _STATUS_BY_WIRE.get(status)
    if domain_status is None:
        raise PermanentFlightsUpstreamError(f"unknown flight status {status}")
    return domain_status
```

### Money travels as a decimal string or as units plus nanos, never as `double`

**Why:** a `double` cannot hold 0.1, and the error reaches the ledger. A decimal string, or units
plus nanos as in `google.type.Money`, converts to `Decimal` exactly; identifiers travel as their
canonical string (`python-boundaries`). `int64` is a Python `int`, range-checked on assignment, and
its JSON mapping is a string.

**Example:**
```protobuf
// WRONG — a binary fraction: 19.99 arrives as 19.989999999999998
message Flight {
  double fare = 3;
}

// CORRECT — the amount as a decimal string beside its currency
message Money {
  string currency_code = 1;
  string amount = 2;
}

message Flight {
  Money fare = 3;
}
```

## Generating and Typing the Code

**Before running protoc, laying out the generated package or adding gRPC's dev dependencies, read
[codegen.md](codegen.md)** — mypy-protobuf rather than `--pyi_out`, the stubs' gaps, the generated
tree's top-level name, the runtime floors it pins, and regeneration in CI.

## The Server

**Before writing the code that builds, starts or stops a `grpc.aio` server, read
[server.md](server.md)** — one context manager in the root, the shutdown grace, `so_reuseport`
off, message and concurrency limits, TLS, and the server inside a FastAPI lifespan or a process of
its own.

## Errors and Status Codes

**Before mapping errors to status codes or writing a server interceptor, read
[errors.md](errors.md)** — one interceptor for every method, the fixed text for what is unmapped,
`AbortError`, which code means what, `google.rpc.Status` details, and the whole module.

## Health, Reflection and Telemetry

**Before adding the health service, reflection, tracing, metrics or an authentication interceptor,
read [operations.md](operations.md)** — health pushed rather than computed, Kubernetes' native
probe, reflection behind a setting, where traces and metrics come from, and the methods
authentication leaves open.

## The Client

**Before writing a client adapter or building a channel, read [client.md](client.md)** — one
channel per target, a deadline on every call, statuses translated at the adapter, retries in the
service config, keepalive, TLS names and per-call credentials.

## Streaming RPCs

**Before writing a server-streaming handler or consuming a stream, read
[streaming.md](streaming.md)** — closed at `yield` rather than cancelled, flow control and fan-out,
a stream's lifetime, and cancelling a call left early.

## Testing

**Before testing a servicer or a client adapter, read [in-process-tests.md](in-process-tests.md)**
— the servicer called directly, one in-process server for everything else, a Unix socket for the
shutdown tests, and the whole test module with its fakes.

## Beside FastAPI and pydantic

**Before serving the same service over HTTP and gRPC, or bringing pydantic near a message, read
[fastapi.md](fastapi.md)** — why no bridging library is used, two adapters over one service, and
what the converter checks instead of a model.

## Changing the Schema

**Before editing a `.proto` file, read [schema.md](schema.md)** — reserved numbers and names, a new
package for a breaking change, and `buf breaking` in CI.

---
name: python-grpc
description: >-
  grpcio asyncio mechanics: servers and channels, typed stubs, protobuf kept at the edge, status
  codes, deadlines and retries, health, TLS, streaming, in-process tests, .proto evolution. Use
  when code imports grpc, grpc.aio or a _pb2 module, implements a servicer, calls a gRPC service,
  or edits a .proto file.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/*.proto"
---

# gRPC

Checked against grpcio, grpcio-tools, grpcio-health-checking, grpcio-status and
grpcio-observability 1.84, protobuf 7.36, mypy-protobuf 5.1, types-grpcio 1.84, buf 1.73, on Python
3.13. Validation at the edge, deadlines, retry policy, aware UTC and `Decimal` money are
`python-boundaries`; where the server and the channels are built is `python-wiring`; draining on
shutdown is `python-async`, the grace period and the pod's probes `python-container`; verifying a
token is `python-auth`, a stream's guarantees `python-streaming`, the meter provider
`python-observability`. A script that calls a gRPC service once still sets a deadline and verifies
TLS.

### The servicer converts at the edge: messages never reach the service

**Why:** a service that takes `GetFlightRequest` has learned the transport, and a worker or a test
must build a message to call it. The servicer converts the request into domain values, calls one
service method and converts the result. It inherits the generated `FlightServiceServicer` — an ABC
to mypy-protobuf, a plain class at runtime whose unimplemented methods answer `UNIMPLEMENTED` — so
`@override` and `@final` apply as to any implementation.

**Example:**
```python
# WRONG — the service receives the wire message, and every other caller must build one
@final
class FlightServicer(flights_pb2_grpc.FlightServiceServicer):
    def __init__(self, *, flights: FlightService) -> None:
        self._flights = flights

    @override
    async def GetFlight(
        self, request: flights_pb2.GetFlightRequest, context: _GetFlightContext
    ) -> flights_pb2.GetFlightResponse:
        return flights_pb2.GetFlightResponse(flight=await self._flights.get_flight(request))


# CORRECT — converted at the edge; the service sees a FlightId and returns a Flight
@final
class FlightServicer(flights_pb2_grpc.FlightServiceServicer):
    def __init__(self, *, flights: FlightService) -> None:
        self._flights = flights

    @override
    async def GetFlight(
        self, request: flights_pb2.GetFlightRequest, context: _GetFlightContext
    ) -> flights_pb2.GetFlightResponse:
        flight = await self._flights.get_flight(flight_id_from_wire(request.flight_id))
        return flights_pb2.GetFlightResponse(flight=flight_to_wire(flight))
```

### A converter reads every field by name, one function per direction

**Why:** `MessageToDict` renames fields to lowerCamelCase, drops every field at its default and
writes `int64` as a string, so a constructor fed from it gets strings where datetimes go and loses
the fields that were unset; a strict model rejects the result, and a lax one guesses.

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
        fare=_fare_from_wire(message.fare),
        departs_at=_departs_at_from_wire(message),
        gate=message.gate if message.HasField("gate") else None,
    )
```

### A converter checks what the message cannot, and raises the error that maps to `INVALID_ARGUMENT`

**Why:** the message parses the wire but not a UUID's format, a positive amount or a known enum
value. A `ValueError` that escapes the converter is unclassified and reaches the client as
`INTERNAL`; the converter's own error is mapped to `INVALID_ARGUMENT` by the interceptor.

**Example:**
```python
# WRONG — a malformed id escapes as ValueError, and the client sees INTERNAL
def flight_id_from_wire(value: str) -> FlightId:
    return FlightId(UUID(value))


# CORRECT — the client is told which field is wrong
def flight_id_from_wire(value: str) -> FlightId:
    try:
        return FlightId(UUID(value))
    except ValueError as error:
        raise InvalidFlightRequestError("flight_id: must be a UUID") from error
```

### A scalar whose absence means something is declared `optional` and read through `HasField`

**Why:** a proto3 scalar without `optional` has no presence: an unset string reads `""` and an unset
number `0`, and nothing tells "not sent" from "sent empty". With `optional`, `HasField` answers, and
passing `gate=None` to the constructor leaves the field unset. A field added later is absent from
every client built before it, so the converter treats it as optional until they all send it:
`optional string gate = 5;`, never a bare `string gate = 5;`.

### A message field is asked `HasField` before it is read, and a `Timestamp` becomes aware UTC

**Why:** a message field is never `None`: an unset `departs_at` reads as an empty `Timestamp`, which
converts to 1970-01-01. `ToDatetime()` is naive and `ToDatetime(tzinfo=UTC)` aware; `FromDatetime`
takes a naive value as UTC without complaint. `Duration` has `ToTimedelta` and `FromTimedelta`.

**Example:**
```python
# WRONG — a flight sent without departs_at arrives as 1970-01-01, and naive
def _departs_at_from_wire(message: flights_pb2.Flight) -> datetime:
    return message.departs_at.ToDatetime()


# CORRECT — absence is the upstream's error, and the instant is aware UTC
def _departs_at_from_wire(message: flights_pb2.Flight) -> datetime:
    if not message.HasField("departs_at"):
        raise PermanentFlightsUpstreamError(f"flight {message.flight_id} has no departs_at")
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
plus nanos as in `google.type.Money`, converts to `Decimal` exactly; an identifier travels as its
canonical string. `int64` is a Python `int`, range-checked on assignment, and its JSON mapping is a
string.

## The Schema and the Generated Code

**Before editing a `.proto` file, running protoc, laying out the generated package or adding gRPC's
dev dependencies, read [proto.md](proto.md)** — mypy-protobuf rather than `--pyi_out`, the names
that exist only in the stubs, the generated tree's top-level name, the runtime floors, reserved
numbers, a new package for a breaking change, `buf breaking` in CI.

- The types come from mypy-protobuf, not from `--pyi_out`
- Below Python 3.14, a module whose signatures name a stub-only type postpones its annotations
- The generated tree's top-level name is one no hand-written package has
- `grpcio` and `protobuf` are declared at least at the generator's versions
- Generated files are never edited, and CI proves they match the schema
- A removed field is reserved by number and by name, and a number is never reused
- A breaking change is a new package, served beside the old one until the last client moves
- `buf breaking` and `buf lint` run in CI against the main branch

## The Server

**Before writing the code that builds, starts or stops a `grpc.aio` server, a server interceptor,
a status code mapping, a streaming handler, or adding health, reflection or metrics, read
[server.md](server.md)** — one context manager around `start` and `stop(grace)`, `so_reuseport`
off, limits, TLS, the interceptor module with `AbortError` and the fixed text for what is
unmapped, which code means what, `google.rpc.Status` details, a stream closed at `yield`, health
pushed rather than computed, the methods authentication leaves open.

- The root enters the server through one context manager that starts it and stops it with a grace
- `stop` gets a grace: new calls are refused at once, the calls in flight get that long
- `grpc.so_reuseport` is turned off
- The message limit is one named constant on the server and the client's channel, and the calls in flight are bounded
- The port is TLS, unless a mesh sidecar terminates TLS inside the pod
- One interceptor maps errors to status codes; the servicer never aborts itself
- An unmapped error is logged once with its traceback and answered with a fixed text
- `AbortError` is re-raised before the boundary's `except Exception`
- The code says what the client can do about it
- Field-level detail a client acts on travels as a `google.rpc.Status`
- A server-streaming handler releases what it holds in `finally` or `async with`
- Health is pushed: a task sets each service's status, and nothing is computed per check
- Kubernetes probes the health service natively, on a numeric port at the pod's address
- Reflection is behind a setting that is off wherever policy says so
- Traces come from the instrumentation; metrics from a plugin the entry point registers
- Cross-cutting work is a server interceptor, and authentication leaves health and reflection open

## The Client

**Before writing a client adapter, building a channel or consuming a stream, read
[client.md](client.md)** — one channel per target, a deadline on every call, statuses translated
at the adapter, retries in the service config, keepalive, TLS names, per-call credentials, a
stream's lifetime and cancelling a call left early.

- One channel per target, built by the root and closed with it, shared by every stub
- Every call carries `timeout=`
- Status codes are translated at the adapter, with the cause kept
- Retries live in the service config, for the idempotent methods, on `UNAVAILABLE`
- Keepalive pings no more often than the server allows
- TLS verifies the target's name, and nothing overrides it
- Per-call credentials ride a secure channel
- A stream's `timeout=` covers its whole life, so a watch has a maximum lifetime and reopens
- A client that leaves a stream early cancels the call

## Testing

**Before testing a servicer or a client adapter, read [in-process-tests.md](in-process-tests.md)**
— the servicer called directly, one in-process server for everything else, a Unix socket for the
shutdown tests, the fake that records a lookup started.

- A servicer method is called directly, with grpc's context autospecced
- The mapping, the translation and the deadlines are tested through one in-process server
- A shutdown test opens the channel first, on a Unix socket, so it outlives the server

## With Other Libraries

**Before running a gRPC server beside a FastAPI app, read
[fastapi-grpc.md](../python-integrations/fastapi-grpc.md)** — the server entered in the lifespan,
under one worker.

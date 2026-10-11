# Beside FastAPI and pydantic

No maintained library joins `grpc.aio` to FastAPI, or messages to pydantic models, in a way these
rules can use. What exists, and why it is not used:

| Library | What it does | Why it is not used here |
|---|---|---|
| `protobuf-to-pydantic` 0.3.3.1, last release June 2025 | pydantic models generated from messages | its runtime mode raises `AttributeError` on protobuf 7; its plugin defaults a missing `Timestamp` to the naive `datetime.now` and an `optional` string to `""` |
| `betterproto2` 0.10 | its own message runtime, optionally pydantic dataclasses | async clients and servers run on `grpclib`, not `grpc.aio`; its README says it is still subject to breaking changes |
| `pydantic-rpc` 0.15 | a gRPC or Connect service built from pydantic models, with no `.proto` | the schema is derived from Python code, so the contract other languages compile has no file of its own to review or check with buf |
| `connectrpc` 0.12 | Connect, gRPC and gRPC-Web as an ASGI app beside FastAPI | in beta by its own documentation; its gRPC protocol needs an HTTP/2 server, and uvicorn speaks HTTP/1.1 |
| `grpc-gateway`, `fastgrpc` on PyPI | REST-to-gRPC bridges | one release each, in 2023 and 2021 |

The maintained REST-to-gRPC gateway is the Go project `grpc-ecosystem/grpc-gateway`, run as a
process of its own. Serving both from one process belongs with the server rules of this skill.

### A FastAPI route and a gRPC servicer are two adapters over the same service

**Why:** the route parses with pydantic (`python-fastapi`), the servicer with the generated message;
each converts to the same domain values and calls the same method. A route that calls the stub of
its own process, or a servicer that calls the route, serializes twice, fails twice, and spends a
deadline on a loopback hop.

**Example:**
```python
# WRONG — the route calls its own process over gRPC: two serializations and a loopback deadline
@flights_router.get("/flights/{flight_id}")
async def read_flight(flight_id: UUID, stub: FlightStubDep) -> FlightOut:
    request = flights_pb2.GetFlightRequest(flight_id=str(flight_id))
    response = await stub.GetFlight(request, timeout=_LOOPBACK_TIMEOUT_SECONDS)
    return FlightOut.from_flight(flight_from_wire(response.flight))


# CORRECT — the route calls the service the servicer calls
@flights_router.get("/flights/{flight_id}")
async def read_flight(flight_id: UUID, flights: FlightServiceDep) -> FlightOut:
    return FlightOut.from_flight(await flights.get_flight(FlightId(flight_id)))
```

### On the gRPC side the converter checks what the message cannot, and pydantic has no job

**Why:** the message already parses the wire. What it does not check — a UUID's format, a positive
amount, a known enum value — the converter checks, raising an error the interceptor answers
`INVALID_ARGUMENT`. The HTTP model reached through `MessageToDict` gets camelCase keys, defaults
dropped and `int64` as strings: a strict model rejects it, a lax one guesses. When the same
constraints must hold in every language that compiles the schema, they are declared in the `.proto`
with `protovalidate` (2.0), and `protovalidate.validate(message)` raises `ValidationError`.

**Example:**
```python
# WRONG — the HTTP model reused through a dict: camelCase keys, defaults dropped, int64 as strings
def flight_id_from_wire(request: flights_pb2.GetFlightRequest) -> FlightId:
    return GetFlightQuery.model_validate(MessageToDict(request)).flight_id


# CORRECT — the field read from the message, and checked by the converter
def flight_id_from_wire(value: str) -> FlightId:
    try:
        return FlightId(UUID(value))
    except ValueError as error:
        raise InvalidRequestError("flight_id: must be a UUID") from error
```

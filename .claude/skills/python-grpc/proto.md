# The Schema and the Generated Code

### The types come from mypy-protobuf, not from `--pyi_out`

**Why:** `--pyi_out` types the messages only: no service stubs, and `HasField("gaet")` passes.
mypy-protobuf's `--mypy_out` types `HasField` with the fields that have presence, and
`--mypy_grpc_out` types servicers and stubs — `FlightServiceStub(channel)` on a `grpc.aio` channel
is a `FlightServiceAsyncStub`. The dev group holds `mypy-protobuf`, `types-protobuf`,
`types-grpcio` and, per companion package used, `types-grpcio-health-checking` or
`types-grpcio-status`; `grpc-stubs` is archived.

**Example:**
```bash
# CORRECT — HasField checked against the fields with presence, servicers and stubs typed
uv run python -m grpc_tools.protoc -I proto \
    --python_out=src --grpc_python_out=src --mypy_out=src --mypy_grpc_out=src \
    proto/airapis/flights/v1/flights.proto
```

### Below Python 3.14, a module whose signatures name a stub-only type postpones its annotations

**Why:** `FlightServiceAsyncStub` exists only in the `.pyi`, and `types-grpcio` makes
`RpcMethodHandler` generic where the runtime class is not; measured on 3.13, a signature naming
either raised at import — "module 'flights_pb2_grpc' has no attribute 'FlightServiceAsyncStub'",
"type 'RpcMethodHandler' is not subscriptable". `from __future__ import annotations` keeps
them strings. The stubs also lag the runtime the other way: they lack `grpc_health.v1.health.aio`
and every method of `HealthStub`, so that import or call carries `# type: ignore[attr-defined]` and
its reason.

### The generated tree's top-level name is one no hand-written package has

**Why:** the directory below `-I` is the import path: generated modules import each other by it
(`from airapis.flights.v1 import flights_pb2`), and protoc writes no `__init__.py`. A generated
`airline/flights/v1` beside the application package `airline` is shadowed by it, and the import
fails with `ModuleNotFoundError`.

**Example:**
```text
# WRONG — the generated airline.flights.v1 is shadowed by the application's airline package
proto/airline/flights/v1/flights.proto
src/airline/flights/v1/flights_pb2.py

# CORRECT — a top-level name of its own for the API, beside the application's
proto/airapis/flights/v1/flights.proto
src/airapis/flights/v1/flights_pb2.py
```

### `grpcio` and `protobuf` are declared at least at the generator's versions

**Why:** `_pb2_grpc.py` raises `RuntimeError` on import when the installed `grpcio` is older than
the `grpcio-tools` that generated it, and `_pb2.py` refuses a `protobuf` older than its generator.
The generator is bumped only with them.

### Generated files are never edited, and CI proves they match the schema

**Why:** checked in, a `.proto` changed without regenerating — or a generated file edited by hand —
ships code that does not match the schema; CI regenerates and fails on any difference. Either way
the linters skip them.

### A removed field is reserved by number and by name, and a number is never reused

**Why:** a field's number is its wire identity and its name its JSON identity. An old client still
sending its remarks as field 6 to a server that reads 6 as `comment` gets a successful call with the
wrong meaning.

**Example:**
```protobuf
// WRONG — the deleted remark's number reused: old clients' remarks arrive as comments
message Flight {
  string comment = 6;
}

// CORRECT — the number and the name reserved, the new field numbered after them
message Flight {
  reserved 6;
  reserved "remark";
  string comment = 7;
}
```

### A breaking change is a new package, served beside the old one until the last client moves

**Why:** a field's type changed in place breaks every client compiled against the old schema at
once, and no deploy order fixes it. `airapis.flights.v2` is a new service name; `v1` keeps
answering until nobody calls it.

### `buf breaking` and `buf lint` run in CI against the main branch

**Why:** a reviewer misses a reused number; buf does not. `buf breaking --against
'.git#branch=main'` needs `main` fetched. The default category, `FILE`, reported the deletion above
even when reserved — right for a package whose generated modules other code imports; `WIRE_JSON`
accepted it once number and name were both reserved — right for a service whose clients generate
their own code.

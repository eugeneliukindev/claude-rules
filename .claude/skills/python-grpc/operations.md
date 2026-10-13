# Health, Reflection and Telemetry

## Contents

- Health is pushed, not computed per check
- Kubernetes probes the health service natively
- Reflection behind a setting
- Traces from the instrumentation, metrics from `grpcio-observability`
- Authentication leaves health and reflection open

### Health is pushed: a task sets each service's status, and nothing is computed per check

**Why:** `HealthServicer()` reports `""` as `SERVING` from construction, a named service as
`NOT_FOUND` until `set`, and `enter_graceful_shutdown()` turns every one `NOT_SERVING` and ignores
later `set`s. A check that pings the database itself makes every probe wait on it, and a hung
database hangs the probe; readiness that depends on the database is a task that sets the service's
status, while `""` answers liveness (`python-container`).

**Example:**
```python
# WRONG — every probe waits on the database, and a hung database hangs the probe with it
@final
class DatabaseHealthServicer(health_aio.HealthServicer):
    def __init__(self, database: Database) -> None:
        super().__init__()
        self._database = database

    @override
    async def Check(
        self, request: health_pb2.HealthCheckRequest, context: _HealthContext
    ) -> health_pb2.HealthCheckResponse:
        await self._database.ping()
        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)


# CORRECT — a task the root runs pings under a deadline and pushes the result
async def report_readiness(
    health: health_aio.HealthServicer, database: Database, *, interval_seconds: float
) -> None:
    while True:
        try:
            async with asyncio.timeout(_PING_DEADLINE_SECONDS):
                await database.ping()
        except (DatabaseUnavailableError, TimeoutError):
            status = health_pb2.HealthCheckResponse.NOT_SERVING
        else:
            status = health_pb2.HealthCheckResponse.SERVING
        await health.set(_FLIGHT_SERVICE_NAME, status)
        await asyncio.sleep(interval_seconds)
```

### Kubernetes probes the health service natively, on a numeric port at the pod's address

**Why:** the `grpc` probe is stable since Kubernetes 1.27. It takes a numeric port only, speaks
plaintext unless `mode: TLS` — which skips verification and needs a feature gate — and connects to
the pod's address, so a server listening on `127.0.0.1` is never reached. `service` names what the
probe asks about; `""` is liveness.

**Example:**
```yaml
# WRONG — a named port is rejected by the API, and no service named: readiness asks liveness
readinessProbe:
  grpc:
    port: grpc

# CORRECT — the port number, and the service whose readiness the root pushes
readinessProbe:
  grpc:
    port: 50051
    service: airapis.flights.v1.FlightService
```

### Reflection is behind a setting that is off wherever policy says so

**Why:** reflection publishes the whole schema — every service, method and field — to whoever
connects. It helps a developer with `grpcurl`; in production it is a map for an attacker.

### Traces come from the instrumentation; metrics from a plugin the entry point registers

**Why:** `opentelemetry-instrumentation-grpc` — `aio_server_interceptor()`,
`aio_client_interceptors()` — records spans and no metrics. `grpcio-observability`'s
`OpenTelemetryPlugin(meter_provider=...).register_global()` recorded `grpc.server.call.duration` and
`grpc.client.attempt.duration` with `grpc.method` and `grpc.status` attributes. It is process-wide,
so only the entry point registers it, before any server or channel exists (`python-observability`).

**Example:**
```python
# WRONG — the tracing interceptor alone: spans, and no call durations at all
def main() -> None:
    server_settings = ServerSettings()
    app_settings = AppSettings()
    asyncio.run(serve(address=server_settings.address, database_url=app_settings.database_url))


# CORRECT — the entry point registers the metrics plugin once, for the whole process
def main() -> None:
    server_settings = ServerSettings()
    app_settings = AppSettings()
    meter_provider = build_meter_provider(otlp_endpoint=server_settings.otlp_endpoint)
    OpenTelemetryPlugin(meter_provider=meter_provider).register_global()
    asyncio.run(serve(address=server_settings.address, database_url=app_settings.database_url))
```

### Cross-cutting work is a server interceptor, and authentication leaves health and reflection open

**Why:** declared once on the server, an interceptor covers the method added next year; a value it
puts in a `ContextVar` — the request id from `invocation_metadata` — was visible in the handler.
Authentication is one interceptor that rejects with `UNAUTHENTICATED`; the kubelet's probe and a
developer's reflection client carry no token, so their methods are on its allowlist. Verifying the
token is `python-auth`.

**Example:**
```python
# WRONG — the probes carry no token: every health check is UNAUTHENTICATED, and no pod gets ready
_OPEN_METHODS: Final = frozenset[str]()

# CORRECT — health and reflection answer without a token; every other method needs one
_OPEN_METHODS: Final = frozenset(
    {
        "/grpc.health.v1.Health/Check",
        "/grpc.health.v1.Health/Watch",
        "/grpc.reflection.v1.ServerReflection/ServerReflectionInfo",
        "/grpc.reflection.v1alpha.ServerReflection/ServerReflectionInfo",
    }
)
```

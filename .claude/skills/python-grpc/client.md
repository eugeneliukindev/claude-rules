# The Client

## Contents

- One channel per target, shared by every stub
- A deadline on every call
- Statuses translated at the adapter
- Retries in the service config, for idempotent methods only
- Keepalive no more often than the server allows
- TLS verifies the target's name
- Per-call credentials need a secure channel

### One channel per target, built by the root and closed with it, shared by every stub

**Why:** a channel per call pays a connection and a TLS handshake each time, and leaves the channels
for the garbage collector to close. The root opens
`async with grpc.aio.secure_channel(target, credentials, options=...)` once and hands it to every
adapter that talks to that target.

**Example:**
```python
# WRONG — a connection and a handshake for every lookup
@final
class GrpcFlightLookup(FlightLookup):
    def __init__(self, target: str, *, credentials: grpc.ChannelCredentials) -> None:
        self._target = target
        self._credentials = credentials

    @override
    async def fetch_flight(self, flight_id: FlightId) -> Flight:
        async with grpc.aio.secure_channel(self._target, self._credentials) as channel:
            stub = flights_pb2_grpc.FlightServiceStub(channel)
            response = await stub.GetFlight(flights_pb2.GetFlightRequest(flight_id=str(flight_id)))
        return flight_from_wire(response.flight)


# CORRECT — the root's channel, one stub over it for the adapter's life
@final
class GrpcFlightLookup(FlightLookup):
    def __init__(self, channel: grpc.aio.Channel, *, timeout_seconds: float) -> None:
        self._stub = flights_pb2_grpc.FlightServiceStub(channel)
        self._timeout_seconds = timeout_seconds

    @override
    async def fetch_flight(self, flight_id: FlightId) -> Flight:
        request = flights_pb2.GetFlightRequest(flight_id=str(flight_id))
        response = await self._stub.GetFlight(request, timeout=self._timeout_seconds)
        return flight_from_wire(response.flight)
```

### Every call carries `timeout=`

**Why:** gRPC has no default deadline: measured, a call to a stalled handler was still waiting after
a second, with `time_remaining()` `None`. The deadline reaches the server, which cancelled the
handler when it passed. Serving one call while making another, pass the smaller of your own timeout
and `context.time_remaining()`, which is `None` when the caller set no deadline.

**Example:**
```python
# WRONG — a stalled server holds the caller forever
async def fetch_flight(stub: FlightServiceAsyncStub, flight_id: FlightId) -> Flight:
    response = await stub.GetFlight(flights_pb2.GetFlightRequest(flight_id=str(flight_id)))
    return flight_from_wire(response.flight)


# CORRECT — the call fails as DEADLINE_EXCEEDED when its time is up, on both sides
async def fetch_flight(
    stub: FlightServiceAsyncStub, flight_id: FlightId, *, timeout_seconds: float
) -> Flight:
    request = flights_pb2.GetFlightRequest(flight_id=str(flight_id))
    response = await stub.GetFlight(request, timeout=timeout_seconds)
    return flight_from_wire(response.flight)
```

### Status codes are translated at the adapter, with the cause kept

**Why:** an `AioRpcError` that escapes makes every caller know gRPC to tell a missing flight from an
outage; it is translated like any upstream error. `NOT_FOUND` becomes the domain's error,
`UNAVAILABLE` and `DEADLINE_EXCEEDED` the transient type, everything else permanent —
`RESOURCE_EXHAUSTED` included, which is also a message over the size limit. `AioRpcError.details()`
is `str | None`.

**Example:**
```python
# WRONG — AioRpcError escapes, and every caller has to know gRPC to tell a 404 from an outage
@final
class GrpcFlightLookup(FlightLookup):
    def __init__(self, channel: grpc.aio.Channel, *, timeout_seconds: float) -> None:
        self._stub = flights_pb2_grpc.FlightServiceStub(channel)
        self._timeout_seconds = timeout_seconds

    @override
    async def fetch_flight(self, flight_id: FlightId) -> Flight:
        request = flights_pb2.GetFlightRequest(flight_id=str(flight_id))
        response = await self._stub.GetFlight(request, timeout=self._timeout_seconds)
        return flight_from_wire(response.flight)


# CORRECT — the status is translated here, with the cause kept
@final
class GrpcFlightLookup(FlightLookup):
    def __init__(self, channel: grpc.aio.Channel, *, timeout_seconds: float) -> None:
        self._stub = flights_pb2_grpc.FlightServiceStub(channel)
        self._timeout_seconds = timeout_seconds

    @override
    async def fetch_flight(self, flight_id: FlightId) -> Flight:
        request = flights_pb2.GetFlightRequest(flight_id=str(flight_id))
        try:
            response = await self._stub.GetFlight(request, timeout=self._timeout_seconds)
        except grpc.aio.AioRpcError as error:
            raise _translate_status(error, flight_id) from error
        return flight_from_wire(response.flight)


def _translate_status(error: grpc.aio.AioRpcError, flight_id: FlightId) -> Exception:
    code = error.code()
    if code == grpc.StatusCode.NOT_FOUND:
        return FlightNotFoundError(flight_id)
    if code in _TRANSIENT_CODES:
        return TransientFlightsUpstreamError(f"{code.name}: {error.details()}")
    return PermanentFlightsUpstreamError(f"{code.name}: {error.details()}")
```

### Retries live in the service config, for the idempotent methods, on `UNAVAILABLE`

**Why:** without a config nothing is retried; with one, the server saw attempts one to three and the
deadline covered all of them. `DEADLINE_EXCEEDED` is never retryable: the budget is spent and the
server may have done the work. This is the one retry layer for the call — no tenacity around it
(`python-boundaries`, `python-tenacity`); the opposite choice turns it off with
`("grpc.enable_retries", 0)`. The channel takes it as
`options=[("grpc.service_config", _SERVICE_CONFIG)]`, and it absorbs the `UNAVAILABLE` a server
answers between `SIGTERM` and its removal from the load balancer.

**Example:**
```python
# WRONG — every method, so a write cut off by a stopping server after its commit runs twice
_RETRIED_METHODS: Final = ({"service": "airapis.flights.v1.FlightService"},)

# CORRECT — the reads, named one by one
_RETRIED_METHODS: Final = (
    {"service": "airapis.flights.v1.FlightService", "method": "GetFlight"},
)

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

### Keepalive pings no more often than the server allows

**Why:** keepalive is off on clients by default, and the server decides how often it may be pinged
— by default no more than every five minutes without data. A client that pings more often is sent
`GOAWAY` with `too_many_pings`, as gRPC's keepalive guide documents, and its calls fail. The
interval is agreed with the service's owners, and no lower than about a minute.

**Example:**
```python
# WRONG — every ten seconds: the server answers GOAWAY too_many_pings and drops the connection
channel = grpc.aio.secure_channel(
    target, channel_credentials, options=[("grpc.keepalive_time_ms", 10_000)]
)

# CORRECT — the interval agreed with the server's owners
channel = grpc.aio.secure_channel(
    target, channel_credentials, options=[("grpc.keepalive_time_ms", _KEEPALIVE_INTERVAL_MS)]
)
```

### TLS verifies the target's name, and nothing overrides it

**Why:** `grpc.ssl_channel_credentials(root_certificates=ca_pem)` trusts a private CA; measured, the
same certificate was accepted as `localhost` and refused as `127.0.0.1`. Overriding the name makes
any certificate the CA signed acceptable for this target. `insecure_channel` is for loopback and
tests; `grpc.local_channel_credentials()` covers both and allows call credentials.

**Example:**
```python
# WRONG — the name check switched off to make a mismatched certificate pass
channel = grpc.aio.secure_channel(
    "10.0.4.17:50051",
    grpc.ssl_channel_credentials(root_certificates=ca_pem),
    options=[("grpc.ssl_target_name_override", "flights.internal")],
)

# CORRECT — the target is the name the certificate was issued for
channel = grpc.aio.secure_channel(
    "flights.internal:50051", grpc.ssl_channel_credentials(root_certificates=ca_pem)
)
```

### Per-call credentials ride a secure channel

**Why:** `grpc.access_token_call_credentials(token)` sends `authorization: Bearer ...`; composed
into the channel with `grpc.composite_channel_credentials`, every call carries it. On an insecure
channel the call raised `UsageError`, because a bearer token in plaintext is a stolen token. The
token is the service's own (`python-auth`).

**Example:**
```python
# WRONG — per-call credentials on an insecure channel: the call raises UsageError
channel = grpc.aio.insecure_channel(target)
response = await stub.GetFlight(
    request, timeout=_TIMEOUT_SECONDS, credentials=grpc.access_token_call_credentials(token)
)

# CORRECT — the token composed into the TLS credentials, sent with every call
channel = grpc.aio.secure_channel(
    target,
    grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(root_certificates=ca_pem),
        grpc.access_token_call_credentials(token),
    ),
)
```

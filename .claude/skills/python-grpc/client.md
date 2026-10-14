# The Client

## Contents

- One channel per target; a deadline on every call
- Statuses translated at the adapter
- Retries in the service config; keepalive
- TLS names and per-call credentials
- A stream's lifetime, and a stream left early

### One channel per target, built by the root and closed with it, shared by every stub

**Why:** a channel per call pays a connection and a TLS handshake each time, and leaves the channels
for the garbage collector to close. The root opens
`async with grpc.aio.secure_channel(target, credentials, options=...)` once, with the server's
message-limit options, and hands it to every adapter for that target; the adapter builds its stub
in the constructor.

### Every call carries `timeout=`

**Why:** gRPC has no default deadline: measured, a call to a stalled handler was still waiting after
a second. The deadline reaches the server, which cancelled the handler when it passed. Serving one
call while making another, pass the smaller of your own timeout and `context.time_remaining()`,
which is `None` when the caller set no deadline.

### Status codes are translated at the adapter, with the cause kept

**Why:** an `AioRpcError` that escapes the adapter makes every caller know gRPC to tell a missing
flight from an outage. `NOT_FOUND` becomes the domain's error, `UNAVAILABLE` and
`DEADLINE_EXCEEDED` the transient type, everything else permanent — `RESOURCE_EXHAUSTED` included,
which is also a message over the size limit. `AioRpcError.details()` is `str | None`.

**Example:**
```python
# CORRECT — the status is translated here, with the cause kept
@final
class GrpcFlightLookup(FlightLookup):
    def __init__(self, *, channel: grpc.aio.Channel, timeout_seconds: float) -> None:
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
deadline covered all of them. A config naming only `{"service": ...}` retries every method, so a
write cut off by a stopping server after its commit runs twice. `DEADLINE_EXCEEDED` is never
retryable: the budget is spent and the server may have done the work. This is the one retry layer
for the call; the opposite choice turns it off with `("grpc.enable_retries", 0)`. It absorbs the
`UNAVAILABLE` a server answers between `SIGTERM` and its removal from the load balancer.

**Example:**
```python
# CORRECT — the reads, named one by one; passed as options=[("grpc.service_config", ...)]
_SERVICE_CONFIG: Final = json.dumps(
    {
        "methodConfig": [
            {
                "name": [{"service": "airapis.flights.v1.FlightService", "method": "GetFlight"}],
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

**Why:** keepalive is off on clients by default, and the server allows a ping no more than every
five minutes without data by default; a client that pings more often is sent `GOAWAY` with
`too_many_pings`, and its calls fail. The interval is agreed with the service's owners.

### TLS verifies the target's name, and nothing overrides it

**Why:** `grpc.ssl_channel_credentials(root_certificates=ca_pem)` trusts a private CA; measured, the
same certificate was accepted as `localhost` and refused as `127.0.0.1`. The target is the name the
certificate was issued for; `grpc.ssl_target_name_override` makes any certificate the CA signed
acceptable for it. `insecure_channel` is for loopback and tests, and
`grpc.local_channel_credentials()` covers both and allows call credentials.

### Per-call credentials ride a secure channel

**Why:** `grpc.access_token_call_credentials(token)` sends `authorization: Bearer ...`. On an
insecure channel the call raises `UsageError` "Call credentials are only valid on secure channels".
The token is composed into the TLS credentials, and every call carries it:
`grpc.composite_channel_credentials(grpc.ssl_channel_credentials(root_certificates=ca_pem),
grpc.access_token_call_credentials(token))`.


### A stream's `timeout=` covers its whole life, so a watch has a maximum lifetime and reopens

**Why:** the deadline counts from the call's start, not from the last message, and a stream with no
deadline outlives every server restart unnoticed. The server sends the current state first, so a
reopened watch misses nothing.

**Example:**
```python
# CORRECT — a bounded lifetime, and a new stream each time it passes
async def watch_flight(
    flight_id: FlightId,
    *,
    stub: flights_pb2_grpc.FlightServiceAsyncStub,
    lifetime_seconds: float = _WATCH_LIFETIME_SECONDS,
) -> AsyncIterator[Flight]:
    request = flights_pb2.WatchFlightRequest(flight_id=str(flight_id))
    while True:
        try:
            async for response in stub.WatchFlight(request, timeout=lifetime_seconds):
                yield flight_from_wire(response.flight)
        except grpc.aio.AioRpcError as error:
            if error.code() != grpc.StatusCode.DEADLINE_EXCEEDED:
                raise _translate_status(error, flight_id) from error
        else:
            return
```

### A client that leaves a stream early cancels the call

**Why:** measured, a client that returned from inside `async for` kept the server's stream running
until its deadline, holding a subscription and a slot under `maximum_concurrent_rpcs`. The call
object from `stub.WatchFlight(...)` is kept, the `async for` over it sits in a `try`, and `finally`
calls `call.cancel()` — a no-op on a call already done.

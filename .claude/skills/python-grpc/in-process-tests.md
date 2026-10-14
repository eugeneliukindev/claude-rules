# Testing a gRPC Service In-Process

## Contents

- The servicer called directly
- One in-process server for the mapping, the translation and the deadlines
- The shutdown tests on a Unix socket

One real server per test on an ephemeral port or a Unix socket, a real channel, and the real client
adapter. The blocks below ran green under grpcio 1.84 and pytest-asyncio 1.4 in auto mode with
`filterwarnings = ["error"]`, and pass `mypy --strict`. The repository fake records that a lookup
started, so a test waits for that state rather than sleeping:

```python
@final
class InMemoryFlightRepository(FlightRepository):
    def __init__(self, flights: Mapping[FlightId, Flight], *, delay_seconds: float = 0.0) -> None:
        self._flights = dict(flights)
        self._delay_seconds = delay_seconds
        self.lookup_started = asyncio.Event()

    @override
    async def find(self, flight_id: FlightId) -> Flight | None:
        self.lookup_started.set()
        await asyncio.sleep(self._delay_seconds)
        return self._flights.get(flight_id)
```

### A servicer method is called directly, with grpc's context autospecced

**Why:** the method is a plain coroutine, so its conversion needs no server. The context is grpc's
object, a boundary the test does not own; `create_autospec` holds it to grpc's signatures, where a
bare `MagicMock()` accepts a misspelt `context.abrot(...)` and passes.

**Example:**
```python
# CORRECT — grpc's own context type, held to its signatures
async def test_get_flight_returns_the_flight_as_a_message(mocker: MockerFixture) -> None:
    servicer = FlightServicer(flights=_service())
    context = mocker.create_autospec(grpc.aio.ServicerContext, instance=True)

    response = await servicer.GetFlight(
        flights_pb2.GetFlightRequest(flight_id=str(_FLIGHT.flight_id)), context
    )

    assert response.flight.fare == flights_pb2.Fare(currency_code="EUR", amount="19.99")
    assert not response.flight.HasField("gate")
```

### The mapping, the translation and the deadlines are tested through one in-process server

**Why:** a stub patched to raise `FlightNotFoundError` raises whatever the test assumed, so neither
the interceptor's mapping nor the adapter's translation runs. The root's own `flight_server_port` on
`127.0.0.1:0` with local credentials, a real channel and the real adapter run both, and a real
deadline; a repository that raises `RuntimeError` proves the client sees `INTERNAL` and
`"internal error"`, and a slow one with `timeout_seconds=0.1` proves `DEADLINE_EXCEEDED` is
transient.

**Example:**
```python
# CORRECT — a real server maps the error, a real channel carries the status, the adapter translates
@asynccontextmanager
async def _serving(flights: FlightService) -> AsyncIterator[grpc.aio.Channel]:
    async with (
        flight_server_port(
            flights=flights,
            address="127.0.0.1:0",
            credentials=grpc.local_server_credentials(_LOCAL_TCP),
            shutdown_grace_seconds=0.0,
        ) as port,
        grpc.aio.secure_channel(
            f"127.0.0.1:{port}", grpc.local_channel_credentials(_LOCAL_TCP)
        ) as channel,
    ):
        yield channel


async def test_fetch_flight_raises_not_found_for_unknown_flight() -> None:
    async with _serving(_service()) as channel:
        lookup = GrpcFlightLookup(channel=channel, timeout_seconds=_TIMEOUT_SECONDS)

        with pytest.raises(FlightNotFoundError, match=str(_UNKNOWN_FLIGHT_ID)) as excinfo:
            await lookup.fetch_flight(_UNKNOWN_FLIGHT_ID)

    assert excinfo.value.flight_id == _UNKNOWN_FLIGHT_ID
```

### A shutdown test opens the channel first, on a Unix socket, so it outlives the server

**Why:** `_serving` closes in reverse, channel first, and a closed channel cancels its own calls
before the server ever stops — the test would see the channel, not the grace. A Unix socket's
address — `unix:` and a path under `tmp_path` — is known before the server starts, so the channel
opens first and the test stops the server under a call in flight, with a grace and without one.

**Example:**
```python
# CORRECT — the channel on the socket outlives the server, and sees what the grace did
@asynccontextmanager
async def _call_in_flight_during_stop(
    tmp_path: Path, *, shutdown_grace_seconds: float, timeout_seconds: float = _TIMEOUT_SECONDS
) -> AsyncIterator[asyncio.Future[Flight]]:
    address = f"unix:{tmp_path / 'flights.sock'}"
    slow = InMemoryFlightRepository({_FLIGHT.flight_id: _FLIGHT}, delay_seconds=0.3)
    async with grpc.aio.secure_channel(
        address, grpc.local_channel_credentials(grpc.LocalConnectionType.UDS)
    ) as channel:
        lookup = GrpcFlightLookup(channel=channel, timeout_seconds=timeout_seconds)
        async with flight_server_port(
            flights=_service(slow),
            address=address,
            credentials=grpc.local_server_credentials(grpc.LocalConnectionType.UDS),
            shutdown_grace_seconds=shutdown_grace_seconds,
        ):
            in_flight = asyncio.ensure_future(lookup.fetch_flight(_FLIGHT.flight_id))
            async with asyncio.timeout(timeout_seconds):
                await slow.lookup_started.wait()
        yield in_flight


async def test_stop_lets_a_call_in_flight_finish_within_the_grace(tmp_path: Path) -> None:
    async with _call_in_flight_during_stop(tmp_path, shutdown_grace_seconds=2.0) as in_flight:
        flight = await in_flight

    assert flight == _FLIGHT


async def test_stop_without_grace_cancels_the_call_in_flight(tmp_path: Path) -> None:
    async with _call_in_flight_during_stop(tmp_path, shutdown_grace_seconds=0.0) as in_flight:
        with pytest.raises(TransientFlightsUpstreamError, match="UNAVAILABLE"):
            await in_flight
```

A streaming handler's release is tested the same way: a feed fake counts its open subscriptions and
sets an `asyncio.Event` when the last one closes; the test reads one message, calls
`call.cancel()`, and waits on the event under `asyncio.timeout`.

# Testing a gRPC Service In-Process

## Contents

- The servicer called directly
- One in-process server for the mapping, the translation and the deadlines
- The shutdown tests on a Unix socket
- The fakes
- The test module

One real server per test on an ephemeral port or a Unix socket, a real channel, and the real client
adapter. The module below ran green under pytest-asyncio 1.4 in auto mode with
`filterwarnings = ["error"]`, and passes `mypy --strict`.

### A servicer method is called directly, with grpc's context autospecced

**Why:** the method is a plain coroutine, so its conversion needs no server. The context is grpc's
object, a boundary the test does not own; `create_autospec` holds it to grpc's signatures, where a
bare mock accepts a misspelt `context.abrot(...)` and passes.

**Example:**
```python
# WRONG — a bare mock: any method name, any arguments, and the test still passes
async def test_get_flight_returns_the_flight_as_a_message(mocker: MockerFixture) -> None:
    servicer = FlightServicer(_service())

    response = await servicer.GetFlight(
        flights_pb2.GetFlightRequest(flight_id=str(_FLIGHT.flight_id)), mocker.MagicMock()
    )

    assert response.flight.fare == flights_pb2.Money(currency_code="EUR", amount="19.99")


# CORRECT — grpc's own context type, held to its signatures
async def test_get_flight_returns_the_flight_as_a_message(mocker: MockerFixture) -> None:
    servicer = FlightServicer(_service())
    context = mocker.create_autospec(grpc.aio.ServicerContext, instance=True)

    response = await servicer.GetFlight(
        flights_pb2.GetFlightRequest(flight_id=str(_FLIGHT.flight_id)), context
    )

    assert response.flight.fare == flights_pb2.Money(currency_code="EUR", amount="19.99")
```

### The mapping, the translation and the deadlines are tested through one in-process server

**Why:** a patched stub raises whatever the test assumed, so neither the interceptor's mapping nor
the adapter's translation runs. A server on `127.0.0.1:0` — `add_secure_port` returns the port it
got — with local credentials, a real channel and the real client adapter runs both, and a real
deadline.

**Example:**
```python
# WRONG — the stub is patched to raise the domain error: nothing between the two ends is tested
async def test_fetch_flight_raises_not_found_for_unknown_flight(mocker: MockerFixture) -> None:
    stub_class = mocker.patch.object(flights_pb2_grpc, "FlightServiceStub", autospec=True)
    stub_class.return_value.GetFlight.side_effect = FlightNotFoundError(_UNKNOWN_FLIGHT_ID)
    channel = mocker.create_autospec(grpc.aio.Channel, instance=True)
    lookup = GrpcFlightLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)

    with pytest.raises(FlightNotFoundError):
        await lookup.fetch_flight(_UNKNOWN_FLIGHT_ID)


# CORRECT — a real server maps the error, a real channel carries the status, the adapter translates
async def test_fetch_flight_raises_not_found_for_unknown_flight() -> None:
    async with _serving(_service()) as channel:
        lookup = GrpcFlightLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)

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
# WRONG — the channel closes before the server stops, cancelling the call the grace was for
async def test_stop_lets_a_call_in_flight_finish_within_the_grace() -> None:
    slow = InMemoryFlightRepository({_FLIGHT.flight_id: _FLIGHT}, delay_seconds=0.3)
    async with _serving(_service(slow), grace_seconds=2.0) as channel:
        lookup = GrpcFlightLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)
        in_flight = asyncio.create_task(lookup.fetch_flight(_FLIGHT.flight_id))
        await slow.lookup_started.wait()

    assert await in_flight == _FLIGHT


# CORRECT — the channel on the socket outlives the server, and sees what the grace did
async def test_stop_lets_a_call_in_flight_finish_within_the_grace(tmp_path: Path) -> None:
    async with _call_in_flight_during_stop(tmp_path, grace_seconds=2.0) as in_flight:
        flight = await in_flight

    assert flight == _FLIGHT
```

## The Fakes

`tests/fakes.py` — every contract gets an in-memory implementation (`testing.md`). The events let a
test wait for a state rather than sleep for it.

```python
"""In-memory implementations of the flight contracts, for tests."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import final, override

from airline.flights.domain import Flight, FlightId
from airline.flights.service import FlightFeed, FlightRepository


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


@final
class BrokenFlightRepository(FlightRepository):
    @override
    async def find(self, flight_id: FlightId) -> Flight | None:
        raise RuntimeError(f"connection to db-7.internal refused for {flight_id}")


@final
class InMemoryFlightFeed(FlightFeed):
    def __init__(self, updates: Sequence[Flight]) -> None:
        self._updates = tuple(updates)
        self.active_subscriptions = 0
        self.all_released = asyncio.Event()

    @override
    @asynccontextmanager
    async def subscribe(self, flight_id: FlightId) -> AsyncIterator[AsyncIterator[Flight]]:
        self.active_subscriptions += 1
        try:
            yield self._replay_then_wait()
        finally:
            self.active_subscriptions -= 1
            if not self.active_subscriptions:
                self.all_released.set()

    async def _replay_then_wait(self) -> AsyncIterator[Flight]:
        for flight in self._updates:
            yield flight
        await asyncio.Event().wait()
```

## The Test Module

```python
"""The flights gRPC service through a real server, channel and client adapter."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final
from uuid import UUID

import grpc
import pytest
from grpc_health.v1 import health_pb2, health_pb2_grpc
from pytest_mock import MockerFixture

from airline.clients.flights import GrpcFlightLookup, TransientFlightsUpstreamError
from airline.errors import FlightNotFoundError
from airline.grpc_api.server import managed_grpc_server
from airline.grpc_api.servicer import FlightServicer
from airline.flights.domain import Flight, FlightId, FlightStatus, Money
from airline.flights.service import FlightRepository, FlightService
from airapis.flights.v1 import flights_pb2, flights_pb2_grpc
from tests.fakes import BrokenFlightRepository, InMemoryFlightFeed, InMemoryFlightRepository

_FLIGHT: Final = Flight(
    flight_id=FlightId(UUID("6f1c2a43-9a4e-4a43-8a37-0d3b1f8f6a10")),
    status=FlightStatus.SCHEDULED,
    fare=Money(amount=Decimal("19.99"), currency="EUR"),
    departs_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
    gate=None,
)
_UNKNOWN_FLIGHT_ID: Final = FlightId(UUID("00000000-0000-4000-8000-000000000000"))
_TIMEOUT_SECONDS: Final = 1.0


def _service(repository: FlightRepository | None = None) -> FlightService:
    return FlightService(
        repository or InMemoryFlightRepository({_FLIGHT.flight_id: _FLIGHT}),
        InMemoryFlightFeed([_FLIGHT]),
    )


@asynccontextmanager
async def _serving(
    flights: FlightService, *, grace_seconds: float = 0.0
) -> AsyncIterator[grpc.aio.Channel]:
    async with (
        managed_grpc_server(
            flights=flights,
            address="127.0.0.1:0",
            credentials=grpc.local_server_credentials(grpc.LocalConnectionType.LOCAL_TCP),
            grace_seconds=grace_seconds,
        ) as port,
        grpc.aio.secure_channel(
            f"127.0.0.1:{port}", grpc.local_channel_credentials(grpc.LocalConnectionType.LOCAL_TCP)
        ) as channel,
    ):
        yield channel


async def test_get_flight_returns_the_flight_as_a_message(mocker: MockerFixture) -> None:
    servicer = FlightServicer(_service())
    context = mocker.create_autospec(grpc.aio.ServicerContext, instance=True)

    response = await servicer.GetFlight(
        flights_pb2.GetFlightRequest(flight_id=str(_FLIGHT.flight_id)), context
    )

    assert response.flight.fare == flights_pb2.Money(currency_code="EUR", amount="19.99")
    assert not response.flight.HasField("gate")


async def test_fetch_flight_round_trips_through_the_server() -> None:
    async with _serving(_service()) as channel:
        lookup = GrpcFlightLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)

        flight = await lookup.fetch_flight(_FLIGHT.flight_id)

    assert flight == _FLIGHT


async def test_fetch_flight_raises_not_found_for_unknown_flight() -> None:
    async with _serving(_service()) as channel:
        lookup = GrpcFlightLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)

        with pytest.raises(FlightNotFoundError, match=str(_UNKNOWN_FLIGHT_ID)) as excinfo:
            await lookup.fetch_flight(_UNKNOWN_FLIGHT_ID)

    assert excinfo.value.flight_id == _UNKNOWN_FLIGHT_ID


async def test_malformed_flight_id_is_invalid_argument() -> None:
    async with _serving(_service()) as channel:
        stub = flights_pb2_grpc.FlightServiceStub(channel)

        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.GetFlight(
                flights_pb2.GetFlightRequest(flight_id="42"), timeout=_TIMEOUT_SECONDS
            )

    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert excinfo.value.details() == "flight_id: must be a UUID"


async def test_malformed_flight_id_on_a_stream_is_invalid_argument() -> None:
    async with _serving(_service()) as channel:
        stub = flights_pb2_grpc.FlightServiceStub(channel)
        call = stub.WatchFlight(
            flights_pb2.WatchFlightRequest(flight_id="42"), timeout=_TIMEOUT_SECONDS
        )

        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await anext(aiter(call))

    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_unexpected_error_is_internal_without_its_message() -> None:
    async with _serving(_service(BrokenFlightRepository())) as channel:
        stub = flights_pb2_grpc.FlightServiceStub(channel)

        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.GetFlight(
                flights_pb2.GetFlightRequest(flight_id=str(_FLIGHT.flight_id)),
                timeout=_TIMEOUT_SECONDS,
            )

    assert excinfo.value.code() == grpc.StatusCode.INTERNAL
    assert excinfo.value.details() == "internal error"


async def test_fetch_flight_past_its_deadline_is_transient() -> None:
    slow = InMemoryFlightRepository({_FLIGHT.flight_id: _FLIGHT}, delay_seconds=1.0)
    async with _serving(_service(slow)) as channel:
        lookup = GrpcFlightLookup(channel, timeout_seconds=0.1)

        with pytest.raises(TransientFlightsUpstreamError, match="DEADLINE_EXCEEDED"):
            await lookup.fetch_flight(_FLIGHT.flight_id)


async def test_health_reports_serving_for_the_flight_service() -> None:
    async with _serving(_service()) as channel:
        health = health_pb2_grpc.HealthStub(channel)

        response = await health.Check(  # type: ignore[attr-defined]  # stubs declare no methods
            health_pb2.HealthCheckRequest(service="airapis.flights.v1.FlightService"),
            timeout=_TIMEOUT_SECONDS,
        )

    assert response.status == health_pb2.HealthCheckResponse.SERVING


@asynccontextmanager
async def _call_in_flight_during_stop(
    tmp_path: Path, *, grace_seconds: float
) -> AsyncIterator[asyncio.Task[Flight]]:
    address = f"unix:{tmp_path / 'flights.sock'}"
    slow = InMemoryFlightRepository({_FLIGHT.flight_id: _FLIGHT}, delay_seconds=0.3)
    async with grpc.aio.secure_channel(
        address, grpc.local_channel_credentials(grpc.LocalConnectionType.UDS)
    ) as channel:
        lookup = GrpcFlightLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)
        async with managed_grpc_server(
            flights=_service(slow),
            address=address,
            credentials=grpc.local_server_credentials(grpc.LocalConnectionType.UDS),
            grace_seconds=grace_seconds,
        ):
            in_flight = asyncio.create_task(lookup.fetch_flight(_FLIGHT.flight_id))
            async with asyncio.timeout(_TIMEOUT_SECONDS):
                await slow.lookup_started.wait()
        yield in_flight


async def test_stop_lets_a_call_in_flight_finish_within_the_grace(tmp_path: Path) -> None:
    async with _call_in_flight_during_stop(tmp_path, grace_seconds=2.0) as in_flight:
        flight = await in_flight

    assert flight == _FLIGHT


async def test_stop_without_grace_cancels_the_call_in_flight(tmp_path: Path) -> None:
    async with _call_in_flight_during_stop(tmp_path, grace_seconds=0.0) as in_flight:
        with pytest.raises(TransientFlightsUpstreamError, match="UNAVAILABLE"):
            await in_flight


async def test_stream_subscription_is_released_when_the_client_cancels() -> None:
    feed = InMemoryFlightFeed([_FLIGHT])
    flights = FlightService(InMemoryFlightRepository({}), feed)
    async with _serving(flights) as channel:
        stub = flights_pb2_grpc.FlightServiceStub(channel)
        call = stub.WatchFlight(
            flights_pb2.WatchFlightRequest(flight_id=str(_FLIGHT.flight_id)), timeout=5.0
        )
        first = await anext(aiter(call))
        call.cancel()
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            await feed.all_released.wait()

    assert first.flight.flight_id == str(_FLIGHT.flight_id)
    assert feed.active_subscriptions == 0
```

The health check carries a suppression because typeshed's `HealthStub` declares no methods.

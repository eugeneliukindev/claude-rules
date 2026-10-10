# Testing a gRPC Service In-Process

The test module behind the testing rules in `SKILL.md`: one real server per test on an ephemeral
port or a Unix socket, a real channel, and the real client adapter. It ran green under
pytest-asyncio 1.4 in auto mode with `filterwarnings = ["error"]`, and passes `mypy --strict`.

- [The fakes](#the-fakes)
- [The tests](#the-tests)
- [What each part is for](#what-each-part-is-for)

## The Fakes

`tests/fakes.py` — every contract gets an in-memory implementation (`testing.md`). The events let a
test wait for a state rather than sleep for it.

```python
"""In-memory implementations of the order contracts, for tests."""

import asyncio
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import final, override

from shop.orders.domain import Order, OrderId
from shop.orders.service import OrderFeed, OrderRepository


@final
class InMemoryOrderRepository(OrderRepository):
    def __init__(self, orders: Mapping[OrderId, Order], *, delay_seconds: float = 0.0) -> None:
        self._orders = dict(orders)
        self._delay_seconds = delay_seconds
        self.lookup_started = asyncio.Event()

    @override
    async def find(self, order_id: OrderId) -> Order | None:
        self.lookup_started.set()
        await asyncio.sleep(self._delay_seconds)
        return self._orders.get(order_id)


@final
class BrokenOrderRepository(OrderRepository):
    @override
    async def find(self, order_id: OrderId) -> Order | None:
        raise RuntimeError(f"connection to db-7.internal refused for {order_id}")


@final
class InMemoryOrderFeed(OrderFeed):
    def __init__(self, updates: Sequence[Order]) -> None:
        self._updates = tuple(updates)
        self.active_subscriptions = 0
        self.all_released = asyncio.Event()

    @override
    @asynccontextmanager
    async def subscribe(self, order_id: OrderId) -> AsyncIterator[AsyncIterator[Order]]:
        self.active_subscriptions += 1
        try:
            yield self._replay_then_wait()
        finally:
            self.active_subscriptions -= 1
            if not self.active_subscriptions:
                self.all_released.set()

    async def _replay_then_wait(self) -> AsyncIterator[Order]:
        for order in self._updates:
            yield order
        await asyncio.Event().wait()
```

## The Tests

```python
"""The orders gRPC service through a real server, channel and client adapter."""

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

from shop.clients.orders import GrpcOrderLookup, TransientOrdersUpstreamError
from shop.errors import OrderNotFoundError
from shop.grpc_api.server import managed_grpc_server
from shop.grpc_api.servicer import OrderServicer
from shop.orders.domain import Money, Order, OrderId, OrderStatus
from shop.orders.service import OrderRepository, OrderService
from shopapis.orders.v1 import orders_pb2, orders_pb2_grpc
from tests.fakes import BrokenOrderRepository, InMemoryOrderFeed, InMemoryOrderRepository

_ORDER: Final = Order(
    order_id=OrderId(UUID("6f1c2a43-9a4e-4a43-8a37-0d3b1f8f6a10")),
    status=OrderStatus.PAID,
    total=Money(amount=Decimal("19.99"), currency="EUR"),
    placed_at=datetime(2026, 3, 1, 9, 0, tzinfo=UTC),
    note=None,
)
_UNKNOWN_ORDER_ID: Final = OrderId(UUID("00000000-0000-4000-8000-000000000000"))
_TIMEOUT_SECONDS: Final = 1.0


def _service(repository: OrderRepository | None = None) -> OrderService:
    return OrderService(
        repository or InMemoryOrderRepository({_ORDER.order_id: _ORDER}),
        InMemoryOrderFeed([_ORDER]),
    )


@asynccontextmanager
async def _serving(
    orders: OrderService, *, grace_seconds: float = 0.0
) -> AsyncIterator[grpc.aio.Channel]:
    async with (
        managed_grpc_server(
            orders,
            address="127.0.0.1:0",
            credentials=grpc.local_server_credentials(grpc.LocalConnectionType.LOCAL_TCP),
            grace_seconds=grace_seconds,
        ) as port,
        grpc.aio.secure_channel(
            f"127.0.0.1:{port}", grpc.local_channel_credentials(grpc.LocalConnectionType.LOCAL_TCP)
        ) as channel,
    ):
        yield channel


async def test_get_order_returns_the_order_as_a_message(mocker: MockerFixture) -> None:
    servicer = OrderServicer(_service())
    context = mocker.create_autospec(grpc.aio.ServicerContext, instance=True)

    response = await servicer.GetOrder(
        orders_pb2.GetOrderRequest(order_id=str(_ORDER.order_id)), context
    )

    assert response.order.total == orders_pb2.Money(currency_code="EUR", amount="19.99")
    assert not response.order.HasField("note")


async def test_fetch_order_round_trips_through_the_server() -> None:
    async with _serving(_service()) as channel:
        lookup = GrpcOrderLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)

        order = await lookup.fetch_order(_ORDER.order_id)

    assert order == _ORDER


async def test_fetch_order_raises_not_found_for_unknown_order() -> None:
    async with _serving(_service()) as channel:
        lookup = GrpcOrderLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)

        with pytest.raises(OrderNotFoundError, match=str(_UNKNOWN_ORDER_ID)) as excinfo:
            await lookup.fetch_order(_UNKNOWN_ORDER_ID)

    assert excinfo.value.order_id == _UNKNOWN_ORDER_ID


async def test_malformed_order_id_is_invalid_argument() -> None:
    async with _serving(_service()) as channel:
        stub = orders_pb2_grpc.OrderServiceStub(channel)

        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.GetOrder(orders_pb2.GetOrderRequest(order_id="42"), timeout=_TIMEOUT_SECONDS)

    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT
    assert excinfo.value.details() == "order_id: must be a UUID"


async def test_malformed_order_id_on_a_stream_is_invalid_argument() -> None:
    async with _serving(_service()) as channel:
        stub = orders_pb2_grpc.OrderServiceStub(channel)
        call = stub.WatchOrder(
            orders_pb2.WatchOrderRequest(order_id="42"), timeout=_TIMEOUT_SECONDS
        )

        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await anext(aiter(call))

    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT


async def test_unexpected_error_is_internal_without_its_message() -> None:
    async with _serving(_service(BrokenOrderRepository())) as channel:
        stub = orders_pb2_grpc.OrderServiceStub(channel)

        with pytest.raises(grpc.aio.AioRpcError) as excinfo:
            await stub.GetOrder(
                orders_pb2.GetOrderRequest(order_id=str(_ORDER.order_id)), timeout=_TIMEOUT_SECONDS
            )

    assert excinfo.value.code() == grpc.StatusCode.INTERNAL
    assert excinfo.value.details() == "internal error"


async def test_fetch_order_past_its_deadline_is_transient() -> None:
    slow = InMemoryOrderRepository({_ORDER.order_id: _ORDER}, delay_seconds=1.0)
    async with _serving(_service(slow)) as channel:
        lookup = GrpcOrderLookup(channel, timeout_seconds=0.1)

        with pytest.raises(TransientOrdersUpstreamError, match="DEADLINE_EXCEEDED"):
            await lookup.fetch_order(_ORDER.order_id)


async def test_health_reports_serving_for_the_order_service() -> None:
    async with _serving(_service()) as channel:
        health = health_pb2_grpc.HealthStub(channel)

        response = await health.Check(  # type: ignore[attr-defined]  # stubs declare no methods
            health_pb2.HealthCheckRequest(service="shopapis.orders.v1.OrderService"),
            timeout=_TIMEOUT_SECONDS,
        )

    assert response.status == health_pb2.HealthCheckResponse.SERVING


@asynccontextmanager
async def _call_in_flight_during_stop(
    tmp_path: Path, *, grace_seconds: float
) -> AsyncIterator[asyncio.Task[Order]]:
    address = f"unix:{tmp_path / 'orders.sock'}"
    slow = InMemoryOrderRepository({_ORDER.order_id: _ORDER}, delay_seconds=0.3)
    async with grpc.aio.secure_channel(
        address, grpc.local_channel_credentials(grpc.LocalConnectionType.UDS)
    ) as channel:
        lookup = GrpcOrderLookup(channel, timeout_seconds=_TIMEOUT_SECONDS)
        async with managed_grpc_server(
            _service(slow),
            address=address,
            credentials=grpc.local_server_credentials(grpc.LocalConnectionType.UDS),
            grace_seconds=grace_seconds,
        ):
            in_flight = asyncio.create_task(lookup.fetch_order(_ORDER.order_id))
            async with asyncio.timeout(_TIMEOUT_SECONDS):
                await slow.lookup_started.wait()
        yield in_flight


async def test_stop_lets_a_call_in_flight_finish_within_the_grace(tmp_path: Path) -> None:
    async with _call_in_flight_during_stop(tmp_path, grace_seconds=2.0) as in_flight:
        order = await in_flight

    assert order == _ORDER


async def test_stop_without_grace_cancels_the_call_in_flight(tmp_path: Path) -> None:
    async with _call_in_flight_during_stop(tmp_path, grace_seconds=0.0) as in_flight:
        with pytest.raises(TransientOrdersUpstreamError, match="UNAVAILABLE"):
            await in_flight


async def test_stream_subscription_is_released_when_the_client_cancels() -> None:
    feed = InMemoryOrderFeed([_ORDER])
    orders = OrderService(InMemoryOrderRepository({}), feed)
    async with _serving(orders) as channel:
        stub = orders_pb2_grpc.OrderServiceStub(channel)
        call = stub.WatchOrder(
            orders_pb2.WatchOrderRequest(order_id=str(_ORDER.order_id)), timeout=5.0
        )
        first = await anext(aiter(call))
        call.cancel()
        async with asyncio.timeout(_TIMEOUT_SECONDS):
            await feed.all_released.wait()

    assert first.order.order_id == str(_ORDER.order_id)
    assert feed.active_subscriptions == 0
```

## What Each Part Is For

- **`_serving` is two items of one `async with`**: the server, then a channel to the port it bound.
  They close in reverse, channel first — which is why a test of the shutdown grace cannot use it: a
  closed channel cancels its own calls before the server ever stops.
- **`_call_in_flight_during_stop` opens the channel before the server**, on a Unix socket whose
  address is known in advance, so the channel outlives the server and the test sees what the grace
  did to the call.
- **The servicer test needs no server**: the method is a coroutine, and the context is grpc's own
  type under `create_autospec`, unused by a servicer whose errors the interceptor maps.
- **The health check carries a suppression** because typeshed's `HealthStub` declares no methods.
- **The lifespan variant** is the same tests' shape under `asgi-lifespan`'s `LifespanManager`
  (`python-fastapi`), with a channel on the Unix socket address the factory was given.

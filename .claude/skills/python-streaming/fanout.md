# Fan-Out Across Workers — the Whole Example

The pieces `SKILL.md` names, assembled and checked: `mypy --strict`, and a contract suite run
against the fake and against a broker. The redis implementation, the lifespan that builds it, and
how redis-py shows a gap are in `python-redis`.

- [Layout](#layout)
- [The relay and its wiring](#the-relay-and-its-wiring)
- [The fake and the contract suite](#the-fake-and-the-contract-suite)

## Layout

```
order_events/
    base.py           # OrderEventChannel(ABC), OrderEventChannelLostError
    redis_pubsub.py   # RedisOrderEventChannel — the only file that imports redis
    __init__.py       # the contract, its error and the implementations
relay.py              # OrderEventRelay — beside the feed, knows only the contract
tests/fakes.py        # InMemoryOrderEventChannel
```

Each implementation is a module named for its mechanism — `redis_pubsub.py`, `nats.py`,
`pg_listen.py` — and **turns every sign of a gap into `OrderEventChannelLostError` while
iterating**, not only on leaving the `async with`, where the relay's loop would never see it (the
redis signals: `python-redis`).

## The relay and its wiring

```python
@final
class OrderEventRelay:
    def __init__(self, *, channel: OrderEventChannel, feed: OrderFeed) -> None:
        self._channel = channel
        self._feed = feed

    async def run(self) -> None:
        while True:
            try:
                async with self._channel.subscribe() as events:
                    self._feed.end_all_streams()
                    async for event in events:
                        self._feed.publish(event)
            except OrderEventChannelLostError:
                logger.warning("order event subscription lost", exc_info=True)
            await asyncio.sleep(_RESUBSCRIBE_DELAY_SECONDS)
```

The lifespan builds the channel and the feed once, runs the relay in its task group and cancels it
at shutdown (`python-fastapi`; the redis version, built on the root's one client, is in
`python-redis`). Request handlers reach the channel through a `Depends` accessor and call
`order_events.publish`, never `feed.publish` — the feed reaches only its own process.

## The fake and the contract suite

The fake drops its subscriptions on demand, which is what the relay's own unit test needs; it
lives in `tests/fakes.py` and passes the same suite as every broker implementation
(`python-contracts`).

```python
@final
class InMemoryOrderEventChannel(OrderEventChannel):
    def __init__(self) -> None:
        self._subscriptions: set[asyncio.Queue[OrderEvent]] = set()

    @override
    async def publish(self, event: OrderEvent) -> None:
        for events in self._subscriptions:
            events.put_nowait(event)

    @override
    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[OrderEvent]]:
        events = asyncio.Queue[OrderEvent]()
        self._subscriptions.add(events)
        try:
            yield _drain(events)
        finally:
            self._subscriptions.discard(events)

    def drop_subscriptions(self) -> None:
        for events in self._subscriptions:
            events.shutdown()
        self._subscriptions.clear()


async def _drain(events: asyncio.Queue[OrderEvent]) -> AsyncIterator[OrderEvent]:
    while True:
        try:
            yield await events.get()
        except asyncio.QueueShutDown:
            raise OrderEventChannelLostError("dropped by the test") from None
```

```python
@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("redis", id="redis", marks=pytest.mark.integration),
    ]
)
def channel(request: pytest.FixtureRequest) -> OrderEventChannel:
    channel: OrderEventChannel = request.getfixturevalue(f"{request.param}_channel")
    return channel


async def test_published_event_reaches_a_live_subscription(channel: OrderEventChannel) -> None:
    async with channel.subscribe() as events:
        await channel.publish(_SHIPPED)
        async with asyncio.timeout(_DELIVERY_TIMEOUT_SECONDS):
            assert await anext(events) == _SHIPPED
```

The loss case is the same test with the subscription dropped in the middle — `drop_subscriptions()`
on the fake, the broker's own way of cutting a subscriber for a real one — and `pytest.raises
(OrderEventChannelLostError)` around the next `anext`. The relay's own test runs on the fake: a
stream subscribed to the feed ends with `QueueShutDown` once the fake drops and the relay
resubscribes.

# Fan-Out Across Workers

## Contents

- One subscription per worker, behind a channel contract
- The contract states at-most-once delivery and raises on a gap
- Streams end when a subscription goes live
- The relay only queues
- A room is a key of the feed
- The whole example: layout, relay, wiring, the fake and the contract suite

The redis implementation and how redis-py shows a gap are in `python-redis`; the lifespan that
builds the channel and runs the relay in a FastAPI service is in `python-fastapi`.

### Each worker subscribes once to a channel between processes, and publishes to the channel

**Why:** an in-process subscriber set reaches only the connections on the same process — with two
workers or two replicas, an event published on one never arrives at clients of the other. Each
worker subscribes **once** and fans out locally through the bounded queues of `SKILL.md`; one
subscription per connection multiplies the broker's load by the connection count. A request
handler publishes to the channel, never to the feed. The durable log behind `Last-Event-ID` is
separate: a pub/sub channel forgets what nobody was listening for.

**Example:**
```python
# WRONG — the scan reaches only the clients connected to this worker
@final
class ParcelScanning:
    def __init__(self, *, feed: ParcelFeed, history: ParcelHistory) -> None:
        self._feed = feed
        self._history = history

    async def record_scan(self, scan: Scan) -> None:
        event = await self._history.append(scan)
        self._feed.publish(event)


# CORRECT — every worker's relay receives it and fans it out to its own connections
@final
class ParcelScanning:
    def __init__(self, *, parcel_events: ParcelEventChannel, history: ParcelHistory) -> None:
        self._parcel_events = parcel_events
        self._history = history

    async def record_scan(self, scan: Scan) -> None:
        event = await self._history.append(scan)
        await self._parcel_events.publish(event)
```

### The channel is a contract that states at-most-once delivery and raises on a gap

**Why:** Redis pub/sub, a NATS subject and PostgreSQL `LISTEN` are implementations of one
capability (`python-contracts`), and every client library hides a dropped subscription differently
— some reconnect and resubscribe without raising, and the event published in between is never
delivered. The relay's correctness rests on two things the contract therefore states: delivery is
at most once, and **a subscription that may have missed an event raises while iterating** — not
only on leaving the `async with`, where the relay's loop would never see it.

**Example:**
```python
# WRONG — nothing says what a dropped subscription does, so each implementation decides
class ParcelEventChannel(ABC):
    @abstractmethod
    async def publish(self, event: ParcelEvent) -> None: ...

    @abstractmethod
    def subscribe(self) -> AbstractAsyncContextManager[AsyncIterator[ParcelEvent]]: ...


# CORRECT — the gap is part of the contract, with its own error
class ParcelEventChannelLostError(TrackingError):
    """The subscription ended, and an event published meanwhile may never arrive."""


class ParcelEventChannel(ABC):
    """Carries parcel events between worker processes, each event at most once."""

    @abstractmethod
    async def publish(self, event: ParcelEvent) -> None: ...

    @abstractmethod
    def subscribe(self) -> AbstractAsyncContextManager[AsyncIterator[ParcelEvent]]:
        """Enter once live; iterating raises ParcelEventChannelLostError if an event is lost."""
```

### Every time a subscription goes live, the relay ends the worker's streams

**Why:** a stream opened while the channel was down replayed from the log, then followed a feed
nothing was filling; one open across the drop missed what was published during it. Ended, each
reconnects — SSE with `Last-Event-ID`, a WebSocket after 1013 — and replays from its own id.

**Example:**
```python
# WRONG — the relay resubscribes and carries on: a stream that missed events never learns it
@final
class ParcelEventRelay:
    def __init__(self, *, channel: ParcelEventChannel, feed: ParcelFeed) -> None:
        self._channel = channel
        self._feed = feed

    async def _follow_channel(self) -> None:
        async with self._channel.subscribe() as events:
            async for event in events:
                self._feed.publish(event)


# CORRECT — the subscription is live: every stream from before it resumes from its own id
@final
class ParcelEventRelay:
    def __init__(self, *, channel: ParcelEventChannel, feed: ParcelFeed) -> None:
        self._channel = channel
        self._feed = feed

    async def _follow_channel(self) -> None:
        async with self._channel.subscribe() as events:
            self._feed.end_all_streams()
            async for event in events:
                self._feed.publish(event)
```

### The relay only queues; it never awaits a socket

**Why:** sending to each connection in turn lets one client that stops reading stall its room, then
the subscription behind it, until the broker drops a subscriber that does not read. `feed.publish` is `put_nowait` into the bounded queues, and each connection's own
push task does the sending.

**Example:**
```python
# WRONG — the relay awaits every socket in the room: one client that stops reading stalls them all
@final
class ParcelEventRelay:
    def __init__(
        self,
        *,
        channel: ParcelEventChannel,
        sockets_by_parcel: Mapping[TrackingNumber, set[WebSocket]],
    ) -> None:
        self._channel = channel
        self._sockets_by_parcel = sockets_by_parcel

    async def _follow_channel(self) -> None:
        async with self._channel.subscribe() as events:
            async for event in events:
                for websocket in tuple(self._sockets_by_parcel.get(event.tracking_number, set())):
                    await websocket.send_text(event.to_json())


# CORRECT — the relay queues; a lagging connection is cut off by the feed, never waited for
@final
class ParcelEventRelay:
    def __init__(self, *, channel: ParcelEventChannel, feed: ParcelFeed) -> None:
        self._channel = channel
        self._feed = feed

    async def _follow_channel(self) -> None:
        async with self._channel.subscribe() as events:
            self._feed.end_all_streams()
            async for event in events:
                self._feed.publish(event)
```

### A room is a key of the feed, carried in a versioned payload — not a channel of its own

**Why:** a channel per parcel is a subscription per parcel on every worker. One channel per kind of
event, the room — here the tracking number — in the payload, a versioned wire model validated on
arrival like any queued message (`python-boundaries`), because during a deploy two versions
publish to the same channel.

**Example:**
```python
# WRONG — a channel name per parcel: every worker subscribes to every parcel anyone follows
def _channel_name(tracking_number: TrackingNumber) -> str:
    return f"parcel-events:{tracking_number}"


# CORRECT — one channel; the parcel and the shape's version travel in the message
class ParcelEventMessage(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore")

    version: Literal[1]
    tracking_number: str
    sequence: int
    status: ParcelStatus
```

## The Whole Example

Checked with `mypy --strict`, and the contract suite run against the fake and against a broker.

```text
parcel_events/
    base.py           # ParcelEventChannel(ABC), ParcelEventChannelLostError
    redis_pubsub.py   # RedisParcelEventChannel — the only file that imports redis
    __init__.py       # the contract, its error and the implementations
relay.py              # ParcelEventRelay — beside the feed, knows only the contract
tests/fakes.py        # InMemoryParcelEventChannel
```

Each implementation is a module named for its mechanism — `redis_pubsub.py`, `nats.py`,
`pg_listen.py`.

```python
@final
class ParcelEventRelay:
    def __init__(
        self,
        *,
        channel: ParcelEventChannel,
        feed: ParcelFeed,
        resubscribe_delay_seconds: float = _RESUBSCRIBE_DELAY_SECONDS,
    ) -> None:
        self._channel = channel
        self._feed = feed
        self._resubscribe_delay_seconds = resubscribe_delay_seconds

    async def run(self) -> None:
        while True:
            try:
                async with self._channel.subscribe() as events:
                    self._feed.end_all_streams()
                    async for event in events:
                        self._feed.publish(event)
            except ParcelEventChannelLostError:
                logger.warning("parcel event subscription lost", exc_info=True)
            await asyncio.sleep(self._resubscribe_delay_seconds)
```

The composition root builds the channel and the feed once, runs the relay in its task group and
cancels it at shutdown; request handlers are handed the channel, never the feed.

The fake drops its subscriptions on demand, which the relay's own unit test needs; it lives in
`tests/fakes.py` and passes the same suite as every broker implementation (`python-contracts`):

```python
@final
class InMemoryParcelEventChannel(ParcelEventChannel):
    def __init__(self) -> None:
        self._subscriptions: set[asyncio.Queue[ParcelEvent]] = set()

    @override
    async def publish(self, event: ParcelEvent) -> None:
        for events in self._subscriptions:
            events.put_nowait(event)

    @override
    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[ParcelEvent]]:
        events = asyncio.Queue[ParcelEvent]()
        self._subscriptions.add(events)
        try:
            yield _drain(events)
        finally:
            self._subscriptions.discard(events)

    def drop_subscriptions(self) -> None:
        for events in self._subscriptions:
            events.shutdown()
        self._subscriptions.clear()


async def _drain(events: asyncio.Queue[ParcelEvent]) -> AsyncIterator[ParcelEvent]:
    while True:
        try:
            yield await events.get()
        except asyncio.QueueShutDown as error:
            raise ParcelEventChannelLostError("dropped by the test") from error
```

The `channel` fixture parametrizes over the fake and every real implementation; the tests are
written once against the contract. The loss case is the same test with the subscription dropped in
the middle — `drop_subscriptions()` on the fake, the broker's own way of cutting a subscriber for a
real one — and `pytest.raises(ParcelEventChannelLostError)` around the next `anext`:

```python
async def test_published_event_reaches_a_live_subscription(channel: ParcelEventChannel) -> None:
    async with channel.subscribe() as events:
        await channel.publish(_OUT_FOR_DELIVERY)

        async with asyncio.timeout(_DELIVERY_TIMEOUT_SECONDS):
            received = await anext(events)

    assert received == _OUT_FOR_DELIVERY
```

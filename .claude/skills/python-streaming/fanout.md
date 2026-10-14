# Fan-Out Across Workers

## Contents

- One subscription per worker, behind a channel contract
- The contract states at-most-once delivery and raises on a gap
- Streams end when a subscription goes live
- The relay only queues
- A room is a key of the feed
- The whole example: layout, relay, wiring, the fake and the contract suite

Redis pub/sub and how redis-py shows a gap are in `python-redis`; the lifespan that builds the
channel and runs the relay in a FastAPI service is in `python-fastapi`.

### Each worker subscribes once to a channel between processes, and publishes to the channel

**Why:** an in-process subscriber set reaches only the connections on the same process — with two
workers or two replicas, a bid placed on one never arrives at bidders of the other. Each worker
subscribes **once** and fans out locally through the bounded queues of `SKILL.md`; one
subscription per connection multiplies the broker's load by the connection count. A request
handler publishes to the channel, never to the feed. The durable log behind `Last-Event-ID` is
separate: a pub/sub channel forgets what nobody was listening for.

**Example:**
```python
# WRONG — the bid reaches only the bidders connected to this worker
@final
class BidDesk:
    def __init__(self, *, feed: BidFeed, history: BidHistory) -> None:
        self._feed = feed
        self._history = history

    async def place(self, offer: BidOffer) -> None:
        bid = await self._history.append(offer)
        self._feed.publish(bid)


# CORRECT — every worker's relay receives it and fans it out to its own connections
@final
class BidDesk:
    def __init__(self, *, bid_channel: BidChannel, history: BidHistory) -> None:
        self._bid_channel = bid_channel
        self._history = history

    async def place(self, offer: BidOffer) -> None:
        bid = await self._history.append(offer)
        await self._bid_channel.publish(bid)
```

### The channel is a contract that states at-most-once delivery and raises on a gap

**Why:** Redis pub/sub, a NATS subject and PostgreSQL `LISTEN` are implementations of one
capability, and every client library hides a dropped subscription differently — some reconnect
and resubscribe without raising, and the bid placed in between is never delivered. The relay's
correctness rests on two things the contract therefore states: delivery is at most once, and **a
subscription that may have missed a bid raises while iterating** — not only on leaving the
`async with`, where the relay's loop would never see it.

**Example:**
```python
# WRONG — nothing says what a dropped subscription does, so each implementation decides
class BidChannel(ABC):
    @abstractmethod
    async def publish(self, bid: Bid) -> None: ...

    @abstractmethod
    def subscribe(self) -> AbstractAsyncContextManager[AsyncIterator[Bid]]: ...


# CORRECT — the gap is part of the contract, with its own error
class BidChannelLostError(AuctionError):
    """The subscription ended, and a bid placed meanwhile may never arrive."""


class BidChannel(ABC):
    """Carries bids between worker processes, each bid at most once."""

    @abstractmethod
    async def publish(self, bid: Bid) -> None: ...

    @abstractmethod
    def subscribe(self) -> AbstractAsyncContextManager[AsyncIterator[Bid]]:
        """Enter once live; iterating raises BidChannelLostError if a bid is lost."""
```

### Every time a subscription goes live, the relay ends the worker's streams

**Why:** a stream opened while the channel was down replayed from the log, then followed a feed
nothing was filling; one open across the drop missed what was placed during it. Ended, each
reconnects — SSE with `Last-Event-ID`, a WebSocket after 1013 — and replays from its own id.

**Example:**
```python
# WRONG — the relay resubscribes and carries on: a stream that missed bids never learns it
@final
class BidRelay:
    def __init__(self, *, channel: BidChannel, feed: BidFeed) -> None:
        self._channel = channel
        self._feed = feed

    async def _follow_channel(self) -> None:
        async with self._channel.subscribe() as bids:
            async for bid in bids:
                self._feed.publish(bid)


# CORRECT — the subscription is live: every stream from before it resumes from its own id
@final
class BidRelay:
    def __init__(self, *, channel: BidChannel, feed: BidFeed) -> None:
        self._channel = channel
        self._feed = feed

    async def _follow_channel(self) -> None:
        async with self._channel.subscribe() as bids:
            self._feed.end_all_streams()
            async for bid in bids:
                self._feed.publish(bid)
```

### The relay only queues; it never awaits a socket

**Why:** sending to each connection in turn lets one bidder who stops reading stall the room, then
the subscription behind it, until the broker drops a subscriber that does not read.
`feed.publish` is `put_nowait` into the bounded queues, and each connection's own push task does
the sending — the `CORRECT` relay above.

**Example:**
```python
# WRONG — the relay awaits every bidder in the room: one that stops reading stalls them all
@final
class BidRelay:
    def __init__(
        self, *, channel: BidChannel, connections_by_lot: Mapping[LotId, set[BidderConnection]]
    ) -> None:
        self._channel = channel
        self._connections_by_lot = connections_by_lot

    async def _follow_channel(self) -> None:
        async with self._channel.subscribe() as bids:
            async for bid in bids:
                for connection in tuple(self._connections_by_lot.get(bid.lot_id, set())):
                    await connection.send(bid.to_json())
```

### A room is a key of the feed, carried in a versioned payload — not a channel of its own

**Why:** a channel per lot is a subscription per lot on every worker. One channel per kind of
event, the room — here the lot — in the payload, a versioned wire model validated on arrival like
any queued message, because during a deploy two versions publish to the same channel.

**Example:**
```python
# WRONG — a channel name per lot: every worker subscribes to every lot anyone follows
def _lot_channel_name(lot_id: LotId) -> str:
    return f"bids:{lot_id}"


# CORRECT — one channel; the lot and the shape's version travel in the message
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class BidMessage:
    version: Literal[1]
    lot_id: str
    sequence: int
    amount_minor_units: int
```

## The Whole Example

Checked with `mypy --strict`, and the contract suite run against the fake and against a broker.

```text
bid_channels/
    base.py           # BidChannel(ABC), BidChannelLostError
    redis_pubsub.py   # RedisBidChannel — the only file that imports redis
    __init__.py       # the contract, its error and the implementations
relay.py              # BidRelay — beside the feed, knows only the contract
tests/fakes.py        # InMemoryBidChannel
```

Each implementation is a module named for its mechanism — `redis_pubsub.py`, `nats.py`,
`pg_listen.py`.

```python
@final
class BidRelay:
    def __init__(
        self,
        *,
        channel: BidChannel,
        feed: BidFeed,
        resubscribe_delay_seconds: float = _RESUBSCRIBE_DELAY_SECONDS,
    ) -> None:
        self._channel = channel
        self._feed = feed
        self._resubscribe_delay_seconds = resubscribe_delay_seconds

    async def run(self) -> None:
        while True:
            try:
                async with self._channel.subscribe() as bids:
                    self._feed.end_all_streams()
                    async for bid in bids:
                        self._feed.publish(bid)
            except BidChannelLostError:
                logger.warning("bid subscription lost", exc_info=True)
            await asyncio.sleep(self._resubscribe_delay_seconds)
```

The composition root builds the channel and the feed once, runs the relay in its task group and
cancels it at shutdown; request handlers are handed the channel, never the feed.

The fake drops its subscriptions on demand, which the relay's own unit test needs; it lives in
`tests/fakes.py` and passes the same suite as every broker implementation:

```python
@final
class InMemoryBidChannel(BidChannel):
    def __init__(self) -> None:
        self._subscriptions: set[asyncio.Queue[Bid]] = set()

    @override
    async def publish(self, bid: Bid) -> None:
        for bids in self._subscriptions:
            bids.put_nowait(bid)

    @override
    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[AsyncIterator[Bid]]:
        bids = asyncio.Queue[Bid]()
        self._subscriptions.add(bids)
        try:
            yield _drain(bids)
        finally:
            self._subscriptions.discard(bids)

    def drop_subscriptions(self) -> None:
        for bids in self._subscriptions:
            bids.shutdown()
        self._subscriptions.clear()


async def _drain(bids: asyncio.Queue[Bid]) -> AsyncIterator[Bid]:
    while True:
        try:
            yield await bids.get()
        except asyncio.QueueShutDown as error:
            raise BidChannelLostError("dropped by the test") from error
```

The `channel` fixture parametrizes over the fake and every real implementation; the tests are
written once against the contract. The loss case is the same test with the subscription dropped in
the middle — `drop_subscriptions()` on the fake, the broker's own way of cutting a subscriber for a
real one — and `pytest.raises(BidChannelLostError)` around the next `anext`:

```python
async def test_published_bid_reaches_a_live_subscription(channel: BidChannel) -> None:
    async with channel.subscribe() as bids:
        await channel.publish(_OPENING_BID)

        async with asyncio.timeout(_DELIVERY_TIMEOUT_SECONDS):
            received = await anext(bids)

    assert received == _OPENING_BID
```

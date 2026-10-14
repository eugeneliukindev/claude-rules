---
name: python-streaming
description: >-
  Designs long-lived responses whatever serves them: release on disconnect, bounded queues,
  deadlines, the SSE and WebSocket protocols, fan-out across workers, downloads. Use when code
  yields events to a client, returns a StreamingResponse or EventSourceResponse, accepts a
  WebSocket, streams a file or an export, or syncs connections between processes. Not for asyncio
  in general (python-async).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Streaming

A response that lives for minutes instead of milliseconds, whatever serves it; the examples run on
Python 3.13+ (`asyncio.Queue.shutdown`). Structured concurrency and cancellation are
`python-async`. Serving a stream from FastAPI — the response classes, Starlette's WebSocket,
uvicorn's flags, the test clients — is `python-fastapi`; GraphQL subscriptions are
`python-strawberry`, gRPC server streams `python-grpc`, and redis pub/sub, which can carry
fan-out between processes, `python-redis`. A script does not serve connections, so none of this applies there.

**The mechanism follows who talks.** The server only — SSE: plain HTTP, and the browser reconnects
and resumes by itself. Both sides — a WebSocket. A finite body too large to build in memory — a
streamed download.

## The Client Leaves Without Saying So

### Everything a stream holds is released by `async with` or `finally` inside the generator

**Why:** when the client goes, the server cancels the generator where it awaits, or the next send
fails — either way the code after the loop never runs, and whatever it was meant to release stays
held. The disconnect arrives as `CancelledError`; caught to carry on, the stream outlives its
client and keeps its subscription forever.

**Example:**
```python
# WRONG — on disconnect the generator is cancelled inside get(), and the queue stays registered
async def follow_lot(lot_id: LotId, *, feed: BidFeed) -> AsyncGenerator[Bid]:
    bids = feed.add_subscriber(lot_id)
    while True:
        try:
            bid = await bids.get()
        except asyncio.QueueShutDown:
            break
        yield bid
    feed.remove_subscriber(lot_id, bids)


# CORRECT — the context manager removes the queue however the stream ends
async def follow_lot(lot_id: LotId, *, feed: BidFeed) -> AsyncGenerator[Bid]:
    async with feed.subscribe(lot_id) as bids:
        while True:
            try:
                bid = await bids.get()
            except asyncio.QueueShutDown:
                return
            yield bid
```

### Release on disconnect is tested on the generator itself

**Why:** closing the generator runs the same `finally` a cancellation runs, without a server or a
client: take one bid, `aclose()`, and assert the feed has no subscriber left.

**Example:**
```python
# WRONG — asserts the bid and never the release, so a leaked subscription passes
async def test_follow_lot_yields_placed_bid() -> None:
    feed = BidFeed()
    bids = follow_lot(_LOT_ID, feed=feed)
    first_bid = asyncio.create_task(anext(bids))
    await _wait_until_subscribed(feed, _LOT_ID)

    feed.publish(_OPENING_BID)

    assert await first_bid == _OPENING_BID


# CORRECT — the stream is closed, and the subscription is asserted gone
async def test_follow_lot_releases_subscription_when_closed() -> None:
    feed = BidFeed()
    bids = follow_lot(_LOT_ID, feed=feed)
    first_bid = asyncio.create_task(anext(bids))
    await _wait_until_subscribed(feed, _LOT_ID)
    feed.publish(_OPENING_BID)
    await first_bid

    await bids.aclose()

    assert feed.subscriber_count(_LOT_ID) == 0
```

## A Slow Client Is Cut Off, Not Buffered

### Every connection has a bounded queue, and the publisher never waits on one

**Why:** an unbounded queue turns one stalled phone into the worker's memory; an awaited `put`
stalls every other bidder behind it. `put_nowait`; on `QueueFull` the subscriber is shut down and
removed in the same step — `put_nowait` on a shut-down queue raises `QueueShutDown` — its stream
ends, and the client reconnects and resumes from its last id.

**Example:**
```python
# WRONG — an unbounded queue per subscriber: a client that stops reading grows it without limit
@final
class BidFeed:
    def __init__(self) -> None:
        self._queues_by_lot: dict[LotId, set[asyncio.Queue[Bid]]] = {}

    def _add_queue(self, lot_id: LotId) -> asyncio.Queue[Bid]:
        bids = asyncio.Queue[Bid]()
        self._queues_by_lot.setdefault(lot_id, set()).add(bids)
        return bids

    def publish(self, bid: Bid) -> None:
        for bids in self._queues_by_lot.get(bid.lot_id, set()):
            bids.put_nowait(bid)


# CORRECT — each queue is bounded; a subscriber that falls behind is shut down and removed
@final
class BidFeed:
    def __init__(self, *, max_pending_bids: int = _MAX_PENDING_BIDS) -> None:
        self._max_pending_bids = max_pending_bids
        self._queues_by_lot: dict[LotId, set[asyncio.Queue[Bid]]] = {}

    def _add_queue(self, lot_id: LotId) -> asyncio.Queue[Bid]:
        bids = asyncio.Queue[Bid](maxsize=self._max_pending_bids)
        self._queues_by_lot.setdefault(lot_id, set()).add(bids)
        return bids

    def publish(self, bid: Bid) -> None:
        subscribers = self._queues_by_lot.get(bid.lot_id, set())
        for bids in tuple(subscribers):
            try:
                bids.put_nowait(bid)
            except asyncio.QueueFull:
                bids.shutdown(immediate=True)
                subscribers.discard(bids)
```

### The send itself has a deadline

**Why:** a client whose TCP window is full blocks a send indefinitely, and the connection holds its
task and its queue with it. The deadline wraps each send; how a framework exposes one is its own
skill.

**Example:**
```python
# WRONG — a client that stops reading parks this task on send forever
async def push_bids(bids: asyncio.Queue[Bid], *, send: Callable[[str], Awaitable[None]]) -> None:
    while True:
        bid = await bids.get()
        await send(bid.to_json())


# CORRECT — a send that cannot complete in time ends the connection
async def push_bids(
    bids: asyncio.Queue[Bid],
    *,
    send: Callable[[str], Awaitable[None]],
    send_timeout_seconds: float = _SEND_TIMEOUT_SECONDS,
) -> None:
    while True:
        bid = await bids.get()
        async with asyncio.timeout(send_timeout_seconds):
            await send(bid.to_json())
```

## A Connection Has a Deadline

### A stream ends after a maximum lifetime, under a deadline that wraps an `await`, never a `yield`

**Why:** without a lifetime, a token checked at the handshake expires while the stream lives on, a
deploy cannot drain, and load stays pinned to the workers that were up when the connection opened;
SSE reconnects by itself, a WebSocket closes with a code the client acts on (`websocket.md`). The
server's own drain at shutdown is set below the orchestrator's kill grace period, and the lifetime
bounds what is left. A timeout scope open across a `yield` fires in whichever task is iterating the
generator — measured: the response task was cancelled from outside, and the generator's
`except TimeoutError` never ran (PEP 789).

**Example:**
```python
# WRONG — the scope spans the yield: at the deadline it cancels the response, not this loop
async def follow_lot(
    lot_id: LotId, *, feed: BidFeed, max_open_seconds: float
) -> AsyncGenerator[Bid]:
    async with feed.subscribe(lot_id) as bids:
        try:
            async with asyncio.timeout(max_open_seconds):
                while True:
                    yield await bids.get()
        except (TimeoutError, asyncio.QueueShutDown):
            return


# CORRECT — one deadline, and each wait for a bid runs under it; the yield is outside
async def follow_lot(
    lot_id: LotId, *, feed: BidFeed, max_open_seconds: float
) -> AsyncGenerator[Bid]:
    deadline = asyncio.get_running_loop().time() + max_open_seconds
    async with feed.subscribe(lot_id) as bids:
        while True:
            try:
                async with asyncio.timeout_at(deadline):
                    bid = await bids.get()
            except (TimeoutError, asyncio.QueueShutDown):
                return
            yield bid
```

### A stream never holds a transaction or a pooled connection while it waits

**Why:** a transaction held for a stream's life holds a pooled connection, and ten idle bidders
drain a pool of ten. The replay is its own short read; the live part reads the feed, not the
database. A framework that keeps a dependency open until the response finishes holds it the same
way.

**Example:**
```python
# WRONG — the history reader, and its connection, stay open until the bidder leaves
async def watch_lot(
    lot_id: LotId, *, history: BidHistory, feed: BidFeed
) -> AsyncGenerator[Bid]:
    async with history.reader() as reader, feed.subscribe(lot_id) as bids:
        for bid in await reader.bids_for(lot_id):
            yield bid
        while True:
            yield await bids.get()


# CORRECT — the replay is one short read, finished before the live part begins
async def watch_lot(
    lot_id: LotId, *, history: BidHistory, feed: BidFeed
) -> AsyncGenerator[Bid]:
    async with feed.subscribe(lot_id) as bids:
        for bid in await history.bids_for(lot_id):
            yield bid
        while True:
            yield await bids.get()
```

## WebSockets

**Before writing the pusher and reader of a WebSocket, choosing its close codes, or checking its
handshake, read [websocket.md](websocket.md)** — pusher and reader in one `TaskGroup`, a code for
each ending, authentication and `Origin` before accepting, each message validated, the frame size.

## Server-Sent Events

**Before emitting server-sent events, setting an event `id`, resuming from `Last-Event-ID`, or
keeping an idle stream alive, read [sse.md](sse.md)** — the browser's connection limit,
heartbeats and buffering, ids from a durable log, subscribe before replay, `retry:`.

## Fan-Out Across Workers

**Before publishing an event that connections on other workers or replicas must receive, or
writing the relay between a broker and the feed, read [fanout.md](fanout.md)** — one subscription
per worker behind a channel contract, streams ended when a subscription goes live, a relay that
only queues, rooms in the payload, gaps raised while iterating, the fake and the contract suite.

## Downloads

**Before streaming an export of a large table, read [downloads.md](downloads.md)** — pages by key
in short reads, nothing held while the client downloads.

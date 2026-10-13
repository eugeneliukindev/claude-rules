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
`python-strawberry`, gRPC server streams `python-grpc`, and the redis channel behind fan-out
`python-redis`. A script does not serve connections, so none of this applies there.

**The mechanism follows who talks.** The server only — SSE: plain HTTP, and the browser reconnects
and resumes by itself. Both sides — a WebSocket. A finite body too large to build in memory — a
streamed download.

## The Client Leaves Without Saying So

### Everything a stream holds is released by `async with` or `finally` inside the generator

**Why:** when the client goes, the server cancels the generator where it awaits, or the next send
fails — either way the code after the loop never runs, and whatever it was meant to release stays
held.

**Example:**
```python
# WRONG — on disconnect the generator is cancelled inside get(), and the queue stays registered
async def follow_parcel(
    tracking_number: TrackingNumber, *, feed: ParcelFeed
) -> AsyncGenerator[ParcelEvent]:
    events = feed.add_subscriber(tracking_number)
    while True:
        try:
            event = await events.get()
        except asyncio.QueueShutDown:
            break
        yield event
    feed.remove_subscriber(tracking_number, events)


# CORRECT — the context manager removes the queue however the stream ends
async def follow_parcel(
    tracking_number: TrackingNumber, *, feed: ParcelFeed
) -> AsyncGenerator[ParcelEvent]:
    async with feed.subscribe(tracking_number) as events:
        while True:
            try:
                event = await events.get()
            except asyncio.QueueShutDown:
                return
            yield event
```

### `CancelledError` is the disconnect, and it is never caught to carry on

**Why:** caught and continued, the stream outlives its client and keeps its subscription forever
(`python-async`).

**Example:**
```python
# WRONG — the cancellation is swallowed, and the loop waits for the next event for nobody
async def follow_parcel(
    tracking_number: TrackingNumber, *, feed: ParcelFeed
) -> AsyncGenerator[ParcelEvent]:
    async with feed.subscribe(tracking_number) as events:
        while True:
            try:
                event = await events.get()
            except asyncio.CancelledError:
                logger.info("tracking client left", extra={"tracking_number": tracking_number})
                continue
            yield event


# CORRECT — cancellation propagates, and async with releases the subscription
async def follow_parcel(
    tracking_number: TrackingNumber, *, feed: ParcelFeed
) -> AsyncGenerator[ParcelEvent]:
    async with feed.subscribe(tracking_number) as events:
        while True:
            try:
                event = await events.get()
            except asyncio.QueueShutDown:
                return
            yield event
```

### Release on disconnect is tested on the generator itself

**Why:** closing the generator runs the same `finally` a cancellation runs, without a server or a
client: take one event, `aclose()`, and assert the feed has no subscriber left.

**Example:**
```python
# WRONG — asserts the event and never the release, so a leaked subscription passes
async def test_follow_parcel_yields_published_event() -> None:
    feed = ParcelFeed()
    events = follow_parcel(_TRACKING_NUMBER, feed=feed)
    first_event = asyncio.create_task(anext(events))
    await _wait_for_subscriber(feed, _TRACKING_NUMBER)

    feed.publish(_OUT_FOR_DELIVERY)

    assert await first_event == _OUT_FOR_DELIVERY


# CORRECT — the stream is closed, and the subscription is asserted gone
async def test_follow_parcel_releases_subscription_when_closed() -> None:
    feed = ParcelFeed()
    events = follow_parcel(_TRACKING_NUMBER, feed=feed)
    first_event = asyncio.create_task(anext(events))
    await _wait_for_subscriber(feed, _TRACKING_NUMBER)
    feed.publish(_OUT_FOR_DELIVERY)
    await first_event

    await events.aclose()

    assert feed.subscriber_count(_TRACKING_NUMBER) == 0
```

## A Slow Client Is Cut Off, Not Buffered

### Every connection has a bounded queue, and the publisher never waits on one

**Why:** an unbounded queue turns one stalled phone into the worker's memory; an awaited `put`
stalls every other subscriber behind it. `put_nowait`; on `QueueFull` the subscriber is shut down
and removed in the same step — `put_nowait` on a shut-down queue raises `QueueShutDown` — its
stream ends, and the client reconnects and resumes from its last id.

**Example:**
```python
# WRONG — an unbounded queue per subscriber: a client that stops reading grows it without limit
@final
class ParcelFeed:
    def __init__(self) -> None:
        self._queues_by_parcel: dict[TrackingNumber, set[asyncio.Queue[ParcelEvent]]] = {}

    def _add_queue(self, tracking_number: TrackingNumber) -> asyncio.Queue[ParcelEvent]:
        events = asyncio.Queue[ParcelEvent]()
        self._queues_by_parcel.setdefault(tracking_number, set()).add(events)
        return events

    def publish(self, event: ParcelEvent) -> None:
        for events in self._queues_by_parcel.get(event.tracking_number, set()):
            events.put_nowait(event)


# CORRECT — each queue is bounded; a subscriber that falls behind is shut down and removed
@final
class ParcelFeed:
    def __init__(self, *, max_pending_events: int = _MAX_PENDING_EVENTS) -> None:
        self._max_pending_events = max_pending_events
        self._queues_by_parcel: dict[TrackingNumber, set[asyncio.Queue[ParcelEvent]]] = {}

    def _add_queue(self, tracking_number: TrackingNumber) -> asyncio.Queue[ParcelEvent]:
        events = asyncio.Queue[ParcelEvent](maxsize=self._max_pending_events)
        self._queues_by_parcel.setdefault(tracking_number, set()).add(events)
        return events

    def publish(self, event: ParcelEvent) -> None:
        subscribers = self._queues_by_parcel.get(event.tracking_number, set())
        for events in tuple(subscribers):
            try:
                events.put_nowait(event)
            except asyncio.QueueFull:
                events.shutdown(immediate=True)
                subscribers.discard(events)
```

### The send itself has a deadline

**Why:** a client whose TCP window is full blocks a send indefinitely, and the connection holds its
task and its queue with it. The deadline wraps each send; how a framework exposes one is its own
skill.

**Example:**
```python
# WRONG — a client that stops reading parks this task on send forever
async def push_events(
    events: asyncio.Queue[ParcelEvent], *, send: Callable[[str], Awaitable[None]]
) -> None:
    while True:
        event = await events.get()
        await send(event.to_json())


# CORRECT — a send that cannot complete in time ends the connection
async def push_events(
    events: asyncio.Queue[ParcelEvent], *, send: Callable[[str], Awaitable[None]]
) -> None:
    while True:
        event = await events.get()
        async with asyncio.timeout(_SEND_TIMEOUT_SECONDS):
            await send(event.to_json())
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
async def follow_parcel(
    tracking_number: TrackingNumber, *, feed: ParcelFeed, lifetime_seconds: float
) -> AsyncGenerator[ParcelEvent]:
    async with feed.subscribe(tracking_number) as events:
        try:
            async with asyncio.timeout(lifetime_seconds):
                while True:
                    yield await events.get()
        except (TimeoutError, asyncio.QueueShutDown):
            return


# CORRECT — one deadline, and each wait for an event runs under it; the yield is outside
async def follow_parcel(
    tracking_number: TrackingNumber, *, feed: ParcelFeed, lifetime_seconds: float
) -> AsyncGenerator[ParcelEvent]:
    deadline = asyncio.get_running_loop().time() + lifetime_seconds
    async with feed.subscribe(tracking_number) as events:
        while True:
            try:
                async with asyncio.timeout_at(deadline):
                    event = await events.get()
            except (TimeoutError, asyncio.QueueShutDown):
                return
            yield event
```

### A stream never holds a transaction or a pooled connection while it waits

**Why:** a transaction held for a stream's life holds a pooled connection, and ten idle listeners
drain a pool of ten. The replay is its own short read (`python-persistence`); the live part reads
the feed, not the database. A framework that keeps a dependency open until the response finishes
holds it the same way.

**Example:**
```python
# WRONG — the history reader, and its connection, stay open until the client leaves
async def stream_parcel(
    tracking_number: TrackingNumber, *, history: ParcelHistory, feed: ParcelFeed
) -> AsyncIterator[ParcelEvent]:
    async with history.reader() as reader, feed.subscribe(tracking_number) as events:
        for event in await reader.events_for(tracking_number):
            yield event
        while True:
            yield await events.get()


# CORRECT — the replay is one short read, finished before the live part begins
async def stream_parcel(
    tracking_number: TrackingNumber, *, history: ParcelHistory, feed: ParcelFeed
) -> AsyncIterator[ParcelEvent]:
    async with feed.subscribe(tracking_number) as events:
        for event in await history.events_for(tracking_number):
            yield event
        while True:
            yield await events.get()
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

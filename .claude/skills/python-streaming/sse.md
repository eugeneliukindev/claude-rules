# Server-Sent Events

## Contents

- An idle stream sends a heartbeat below the shortest idle timeout
- An event id is a position in a durable log
- Subscribe, then replay, then follow live

The protocol, whatever serves it; the response classes, their ping and buffering headers, the
`Last-Event-ID` header parameter and testing an SSE route are in `python-fastapi`.

A browser opens about six HTTP/1.1 connections to one origin, and every open `EventSource` holds
one: the seventh tab waits. SSE is served behind a proxy that speaks HTTP/2 to the browser, or one
stream is shared between tabs.

### An idle stream sends something below the shortest idle timeout on the path

**Why:** proxies and load balancers commonly cut a silent connection after about a minute, and a
dead client is discovered only by a send that fails. A comment line — `: ping` — is ignored by
`EventSource`. The path also must not buffer the stream: a proxy that collects the response
delivers the events in one late burst.

**Example:**
```python
# WRONG — a quiet parcel sends nothing, and the proxy closes the stream after a minute
async def sse_frames(events: AsyncIterator[ParcelEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield f"id: {event.sequence}\ndata: {event.to_json()}\n\n"


# CORRECT — a comment whenever the stream has been quiet for the heartbeat interval
async def sse_frames(
    events: AsyncIterator[ParcelEvent], *, heartbeat_seconds: float = _HEARTBEAT_SECONDS
) -> AsyncIterator[str]:
    while True:
        try:
            async with asyncio.timeout(heartbeat_seconds):
                event = await anext(events)
        except TimeoutError:
            yield ": ping\n\n"
            continue
        except StopAsyncIteration:
            return
        yield f"id: {event.sequence}\ndata: {event.to_json()}\n\n"
```

### An event `id` is a position in a durable log, never a counter in memory

**Why:** on reconnect the browser sends the last id back as `Last-Event-ID`, possibly to another
worker, where a process counter means nothing. The id is the event's sequence in the database or
the broker, and a malformed `Last-Event-ID` is refused as bad input. `retry:` (milliseconds) is
sent once, in the first event — after a restart every client returns at once, so it is not set low.

**Example:**
```python
# WRONG — a per-process counter: after a reconnect to another worker, id 3 is a different event
async def sse_frames(events: AsyncIterator[ParcelEvent]) -> AsyncIterator[str]:
    position = 0
    async for event in events:
        position += 1
        yield f"id: {position}\ndata: {event.to_json()}\n\n"


# CORRECT — the id is the event's sequence in the log, the same on every worker
async def sse_frames(events: AsyncIterator[ParcelEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield f"id: {event.sequence}\ndata: {event.to_json()}\n\n"
```

### A resumed stream subscribes first, then replays, then follows live, skipping what it replayed

**Why:** replay first, and an event published between the query and the subscription is lost for
good; subscribed first, it waits in the queue and is skipped only if the replay already sent it.

**Example:**
```python
# WRONG — an event published during the history query falls between replay and subscription
async def stream_parcel(
    tracking_number: TrackingNumber, *, after: int, history: ParcelHistory, feed: ParcelFeed
) -> AsyncIterator[ParcelEvent]:
    for event in await history.events_after(tracking_number, after):
        yield event
    async with feed.subscribe(tracking_number) as events:
        while True:
            yield await events.get()


# CORRECT — subscribed before the query, so nothing published meanwhile is missed
async def stream_parcel(
    tracking_number: TrackingNumber, *, after: int, history: ParcelHistory, feed: ParcelFeed
) -> AsyncIterator[ParcelEvent]:
    async with feed.subscribe(tracking_number) as events:
        last_sent = after
        for event in await history.events_after(tracking_number, after):
            last_sent = event.sequence
            yield event
        while True:
            event = await events.get()
            if event.sequence > last_sent:
                yield event
```

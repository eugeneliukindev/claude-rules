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
# WRONG — a lot nobody bids on sends nothing, and the proxy closes the stream after a minute
async def bid_frames(bids: AsyncIterator[Bid]) -> AsyncGenerator[str]:
    async for bid in bids:
        yield f"id: {bid.sequence}\ndata: {bid.to_json()}\n\n"


# CORRECT — a comment whenever the stream has been quiet for the heartbeat interval
async def bid_frames(
    bids: AsyncIterator[Bid], *, heartbeat_seconds: float = _HEARTBEAT_SECONDS
) -> AsyncGenerator[str]:
    while True:
        try:
            async with asyncio.timeout(heartbeat_seconds):
                bid = await anext(bids)
        except TimeoutError:
            yield ": ping\n\n"
            continue
        except StopAsyncIteration:
            return
        yield f"id: {bid.sequence}\ndata: {bid.to_json()}\n\n"
```

### An event `id` is a position in a durable log, never a counter in memory

**Why:** on reconnect the browser sends the last id back as `Last-Event-ID`, possibly to another
worker, where a process counter means nothing. The id is the bid's sequence in the database or the
broker, and a malformed `Last-Event-ID` is refused as bad input. `retry:` (milliseconds) is sent
once, in the first event — after a restart every client returns at once, so it is not set low.

**Example:**
```python
# WRONG — a per-process counter: after a reconnect to another worker, id 3 is a different bid
async def bid_frames(bids: AsyncIterator[Bid]) -> AsyncGenerator[str]:
    position = 0
    async for bid in bids:
        position += 1
        yield f"id: {position}\ndata: {bid.to_json()}\n\n"


# CORRECT — the id is the bid's sequence in the log, the same on every worker
async def bid_frames(bids: AsyncIterator[Bid]) -> AsyncGenerator[str]:
    async for bid in bids:
        yield f"id: {bid.sequence}\ndata: {bid.to_json()}\n\n"
```

### A resumed stream subscribes first, then replays, then follows live, skipping what it replayed

**Why:** replay first, and a bid placed between the query and the subscription is lost for good;
subscribed first, it waits in the queue and is skipped only if the replay already sent it.

**Example:**
```python
# WRONG — a bid placed during the history query falls between replay and subscription
async def resume_lot(
    lot_id: LotId, *, after_sequence: int, history: BidHistory, feed: BidFeed
) -> AsyncGenerator[Bid]:
    for bid in await history.bids_after(lot_id, after_sequence):
        yield bid
    async with feed.subscribe(lot_id) as bids:
        while True:
            yield await bids.get()


# CORRECT — subscribed before the query, so nothing placed meanwhile is missed
async def resume_lot(
    lot_id: LotId, *, after_sequence: int, history: BidHistory, feed: BidFeed
) -> AsyncGenerator[Bid]:
    async with feed.subscribe(lot_id) as bids:
        last_sent = after_sequence
        for bid in await history.bids_after(lot_id, after_sequence):
            last_sent = bid.sequence
            yield bid
        while True:
            bid = await bids.get()
            if bid.sequence > last_sent:
                yield bid

---
name: python-streaming
description: >-
  Long-lived and streaming responses in ASGI services — Server-Sent Events, WebSockets and large
  downloads with StreamingResponse, FastAPI's EventSourceResponse, sse-starlette and Starlette's
  WebSocket: noticing the client is gone and releasing in finally, producer and connection in one
  TaskGroup, a bounded queue per connection with a lagging client cut off, heartbeats and proxy
  buffering, event ids and Last-Event-ID resume, a maximum lifetime per connection, no timeout
  across a yield, per-message validation, handshake authentication and Origin checks, no database
  session held by a stream, fan-out across worker processes behind a channel contract whatever the
  broker (redis in python-redis), shutdown and close codes, and testing with websocket_connect and
  a finite SSE stream. Use when Python code returns a StreamingResponse or EventSourceResponse, yields
  from a route, imports sse_starlette, accepts a WebSocket, streams an export or a file to a
  client, or syncs WebSocket rooms between processes.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Streaming Responses

Checked against FastAPI 0.143, Starlette 1.7, sse-starlette 3.5 and uvicorn 0.54, on Python
3.13+ (`asyncio.Queue.shutdown`). Structured concurrency and cancellation are
`python-async`; the factory, lifespan and `Depends` accessors are `python-fastapi`; message models
are `python-pydantic`. This file is what changes when a response lives for minutes instead of
milliseconds. GraphQL subscriptions and gRPC server streams follow the same lifecycle rules; their
mechanics are `python-strawberry` and `python-grpc`. None of it applies to a script: a script does
not serve connections.

**Pick the mechanism by who talks.** The server only — SSE: plain HTTP, and the browser reconnects
and resumes by itself. Both sides — a WebSocket. A finite body too large to build in memory —
`StreamingResponse` over a generator, or `FileResponse` for a file already on disk, which also
answers range requests. For SSE, FastAPI's own `response_class=EventSourceResponse` on a generator
route sends a `: ping` comment after 15 idle seconds and sets `X-Accel-Buffering: no`, with neither
configurable; `sse_starlette.EventSourceResponse` takes `ping=` seconds and `send_timeout=`, and ends
its streams when uvicorn begins shutting down. A plain `StreamingResponse` does none of this.

## The Client Leaves Without Saying So

- **Everything a stream holds is released in `finally` or by `async with` inside the generator.**
  Under uvicorn's HTTP protocol (ASGI spec 2.3) Starlette listens for `http.disconnect` and cancels
  the generator where it awaits; a server on spec 2.4 does not listen, and the generator learns only
  when its next send fails. Either way the code after the loop never runs.

```python
# WRONG — on disconnect the generator is cancelled inside get(), and the queue stays registered
async def follow_order(feed: OrderFeed, order_id: OrderId) -> AsyncGenerator[OrderEvent]:
    events = feed.add_subscriber(order_id)
    while True:
        try:
            event = await events.get()
        except asyncio.QueueShutDown:
            break
        yield event
    feed.remove_subscriber(order_id, events)

# CORRECT — the context manager removes the queue however the stream ends
async def follow_order(feed: OrderFeed, order_id: OrderId) -> AsyncGenerator[OrderEvent]:
    async with feed.subscribe(order_id) as events:
        while True:
            try:
                event = await events.get()
            except asyncio.QueueShutDown:
                return
            yield event
```

- **`CancelledError` is the disconnect; it is never caught to carry on** (`python-async`).
  `await request.is_disconnected()` is a non-blocking poll, for a loop that does expensive work
  between sends on a server that will not cancel it.
- **A WebSocket's producer and reader run in one `TaskGroup`.** The reader is what notices the
  close: `receive_text()` raises `WebSocketDisconnect`, the group cancels the producer, and the
  handler returns. A producer started with `create_task` outlives the socket unless every exit
  path cancels it — measured without the cancel, it stayed parked on a queue nobody would fill.
  `except*` cannot `return`; `pass` and fall out.

```python
# WRONG — the reference is kept, and the pusher still outlives the socket it writes to
@live_router.websocket("/orders/{order_id}/live")
async def follow_order_live(websocket: WebSocket, order_id: OrderId, feed: OrderFeedDep) -> None:
    await websocket.accept()
    async with feed.subscribe(order_id) as events:
        pusher = asyncio.create_task(_push_events(websocket, events))
        try:
            await _read_client_messages(websocket)
        except WebSocketDisconnect:
            pusher.cancel()

# CORRECT — the first task to fail cancels the other; nothing outlives the connection
@live_router.websocket("/orders/{order_id}/live")
async def follow_order_live(websocket: WebSocket, order_id: OrderId, feed: OrderFeedDep) -> None:
    await websocket.accept()
    async with feed.subscribe(order_id) as events:
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(_push_events(websocket, events))
                group.create_task(_read_client_messages(websocket))
        except* WebSocketDisconnect:
            pass
```

The `WRONG` does cancel on a clean close; any other exception out of the reader — a bug, a
malformed frame — skips the `cancel`, and the pusher is left behind.

## A Slow Client Is Cut Off, Not Buffered

- **Every connection gets a bounded queue, and the publisher never waits on one.** `put_nowait`;
  on `QueueFull` the subscriber is shut down and removed, its stream ends, and the client
  reconnects and resumes from its last id. An unbounded queue turns one stalled phone into the
  worker's memory; an awaited `put` stalls every other subscriber behind it.

```python
# WRONG — an unbounded queue per subscriber: a client that stops reading grows it without limit
def publish(self, event: OrderEvent) -> None:
    for events in self._queues_by_order.get(event.order_id, set()):
        events.put_nowait(event)

# CORRECT — each queue holds _MAX_PENDING_EVENTS; a subscriber that falls behind is shut down
def publish(self, event: OrderEvent) -> None:
    subscribers = self._queues_by_order.get(event.order_id, set())
    for events in tuple(subscribers):
        try:
            events.put_nowait(event)
        except asyncio.QueueFull:
            events.shutdown(immediate=True)
            subscribers.discard(events)
```

  Removed in the same step because `put_nowait` on a shut-down queue raises `QueueShutDown`. The
  consumer's `get()` raises it too, which is what ends the stream in `follow_order`.
- **The send itself is bounded**: a client whose TCP window is full blocks `send` indefinitely.
  sse-starlette's `send_timeout` ends the response; around a WebSocket `send_text`, an
  `asyncio.timeout`. sse-starlette's default is no timeout at all.

## Heartbeats, Proxies, Resume

- **An idle stream sends something below the shortest idle timeout on the path** — proxies and
  load balancers commonly cut a silent connection after about a minute, and a dead client is
  discovered only by a send that fails. SSE: a comment line (`: ping`), which `EventSource`
  ignores; both SSE classes above do it. WebSocket: uvicorn's protocol pings (`--ws-ping-interval`,
  20 s by default) — leave them on.
- **Buffering is off along the path.** `X-Accel-Buffering: no` tells nginx not to buffer the
  response; both SSE classes set it, a `StreamingResponse` carrying events must set it itself.
  Starlette's `GZipMiddleware` already skips `text/event-stream`; another compressor may not.
- **An SSE `id` is a position in a durable log** — the event's sequence in the database or the
  broker — never a counter in process memory, which means nothing to the worker the client
  reconnects to. On reconnect the browser sends it back as `Last-Event-ID`:
  `last_event_id: Annotated[int | None, Header()] = None` reads it, and a malformed value is a 422.
- **Subscribe first, then replay what was missed, then follow live, skipping what was replayed.**
  Replay first and an event published between the query and the subscription is lost for good.
- **`retry:` (milliseconds) is sent once, in the first event** — it sets how long the browser waits
  before reconnecting; after a restart every client returns at once, so it is not set low.

## A Connection Has a Deadline

- **Every stream ends by itself after a maximum lifetime**, and the client reconnects: a token
  checked at the handshake expires while the stream lives on, a deploy cannot drain, and load stays
  pinned to the workers that were up when the connection opened. SSE reconnects by itself; a
  WebSocket closes with a code the client acts on.
- **The deadline wraps an `await`, never a `yield`.** A timeout scope open across a `yield` fires
  in whichever task is iterating the generator — measured: the response task was cancelled from
  outside, and the generator's `except TimeoutError` never ran (PEP 789).

```python
# WRONG — the scope spans the yield: at the deadline it cancels the response, not this loop
async def follow_order(
    feed: OrderFeed, order_id: OrderId, *, lifetime_seconds: float
) -> AsyncGenerator[OrderEvent]:
    async with feed.subscribe(order_id) as events:
        try:
            async with asyncio.timeout(lifetime_seconds):
                while True:
                    yield await events.get()
        except (TimeoutError, asyncio.QueueShutDown):
            return

# CORRECT — one deadline, and each wait for an event runs under it; the yield is outside
async def follow_order(
    feed: OrderFeed, order_id: OrderId, *, lifetime_seconds: float
) -> AsyncGenerator[OrderEvent]:
    deadline = asyncio.get_running_loop().time() + lifetime_seconds
    async with feed.subscribe(order_id) as events:
        while True:
            try:
                async with asyncio.timeout_at(deadline):
                    event = await events.get()
            except (TimeoutError, asyncio.QueueShutDown):
                return
            yield event
```

  A WebSocket handler yields nothing, so there the timeout wraps the whole `TaskGroup`, and each
  ending gets its own close code:

```python
@live_router.websocket("/orders/{order_id}/live")
async def follow_order_live(websocket: WebSocket, order_id: OrderId, feed: OrderFeedDep) -> None:
    await websocket.accept()
    try:
        async with (
            feed.subscribe(order_id) as events,
            asyncio.timeout(_CONNECTION_LIFETIME_SECONDS),
            asyncio.TaskGroup() as group,
        ):
            group.create_task(_push_events(websocket, events))
            group.create_task(_read_client_messages(websocket))
    except* WebSocketDisconnect:
        pass
    except* TimeoutError:
        await websocket.close(code=status.WS_1001_GOING_AWAY)
    except* asyncio.QueueShutDown:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
    except* ValidationError:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
```

- **Close codes are a contract with the client**: 1001 and 1012 — reconnect; 1013 — reconnect
  after a backoff; 1008 — do not retry with the same credentials; 1011 — a server error.
- **Shutdown needs the deadline too.** uvicorn sends 1012 to every WebSocket, but waits for open
  HTTP responses — forever, unless `--timeout-graceful-shutdown` is set — and runs the lifespan's
  shutdown only afterwards, so an event set there never reaches a stream. Set the timeout below the
  orchestrator's kill grace period; the maximum lifetime bounds what is left. sse-starlette's
  `shutdown_event` and `shutdown_grace_period` let a stream send a farewell event first.

## The WebSocket Edge

- **Authenticate at the handshake, before `accept()`**, in a dependency on the router that raises
  `WebSocketException(code=status.WS_1008_POLICY_VIOLATION)`. A browser cannot set `Authorization`
  on a WebSocket: the credential is the session cookie, or a short-lived single-use ticket in the
  query string, minted over authenticated HTTP — a URL is logged, so nothing longer-lived goes in
  one. Verifying it is `python-auth`.
- **Check `Origin` against an allowlist.** `CORSMiddleware` passes WebSocket scopes through
  untouched, so a cookie-authenticated socket accepts a connection opened by any page the user
  visits — cross-site WebSocket hijacking.

```python
# WRONG — a cookie-authenticated socket with no Origin check: any site the user visits connects
live_router = APIRouter(dependencies=[Depends(require_session)])

# CORRECT — a foreign origin is refused with 1008 before the handshake completes
async def require_allowed_origin(websocket: WebSocket) -> None:
    if websocket.headers.get("origin") not in _ALLOWED_ORIGINS:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)


live_router = APIRouter(dependencies=[Depends(require_allowed_origin), Depends(require_session)])
```

- **Every incoming message is validated at the edge, one by one**, into a strict discriminated
  union built once as a `TypeAdapter` (`python-pydantic`); a message that fails closes the
  socket with 1003, as the handler above does. `receive_json()` returns `Any`, and a dict passed inward is the unvalidated payload
  `python-boundaries` forbids.

```python
# WRONG — whatever JSON arrives is handed to the service as a dict
async def _read_client_messages(websocket: WebSocket, orders: OrderService) -> None:
    while True:
        await orders.apply_client_message(await websocket.receive_json())

# CORRECT — each frame becomes a typed message or a validation error, here
async def _read_client_messages(websocket: WebSocket, orders: OrderService) -> None:
    while True:
        message = _CLIENT_MESSAGE.validate_json(await websocket.receive_text())
        await orders.apply_client_message(message.to_domain())
```

- **The frame size is bounded by the server**: uvicorn's `--ws-max-size` is 16 MiB by default and
  closes an oversize frame with 1009 — set it to what the protocol needs. A client that sends too
  often is limited per connection like any other input (`python-security`).

## No Database Session for the Life of a Stream

- **A stream never holds a transaction or a pooled connection while it waits.** A dependency with
  `yield` stays open until the response finishes — measured: its `finally` ran after the stream
  ended — so a unit of work taken through `Depends` by a streaming route is held for the stream's
  whole life, and ten idle listeners drain a pool of ten. The replay is its own short read
  (`python-persistence`); the live part reads the feed, not the database.
- **An export from a large table pages by key in short reads** rather than holding one cursor open
  while a slow client downloads; a server-side cursor is acceptable only under the stream's
  deadline, on a pool of its own.

## Fan-Out Across Workers

- **An in-process subscriber set reaches only the connections on the same process.** With two
  workers or two replicas, an event published on one never arrives at clients of the other. Each
  worker subscribes **once** to a channel between processes and fans out locally through the
  bounded queues above — one subscription per worker, never one per connection. The durable log
  behind `Last-Event-ID` is separate: a pub/sub channel forgets what nobody was listening for.
- **The relay depends on a contract, never on a broker.** Redis pub/sub, a NATS subject and
  PostgreSQL `LISTEN` are implementations of one capability (`python-contracts`), and the contract
  states the two things the relay's correctness rests on, which every client library hides
  differently: delivery is at most once, and **a subscription that may have missed an event raises,
  instead of carrying on**.

```python
class OrderEventChannelLostError(Exception):
    """The subscription ended, and an event published meanwhile may never arrive."""


class OrderEventChannel(ABC):
    """Carries order events between worker processes, each event at most once."""

    @abstractmethod
    async def publish(self, event: OrderEvent) -> None: ...

    @abstractmethod
    def subscribe(self) -> AbstractAsyncContextManager[AsyncIterator[OrderEvent]]:
        """Enter once the subscription is live; iterating raises OrderEventChannelLostError
        as soon as an event may have been missed."""
```

- **Every time a subscription goes live, the relay ends the worker's streams.** A stream opened
  while the channel was down replayed from the log, then followed a feed nothing was filling; one
  open across the drop missed what was published during it. Ended, each reconnects — SSE with
  `Last-Event-ID`, a WebSocket after 1013 — and replays from its own id.

```python
# WRONG — the relay resubscribes and carries on: a stream that missed events never learns it
async with self._channel.subscribe() as events:
    async for event in events:
        self._feed.publish(event)

# CORRECT — the subscription is live: every stream from before it resumes from its own id
async with self._channel.subscribe() as events:
    self._feed.end_all_streams()
    async for event in events:
        self._feed.publish(event)
```

- **The relay only queues; it never awaits a socket.** Sending to each connection in turn lets
  one client that stops reading stall its room, then the subscription behind it, until the broker
  drops a subscriber that does not read (redis's limits: `python-redis`). `feed.publish` is
  `put_nowait` into the bounded queues above, and each connection's own push task does the
  sending.

```python
# WRONG — the relay awaits every socket in the room: one client that stops reading stalls them all
async for event in events:
    for websocket in tuple(self._sockets_by_order.get(event.order_id, set())):
        await _send_event(websocket, event)

# CORRECT — the relay queues; a lagging connection is cut off by the feed, never waited for
async for event in events:
    self._feed.publish(event)
```

- **A room is a key of the feed, not a channel.** One channel per kind of event; the room — here
  the order — travels in the payload, a versioned wire model validated on arrival like any queued
  message (`python-boundaries`), because during a deploy two versions publish to the same channel.
- **An implementation turns every sign of a gap into the contract's error, while iterating.**
  Client libraries hide a dropped subscription differently — some reconnect and resubscribe
  without raising, and the event published in between is simply never delivered — so each
  implementation finds its library's signals and raises `OrderEventChannelLostError` from the
  iterator itself (the redis signals and implementation: `python-redis`).

The relay, the wiring, the fake and the contract suite are in [fanout.md](fanout.md).

## Downloads

Streaming instead of materializing is `python-performance`; for a response it means a generator
handed to `StreamingResponse`, with `Content-Disposition` set. A sync generator is iterated in the
thread pool, so blocking reads belong in one; an async generator must not block (`python-async`).

```python
# WRONG — the whole export is built in memory before the first byte leaves
@orders_router.get("/orders/export")
async def export_orders(orders: OrderServiceDep) -> Response:
    lines = [_csv_line(order) async for order in orders.stream_orders()]
    return Response("".join(lines), media_type="text/csv", headers=_EXPORT_HEADERS)

# CORRECT — each line is sent as it is produced; memory stays at one row
@orders_router.get("/orders/export")
async def export_orders(orders: OrderServiceDep) -> StreamingResponse:
    lines = (_csv_line(order) async for order in orders.stream_orders())
    return StreamingResponse(lines, media_type="text/csv", headers=_EXPORT_HEADERS)
```

## Testing

- **A WebSocket is tested through `TestClient.websocket_connect`**, inside `with TestClient(app)`
  so the lifespan runs. A handshake refused before `accept()` raises `WebSocketDisconnect` on
  entering the `with`, carrying the close code.

```python
def test_follow_order_live_refuses_foreign_origin(app: FastAPI) -> None:
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/orders/42/live", headers=_FOREIGN_ORIGIN),
    ):
        pass

    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION
```

- **SSE through a client needs a stream that ends.** Both `TestClient` and httpx2's `ASGITransport`
  collect the whole body before returning, and send `http.disconnect` only after it is complete —
  an endless stream hangs the test. Build the app with a short lifetime and publish once the
  subscriber is registered; the async client and `LifespanManager` are in `python-fastapi`.
- **Release on disconnect is tested on the generator**: take one event, `aclose()` it, and assert
  the feed has no subscriber left — the same `finally` a cancellation runs.

```python
async def test_follow_order_releases_subscription_when_closed() -> None:
    feed = OrderFeed()
    events = follow_order(feed, _ORDER_ID, lifetime_seconds=_LIFETIME_SECONDS)
    first_event = asyncio.create_task(anext(events))
    await _wait_for_subscriber(feed, _ORDER_ID)
    feed.publish(_SHIPPED)
    await first_event

    await events.aclose()

    assert feed.subscriber_count(_ORDER_ID) == 0
```

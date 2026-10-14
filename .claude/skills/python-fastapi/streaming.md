# Streaming in FastAPI

## Contents

- SSE through `EventSourceResponse`, FastAPI's or sse-starlette's
- `Last-Event-ID` as a header parameter
- How a disconnect reaches the route, and `request.is_disconnected()`
- No connection from `Depends` in a streaming route
- The WebSocket handler: one `TaskGroup`, a close code per ending
- `WebSocketDisconnect` ends the reader
- Handshake checks as router dependencies; `CORSMiddleware` skips WebSockets
- `receive_text` and the edge's parser, never `receive_json`
- Downloads through `StreamingResponse`
- uvicorn's flags for long-lived connections
- Tests: `websocket_connect`, and an SSE stream that ends

Checked against FastAPI 0.143, Starlette 1.8, sse-starlette 3.5 and uvicorn 0.54. What a stream
must guarantee whatever the framework — release on disconnect, a bounded queue, a send deadline, a
lifetime, fan-out — is `python-streaming`.

### Events go out through an `EventSourceResponse`, never a bare `StreamingResponse`

**Why:** FastAPI's `response_class=EventSourceResponse` on a generator route sends a `: ping`
comment after 15 idle seconds and sets `X-Accel-Buffering: no` and `Cache-Control: no-cache`, none
of it configurable. `sse_starlette.EventSourceResponse` takes `ping=` seconds — `None`, the
default, means its own 15 seconds, not off — and `send_timeout=`, whose default is no timeout at
all, and ends its streams when uvicorn begins shutting down; `shutdown_event` and
`shutdown_grace_period` let a stream send a farewell event first. A plain `StreamingResponse` does
none of this, and one carrying events sets `X-Accel-Buffering: no` itself; Starlette's
`GZipMiddleware` already skips `text/event-stream`, another compressor may not.

**Example:**
```python
# WRONG — no heartbeat, buffered by the proxy, cached by the browser
@stations_router.get("/stations/{station_id}/availability")
async def station_availability(
    station_id: StationId, history: AvailabilityHistoryDep, feed: AvailabilityFeedDep
) -> StreamingResponse:
    updates = follow_availability(station_id, after=0, history=history, feed=feed)
    return StreamingResponse(encode_sse(updates), media_type="text/event-stream")


# CORRECT — the SSE class frames the updates, pings, and turns buffering and caching off
@stations_router.get("/stations/{station_id}/availability", response_class=EventSourceResponse)
async def station_availability(
    station_id: StationId, history: AvailabilityHistoryDep, feed: AvailabilityFeedDep
) -> AsyncIterator[DockAvailability]:
    async for update in follow_availability(station_id, after=0, history=history, feed=feed):
        yield update
```

### `Last-Event-ID` is a typed header parameter

**Why:** the browser sends it back on reconnect; `Annotated[int | None, Header()]` reads it, and a
malformed value is a 422 before the route runs, where a string parsed by hand fails inside it.

**Example:**
```python
# WRONG — the header is read and parsed by hand, and a malformed one fails mid-stream
@stations_router.get("/stations/{station_id}/availability", response_class=EventSourceResponse)
async def station_availability(
    request: Request,
    station_id: StationId,
    history: AvailabilityHistoryDep,
    feed: AvailabilityFeedDep,
) -> AsyncIterator[DockAvailability]:
    after = int(request.headers.get("last-event-id", "0"))
    async for update in follow_availability(station_id, after=after, history=history, feed=feed):
        yield update


# CORRECT — FastAPI parses it, and refuses a malformed value with 422
@stations_router.get("/stations/{station_id}/availability", response_class=EventSourceResponse)
async def station_availability(
    station_id: StationId,
    history: AvailabilityHistoryDep,
    feed: AvailabilityFeedDep,
    last_event_id: Annotated[int | None, Header()] = None,
) -> AsyncIterator[DockAvailability]:
    after = last_event_id or 0
    async for update in follow_availability(station_id, after=after, history=history, feed=feed):
        yield update
```

### A route that works between sends polls `request.is_disconnected()`

**Why:** under uvicorn's HTTP protocol (ASGI spec 2.3) Starlette listens for `http.disconnect` and
cancels the generator where it awaits; a server on spec 2.4 does not listen, and the generator
learns only when its next send fails. A loop that does expensive work between sends asks
`await request.is_disconnected()`, a non-blocking poll, before each piece.

**Example:**
```python
# WRONG — on a server that does not cancel it, every remaining segment is rendered for nobody
@rides_router.get("/rides/{ride_id}/route", response_class=EventSourceResponse)
async def ride_route(ride_id: RideId, replay: RideReplayDep) -> AsyncIterator[RouteSegment]:
    for segment_number in range(await replay.segment_count(ride_id)):
        yield await replay.render_segment(ride_id, segment_number)


# CORRECT — the route stops rendering the moment the rider is gone
@rides_router.get("/rides/{ride_id}/route", response_class=EventSourceResponse)
async def ride_route(
    request: Request, ride_id: RideId, replay: RideReplayDep
) -> AsyncIterator[RouteSegment]:
    for segment_number in range(await replay.segment_count(ride_id)):
        if await request.is_disconnected():
            return
        yield await replay.render_segment(ride_id, segment_number)
```

### A streaming route takes no connection through `Depends`

**Why:** a dependency with `yield` stays open until the response finishes — measured: its
`finally` ran after the stream ended — so a connection taken through `Depends` is held, out of the
pool, for the stream's whole life. The route takes a history from the lifespan, whose every read
borrows a connection and returns it before the live part begins.

**Example:**
```python
# WRONG — the connection from Depends stays out of the pool until the rider leaves
@stations_router.get("/stations/{station_id}/availability", response_class=EventSourceResponse)
async def station_availability(
    station_id: StationId, connection: ConnectionDep, feed: AvailabilityFeedDep
) -> AsyncIterator[DockAvailability]:
    history = PostgresAvailabilityHistory(connection)
    async for update in follow_availability(station_id, after=0, history=history, feed=feed):
        yield update


# CORRECT — the history borrows a connection per read and returns it
@stations_router.get("/stations/{station_id}/availability", response_class=EventSourceResponse)
async def station_availability(
    station_id: StationId, history: AvailabilityHistoryDep, feed: AvailabilityFeedDep
) -> AsyncIterator[DockAvailability]:
    async for update in follow_availability(station_id, after=0, history=history, feed=feed):
        yield update
```

### A WebSocket handler runs pusher and reader in one `TaskGroup` and closes with a code per ending

**Why:** `receive_text()` raises `WebSocketDisconnect` when the client goes, the group cancels the
pusher, and `except*` — which cannot `return` — passes and falls out. The handler yields nothing,
so the lifetime wraps the whole group, and every other ending closes with its own code through
`websocket.close(code=...)`: 1001 when the lifetime runs out, 1013 when the feed sheds a client too
slow to keep up, 1003 for a frame the edge refuses.

**Example:**
```python
# WRONG — no lifetime, and a clean close cancels the pusher only if the reader ended cleanly
@station_live_router.websocket("/stations/{station_id}/live")
async def watch_station(
    websocket: WebSocket, station_id: StationId, feed: AvailabilityFeedDep
) -> None:
    await websocket.accept()
    async with feed.subscribe(station_id) as updates:
        pusher = asyncio.create_task(_push_updates(updates, websocket=websocket))
        try:
            await _read_rider_messages(websocket)
        except WebSocketDisconnect:
            pusher.cancel()


# CORRECT — one group, one deadline, and a code for each way the connection can end
@station_live_router.websocket("/stations/{station_id}/live")
async def watch_station(
    websocket: WebSocket, station_id: StationId, feed: AvailabilityFeedDep
) -> None:
    await websocket.accept()
    try:
        async with (
            feed.subscribe(station_id) as updates,
            asyncio.timeout(_CONNECTION_LIFETIME_SECONDS),
            asyncio.TaskGroup() as group,
        ):
            group.create_task(_push_updates(updates, websocket=websocket))
            group.create_task(_read_rider_messages(websocket))
    except* WebSocketDisconnect:
        pass
    except* TimeoutError:
        await websocket.close(code=status.WS_1001_GOING_AWAY)
    except* asyncio.QueueShutDown:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
    except* ValidationError:
        await websocket.close(code=status.WS_1003_UNSUPPORTED_DATA)
```

### `WebSocketDisconnect` ends the reader; it is never caught to keep reading

**Why:** after the disconnect message every further `receive` raises `RuntimeError: Cannot call
"receive" once a disconnect message has been received` — the handler that logged the close and
looped turns a normal goodbye into an error.

**Example:**
```python
# WRONG — the close is logged and the loop goes on: the next receive raises RuntimeError
async def _read_rider_messages(websocket: WebSocket) -> None:
    while True:
        try:
            await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info("station watcher left")


# CORRECT — the disconnect leaves the loop, and the TaskGroup ends the connection
async def _read_rider_messages(websocket: WebSocket) -> None:
    while True:
        await websocket.receive_text()
```

### Handshake checks are router dependencies that raise `WebSocketException` with 1008

**Why:** a dependency on the router runs before `accept()`, so a refused connection never opens.
`CORSMiddleware` passes WebSocket scopes through untouched, so a cookie-authenticated socket checks
`Origin` on its own router.

**Example:**
```python
# WRONG — a cookie-authenticated socket with no Origin check: any site the rider visits connects
station_live_router = APIRouter(dependencies=[Depends(require_rider_session)])


# CORRECT — a foreign origin is refused with 1008 before the handshake completes
async def refuse_foreign_origin(websocket: WebSocket) -> None:
    if websocket.headers.get("origin") not in _ALLOWED_ORIGINS:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)


station_live_router = APIRouter(
    dependencies=[Depends(refuse_foreign_origin), Depends(require_rider_session)]
)
```

### A frame is read with `receive_text` and handed to the edge's parser, never `receive_json`

**Why:** `receive_json()` returns `Any`, already decoded in Python mode; the raw text goes to a
parser built once — a strict discriminated union validated as JSON — which returns a typed message
or raises the `ValidationError` that closes with 1003.

**Example:**
```python
# WRONG — whatever JSON arrives is handed to the service as a dict
async def _read_rider_messages(websocket: WebSocket, *, holds: DockHolds) -> None:
    while True:
        await holds.request_hold(await websocket.receive_json())


# CORRECT — each frame becomes a typed message or a ValidationError
async def _read_rider_messages(websocket: WebSocket, *, holds: DockHolds) -> None:
    while True:
        message = parse_rider_message(await websocket.receive_text())
        await holds.request_hold(message.to_domain())
```

### A download is a generator handed to `StreamingResponse`, and blocking reads go in a sync one

**Why:** Starlette iterates a sync generator in its thread pool, so a blocking `read()` there costs
a thread and not the event loop; an async generator must not block. `Content-Disposition` names the
file.

**Example:**
```python
# WRONG — the whole export is built in memory before the first byte leaves
@rides_router.get("/rides/export")
async def export_rides(history: RideHistoryDep) -> Response:
    body = b"".join([line async for line in ride_history_csv(history=history)])
    return Response(body, media_type="text/csv", headers=_EXPORT_HEADERS)


# CORRECT — each line is sent as it is produced
@rides_router.get("/rides/export")
async def export_rides(history: RideHistoryDep) -> StreamingResponse:
    return StreamingResponse(
        ride_history_csv(history=history), media_type="text/csv", headers=_EXPORT_HEADERS
    )
```

### uvicorn is started with the limits a long-lived connection needs

**Why:** uvicorn sends 1012 to every WebSocket at shutdown but runs the lifespan's shutdown only
after the open HTTP responses end, so an event set there never reaches a stream; their drain is
bounded as `serving.md` says. `--ws-max-size` is 16 MiB by default and closes an oversize frame with
1009 — set it to what the protocol needs. `--ws-ping-interval`, 20 seconds by default, is the
WebSocket heartbeat; it stays on.

### A WebSocket is tested through `websocket_connect`, inside `with TestClient(app)`

**Why:** outside the `with` the lifespan never runs, so the feed it builds does not exist. A
handshake refused before `accept()` raises `WebSocketDisconnect` on entering the connection's
`with`, carrying the close code.

**Example:**
```python
# WRONG — no lifespan, and any disconnect passes: a feed that was never built fails it too
def test_watch_station_refuses_foreign_origin(app: FastAPI) -> None:
    client = TestClient(app)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/stations/S-114/live", headers=_FOREIGN_ORIGIN),
    ):
        pass


# CORRECT — the lifespan runs, and the refusal's close code is asserted
def test_watch_station_refuses_foreign_origin(app: FastAPI) -> None:
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/stations/S-114/live", headers=_FOREIGN_ORIGIN),
    ):
        pass

    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION
```

### An SSE route is tested with a stream that ends

**Why:** both `TestClient` and httpx's `ASGITransport` collect the whole body before returning, and
send `http.disconnect` only after it is complete — an endless stream hangs the test. The app is
built with a short lifetime and the update is published once the subscriber is registered, through
the async client and `LifespanManager` of [testing.md](testing.md).

**Example:**
```python
# WRONG — the stream never ends, so the request never returns and the test hangs
def test_station_availability_streams_freed_dock(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/stations/S-114/availability")

    assert "dock_freed" in response.text


# CORRECT — a one-second lifetime ends the stream, after the update published to it
async def test_station_availability_streams_freed_dock() -> None:
    app = build_bike_share_api(database_url=_TEST_DATABASE_URL, stream_lifetime_seconds=1.0)
    async with LifespanManager(app) as manager, _client(manager.app) as client:
        publishing = asyncio.create_task(_publish_when_subscribed(app, _DOCK_FREED))

        response = await client.get("/stations/S-114/availability")

        await publishing
    assert "dock_freed" in response.text
```

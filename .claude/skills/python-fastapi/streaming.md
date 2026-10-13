# Streaming in FastAPI

## Contents

- SSE through `EventSourceResponse`, FastAPI's or sse-starlette's
- `Last-Event-ID` as a header parameter
- How a disconnect reaches the route, and `request.is_disconnected()`
- No connection from `Depends` in a streaming route
- The WebSocket handler: one `TaskGroup`, a close code per ending
- `WebSocketDisconnect` ends the reader
- Handshake checks as router dependencies; `CORSMiddleware` skips WebSockets
- `receive_text` and a `TypeAdapter`, never `receive_json`
- Downloads through `StreamingResponse`
- uvicorn's flags for long-lived connections
- Tests: `websocket_connect`, and an SSE stream that ends

Checked against FastAPI 0.143, Starlette 1.7, sse-starlette 3.5 and uvicorn 0.54. What a stream must
do — release on disconnect, a bounded queue, a send deadline, a lifetime, the WebSocket and SSE
protocols, fan-out — is `python-streaming`.

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
@tracking_router.get("/parcels/{tracking_number}/events")
async def parcel_events(
    tracking_number: TrackingNumber, history: ParcelHistoryDep, feed: ParcelFeedDep
) -> StreamingResponse:
    frames = sse_frames(stream_parcel(tracking_number, after=0, history=history, feed=feed))
    return StreamingResponse(frames, media_type="text/event-stream")


# CORRECT — the SSE class frames the events, pings, and turns buffering and caching off
@tracking_router.get("/parcels/{tracking_number}/events", response_class=EventSourceResponse)
async def parcel_events(
    tracking_number: TrackingNumber, history: ParcelHistoryDep, feed: ParcelFeedDep
) -> AsyncIterator[ParcelEvent]:
    async for event in stream_parcel(tracking_number, after=0, history=history, feed=feed):
        yield event
```

### `Last-Event-ID` is a typed header parameter

**Why:** the browser sends it back on reconnect; `Annotated[int | None, Header()]` reads it, and a
malformed value is a 422 before the route runs, where a string parsed by hand fails inside it.

**Example:**
```python
# WRONG — the header is read and parsed by hand, and a malformed one fails mid-stream
@tracking_router.get("/parcels/{tracking_number}/events", response_class=EventSourceResponse)
async def parcel_events(
    request: Request,
    tracking_number: TrackingNumber,
    history: ParcelHistoryDep,
    feed: ParcelFeedDep,
) -> AsyncIterator[ParcelEvent]:
    after = int(request.headers.get("last-event-id", "0"))
    async for event in stream_parcel(tracking_number, after=after, history=history, feed=feed):
        yield event


# CORRECT — FastAPI parses it, and refuses a malformed value with 422
@tracking_router.get("/parcels/{tracking_number}/events", response_class=EventSourceResponse)
async def parcel_events(
    tracking_number: TrackingNumber,
    history: ParcelHistoryDep,
    feed: ParcelFeedDep,
    last_event_id: Annotated[int | None, Header()] = None,
) -> AsyncIterator[ParcelEvent]:
    after = last_event_id or 0
    async for event in stream_parcel(tracking_number, after=after, history=history, feed=feed):
        yield event
```

### A route that works between sends polls `request.is_disconnected()`

**Why:** under uvicorn's HTTP protocol (ASGI spec 2.3) Starlette listens for `http.disconnect` and
cancels the generator where it awaits; a server on spec 2.4 does not listen, and the generator
learns only when its next send fails. A loop that does expensive work between sends asks
`await request.is_disconnected()`, a non-blocking poll, before each piece.

**Example:**
```python
# WRONG — on a server that does not cancel it, every remaining page is rendered for nobody
@reports_router.get("/reports/{report_id}/pages", response_class=EventSourceResponse)
async def report_pages(report_id: ReportId, reports: ReportServiceDep) -> AsyncIterator[Page]:
    for page_number in range(await reports.page_count(report_id)):
        yield await reports.render_page(report_id, page_number)


# CORRECT — the route stops rendering the moment the client is gone
@reports_router.get("/reports/{report_id}/pages", response_class=EventSourceResponse)
async def report_pages(
    request: Request, report_id: ReportId, reports: ReportServiceDep
) -> AsyncIterator[Page]:
    for page_number in range(await reports.page_count(report_id)):
        if await request.is_disconnected():
            return
        yield await reports.render_page(report_id, page_number)
```

### A streaming route takes no connection through `Depends`

**Why:** a dependency with `yield` stays open until the response finishes — measured: its
`finally` ran after the stream ended — so a connection taken through `Depends` is held, out of the
pool, for the stream's whole life. The route takes the history, whose every read borrows a
connection and returns it (`python-streaming`).

**Example:**
```python
# WRONG — the connection from Depends stays out of the pool until the client leaves
@tracking_router.get("/parcels/{tracking_number}/events", response_class=EventSourceResponse)
async def parcel_events(
    tracking_number: TrackingNumber, connection: ConnectionDep, feed: ParcelFeedDep
) -> AsyncIterator[ParcelEvent]:
    history = PostgresParcelHistory(connection)
    async for event in stream_parcel(tracking_number, after=0, history=history, feed=feed):
        yield event


# CORRECT — the history borrows a connection per read and returns it before the live part
@tracking_router.get("/parcels/{tracking_number}/events", response_class=EventSourceResponse)
async def parcel_events(
    tracking_number: TrackingNumber, history: ParcelHistoryDep, feed: ParcelFeedDep
) -> AsyncIterator[ParcelEvent]:
    async for event in stream_parcel(tracking_number, after=0, history=history, feed=feed):
        yield event
```

### A WebSocket handler runs pusher and reader in one `TaskGroup` and closes with a code per ending

**Why:** `receive_text()` raises `WebSocketDisconnect` when the client goes, the group cancels the
pusher, and `except*` — which cannot `return` — passes and falls out. The handler yields nothing,
so the lifetime wraps the whole group, and each other ending closes with the code
`python-streaming` assigns it through `websocket.close(code=...)`.

**Example:**
```python
# WRONG — no lifetime, and a clean close cancels the pusher only if the reader ended cleanly
@live_router.websocket("/parcels/{tracking_number}/live")
async def follow_parcel_live(
    websocket: WebSocket, tracking_number: TrackingNumber, feed: ParcelFeedDep
) -> None:
    await websocket.accept()
    async with feed.subscribe(tracking_number) as events:
        pusher = asyncio.create_task(push_events(events, send=websocket.send_text))
        try:
            await _read_client_messages(websocket)
        except WebSocketDisconnect:
            pusher.cancel()


# CORRECT — one group, one deadline, and a code for each way the connection can end
@live_router.websocket("/parcels/{tracking_number}/live")
async def follow_parcel_live(
    websocket: WebSocket, tracking_number: TrackingNumber, feed: ParcelFeedDep
) -> None:
    await websocket.accept()
    try:
        async with (
            feed.subscribe(tracking_number) as events,
            asyncio.timeout(_CONNECTION_LIFETIME_SECONDS),
            asyncio.TaskGroup() as group,
        ):
            group.create_task(push_events(events, send=websocket.send_text))
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

### `WebSocketDisconnect` ends the reader; it is never caught to keep reading

**Why:** after the disconnect message every further `receive` raises `RuntimeError: Cannot call
"receive" once a disconnect message has been received` — the handler that logged the close and
looped turns a normal goodbye into an error.

**Example:**
```python
# WRONG — the close is logged and the loop goes on: the next receive raises RuntimeError
async def _read_client_messages(websocket: WebSocket) -> None:
    while True:
        try:
            await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info("tracking client left")


# CORRECT — the disconnect leaves the loop, and the TaskGroup ends the connection
async def _read_client_messages(websocket: WebSocket) -> None:
    while True:
        await websocket.receive_text()
```

### Handshake checks are router dependencies that raise `WebSocketException` with 1008

**Why:** a dependency on the router runs before `accept()`, so a refused connection never opens.
`CORSMiddleware` passes WebSocket scopes through untouched, so the `Origin` check is the router's
own; verifying the session or ticket is `python-auth`.

**Example:**
```python
# WRONG — a cookie-authenticated socket with no Origin check: any site the user visits connects
live_router = APIRouter(dependencies=[Depends(require_session)])


# CORRECT — a foreign origin is refused with 1008 before the handshake completes
async def require_allowed_origin(websocket: WebSocket) -> None:
    if websocket.headers.get("origin") not in _ALLOWED_ORIGINS:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)


live_router = APIRouter(dependencies=[Depends(require_allowed_origin), Depends(require_session)])
```

### A frame is read with `receive_text` and validated by a `TypeAdapter`, never `receive_json`

**Why:** `receive_json()` returns `Any`, already decoded in Python mode; the text validated as JSON
by a strict discriminated union built once is the edge `python-streaming` asks for
(`python-pydantic` for the union).

**Example:**
```python
# WRONG — whatever JSON arrives is handed to the service as a dict
async def _read_client_messages(websocket: WebSocket, *, tracking: TrackingService) -> None:
    while True:
        await tracking.apply_client_message(await websocket.receive_json())


# CORRECT — each frame becomes a typed message or a ValidationError, which closes with 1003
async def _read_client_messages(websocket: WebSocket, *, tracking: TrackingService) -> None:
    while True:
        message = _CLIENT_MESSAGE.validate_json(await websocket.receive_text())
        await tracking.apply_client_message(message.to_domain())
```

### A download is a generator handed to `StreamingResponse`, and blocking reads go in a sync one

**Why:** Starlette iterates a sync generator in its thread pool, so a blocking `read()` there costs
a thread and not the event loop; an async generator must not block. `Content-Disposition` names the
file.

**Example:**
```python
# WRONG — the whole export is built in memory before the first byte leaves
@audit_router.get("/audit-log/export")
async def export_audit_log(audit: AuditLogDep) -> Response:
    body = b"".join([line async for line in audit_log_csv(entries=audit)])
    return Response(body, media_type="text/csv", headers=_EXPORT_HEADERS)


# CORRECT — each line is sent as it is produced
@audit_router.get("/audit-log/export")
async def export_audit_log(audit: AuditLogDep) -> StreamingResponse:
    return StreamingResponse(
        audit_log_csv(entries=audit), media_type="text/csv", headers=_EXPORT_HEADERS
    )
```

### uvicorn is started with the limits a long-lived connection needs

**Why:** uvicorn sends 1012 to every WebSocket at shutdown but runs the lifespan's shutdown only
after the open HTTP responses end, so an event set there never reaches a stream; their drain is
bounded as `serving.md` says. `--ws-max-size` is 16 MiB by default and closes an oversize frame with
1009 — set to what the protocol needs. `--ws-ping-interval`, 20 seconds by default, is the WebSocket
heartbeat; it stays on.

### A WebSocket is tested through `websocket_connect`, inside `with TestClient(app)`

**Why:** outside the `with` the lifespan never runs, so the feed and the channel it builds do not
exist. A handshake refused before `accept()` raises `WebSocketDisconnect` on entering the
connection's `with`, carrying the close code.

**Example:**
```python
# WRONG — no lifespan, and any disconnect passes: a feed that was never built fails it too
def test_follow_parcel_live_refuses_foreign_origin(app: FastAPI) -> None:
    client = TestClient(app)

    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/parcels/JD014600/live", headers=_FOREIGN_ORIGIN),
    ):
        pass


# CORRECT — the lifespan runs, and the refusal's close code is asserted
def test_follow_parcel_live_refuses_foreign_origin(app: FastAPI) -> None:
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect) as excinfo,
        client.websocket_connect("/parcels/JD014600/live", headers=_FOREIGN_ORIGIN),
    ):
        pass

    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION
```

### An SSE route is tested with a stream that ends

**Why:** both `TestClient` and httpx's `ASGITransport` collect the whole body before returning, and
send `http.disconnect` only after it is complete — an endless stream hangs the test. The app is
built with a short lifetime and the event is published once the subscriber is registered; the
async client and `LifespanManager` are under Testing in `SKILL.md`.

**Example:**
```python
# WRONG — the stream never ends, so the request never returns and the test hangs
def test_parcel_events_streams_published_event(app: FastAPI) -> None:
    with TestClient(app) as client:
        response = client.get("/parcels/JD014600/events")

    assert "out_for_delivery" in response.text


# CORRECT — a one-second lifetime ends the stream, after the event published to it
async def test_parcel_events_streams_published_event() -> None:
    app = create_app(stream_lifetime_seconds=1.0)
    async with LifespanManager(app) as manager, _client(manager.app) as client:
        publishing = asyncio.create_task(_publish_when_subscribed(app, _OUT_FOR_DELIVERY))

        response = await client.get("/parcels/JD014600/events")

        await publishing
    assert "out_for_delivery" in response.text
```

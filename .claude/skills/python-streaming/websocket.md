# WebSockets

## Contents

- The pusher and the reader in one `TaskGroup`
- Each ending closes with the code the client acts on
- Authentication and `Origin` before the connection is accepted
- Every message validated; the frame size bounded

The protocol and the connection's structure, whatever serves it; Starlette's `WebSocket`, its
disconnect exception, router dependencies and the test client are in `python-fastapi`, and
verifying the credential is `python-auth`.

### The pusher and the reader run in one `TaskGroup`

**Why:** the reader is what notices the close — its receive fails when the client goes, the group
cancels the pusher, and the connection ends. A pusher started with `create_task` outlives the
socket unless every exit path cancels it; measured without the cancel, it stayed parked on a queue
nobody would fill.

**Example:**
```python
# WRONG — a clean close cancels the pusher; any other error out of the reader leaves it behind
async def serve_bidder(
    bids: asyncio.Queue[Bid],
    *,
    send: Callable[[str], Awaitable[None]],
    receive: Callable[[], Awaitable[str]],
    floor: AuctionFloor,
) -> None:
    pusher = asyncio.create_task(push_bids(bids, send=send))
    try:
        await read_bidder_messages(receive=receive, floor=floor)
    except BidderGoneError:
        pusher.cancel()


# CORRECT — the first task to fail cancels the other; nothing outlives the connection
async def serve_bidder(
    bids: asyncio.Queue[Bid],
    *,
    send: Callable[[str], Awaitable[None]],
    receive: Callable[[], Awaitable[str]],
    floor: AuctionFloor,
) -> None:
    async with asyncio.TaskGroup() as group:
        group.create_task(push_bids(bids, send=send))
        group.create_task(read_bidder_messages(receive=receive, floor=floor))
```

### Each way a connection ends closes it with the code the client acts on

**Why:** close codes are a contract with the client: 1001 and 1012 — reconnect; 1013 — reconnect
after a backoff; 1008 — do not retry with the same credentials; 1003 — the client sent what the
protocol does not accept; 1011 — a server error. A connection that ends without a code leaves the
client guessing whether to come back.

**Example:**
```python
# WRONG — every ending looks the same to the bidder
def close_code_for(ending: BaseException) -> int:
    return _NORMAL_CLOSURE


# CORRECT — the lifetime, a dropped subscriber, a bad message and a failure each say what to do
def close_code_for(ending: BaseException) -> int:
    match ending:
        case TimeoutError():
            return _GOING_AWAY
        case asyncio.QueueShutDown():
            return _TRY_AGAIN_LATER
        case MalformedBidderMessageError():
            return _UNSUPPORTED_DATA
        case _:
            return _INTERNAL_ERROR
```

### A connection is authenticated and its `Origin` checked before it is accepted

**Why:** a browser cannot set `Authorization` on a WebSocket: the credential is the session cookie,
or a short-lived single-use ticket in the query string minted over authenticated HTTP — a URL is
logged, so nothing longer-lived goes in one. A cookie-authenticated socket without an `Origin`
check accepts a connection opened by any page the user visits — cross-site WebSocket hijacking —
and CORS does not apply to the WebSocket handshake. Both checks refuse with 1008 before the
connection is accepted.

**Example:**
```python
# WRONG — any origin is accepted: a page on another site connects with the bidder's cookie
def is_allowed_handshake(headers: Mapping[str, str], *, bidders: BidderSessions) -> bool:
    return bidders.is_valid(headers.get("cookie", ""))


# CORRECT — the origin is on the allowlist, and only then the session counts
def is_allowed_handshake(
    headers: Mapping[str, str], *, bidders: BidderSessions, allowed_origins: frozenset[str]
) -> bool:
    return headers.get("origin") in allowed_origins and bidders.is_valid(headers.get("cookie", ""))
```

### Every incoming message is validated at the edge, and the frame size is bounded

**Why:** a frame decoded into a dict and passed inward is an unvalidated payload in the domain.
Each frame becomes a member of a strict discriminated union; a frame that fails closes the socket
with 1003. The server bounds the frame size to what the protocol needs, and a client that sends
too often is rate-limited per connection like any other input.

**Example:**
```python
# WRONG — whatever JSON arrives is handed to the floor as a dict
async def read_bidder_messages(
    *, receive: Callable[[], Awaitable[str]], floor: AuctionFloor
) -> None:
    while True:
        await floor.apply(json.loads(await receive()))


# CORRECT — each frame becomes a typed message or a validation error, here
async def read_bidder_messages(
    *, receive: Callable[[], Awaitable[str]], floor: AuctionFloor
) -> None:
    while True:
        message = parse_bidder_message(await receive())
        await floor.apply(message.to_domain())

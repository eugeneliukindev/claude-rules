# Streaming RPCs

The rules for long-lived responses are `python-streaming`'s; what gRPC adds is below.

### A server-streaming handler releases what it holds in `finally` or `async with`

**Why:** a handler suspended at `yield` is closed, not cancelled, when the client cancels or the
deadline passes: measured, its `except CancelledError` never ran and its `finally` did. Code after
the loop runs only when the stream ends on its own.

**Example:**
```python
# WRONG — on cancel the generator is closed at yield, and stop_following never runs
@final
class FlightServicer(flights_pb2_grpc.FlightServiceServicer):
    def __init__(self, flights: FlightService) -> None:
        self._flights = flights

    @override
    async def GetFlight(
        self, request: flights_pb2.GetFlightRequest, context: _GetFlightContext
    ) -> flights_pb2.GetFlightResponse:
        flight = await self._flights.get_flight(flight_id_from_wire(request.flight_id))
        return flights_pb2.GetFlightResponse(flight=flight_to_wire(flight))

    @override
    async def WatchFlight(
        self, request: flights_pb2.WatchFlightRequest, context: _WatchFlightContext
    ) -> AsyncIterator[flights_pb2.WatchFlightResponse]:
        updates = self._flights.start_following(flight_id_from_wire(request.flight_id))
        async for flight in updates:
            yield flights_pb2.WatchFlightResponse(flight=flight_to_wire(flight))
        self._flights.stop_following(updates)


# CORRECT — the context manager removes the subscription however the stream ends
@final
class FlightServicer(flights_pb2_grpc.FlightServiceServicer):
    def __init__(self, flights: FlightService) -> None:
        self._flights = flights

    @override
    async def GetFlight(
        self, request: flights_pb2.GetFlightRequest, context: _GetFlightContext
    ) -> flights_pb2.GetFlightResponse:
        flight = await self._flights.get_flight(flight_id_from_wire(request.flight_id))
        return flights_pb2.GetFlightResponse(flight=flight_to_wire(flight))

    @override
    async def WatchFlight(
        self, request: flights_pb2.WatchFlightRequest, context: _WatchFlightContext
    ) -> AsyncIterator[flights_pb2.WatchFlightResponse]:
        async with self._flights.follow_flight(flight_id_from_wire(request.flight_id)) as updates:
            async for flight in updates:
                yield flights_pb2.WatchFlightResponse(flight=flight_to_wire(flight))
```

### Flow control bounds one stream, not a fan-out: each subscriber gets a bounded queue

**Why:** a slow reader stalls `yield` once the HTTP/2 windows fill — measured, the server stopped
after 62 messages of 100 KB while the client slept. A publisher that awaits each subscriber's queue
in turn is held by the slowest; it gives each a bounded queue and never awaits one.

**Example:**
```python
# WRONG — one slow watcher's full queue holds the update back from every other watcher
@final
class FlightUpdateFanout:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[Flight]] = set()

    async def publish(self, flight: Flight) -> None:
        for queue in self._queues:
            await queue.put(flight)


# CORRECT — a full queue drops its watcher, which reopens the stream; the others are not held
@final
class FlightUpdateFanout:
    def __init__(self) -> None:
        self._queues: set[asyncio.Queue[Flight]] = set()

    def publish(self, flight: Flight) -> None:
        for queue in tuple(self._queues):
            try:
                queue.put_nowait(flight)
            except asyncio.QueueFull:
                self._queues.discard(queue)
                queue.shutdown(immediate=True)
```

### A stream's `timeout=` covers its whole life, so a watch has a maximum lifetime and reopens

**Why:** the deadline counts from the call's start, not from the last message, and a stream with no
deadline outlives every server restart unnoticed. A watch that should last gets a maximum lifetime,
and the client reopens it when it passes; the server sends the current state first, so a reopened
watch misses nothing.

**Example:**
```python
# WRONG — no deadline: a stream that stalls is never noticed
async def watch_flight(stub: FlightServiceAsyncStub, flight_id: FlightId) -> AsyncIterator[Flight]:
    request = flights_pb2.WatchFlightRequest(flight_id=str(flight_id))
    async for response in stub.WatchFlight(request):
        yield flight_from_wire(response.flight)


# CORRECT — a bounded lifetime, and a new stream each time it passes
async def watch_flight(stub: FlightServiceAsyncStub, flight_id: FlightId) -> AsyncIterator[Flight]:
    request = flights_pb2.WatchFlightRequest(flight_id=str(flight_id))
    while True:
        try:
            async for response in stub.WatchFlight(request, timeout=_WATCH_LIFETIME_SECONDS):
                yield flight_from_wire(response.flight)
        except grpc.aio.AioRpcError as error:
            if error.code() != grpc.StatusCode.DEADLINE_EXCEEDED:
                raise _translate_status(error, flight_id) from error
        else:
            return
```

### A client that leaves a stream early cancels the call

**Why:** measured, a client that broke out of `async for` and dropped the call kept the server's
stream running until its deadline, holding a subscription and a slot under
`maximum_concurrent_rpcs` the whole time.

**Example:**
```python
# WRONG — returning mid-stream leaves the call open on the server until its deadline
async def wait_for_gate(stub: FlightServiceAsyncStub, flight_id: FlightId) -> str:
    call = stub.WatchFlight(
        flights_pb2.WatchFlightRequest(flight_id=str(flight_id)), timeout=_WAIT_SECONDS
    )
    async for response in call:
        if response.flight.HasField("gate"):
            return response.flight.gate
    raise GateNotAssignedError(flight_id)


# CORRECT — the call is cancelled however the loop is left
async def wait_for_gate(stub: FlightServiceAsyncStub, flight_id: FlightId) -> str:
    call = stub.WatchFlight(
        flights_pb2.WatchFlightRequest(flight_id=str(flight_id)), timeout=_WAIT_SECONDS
    )
    try:
        async for response in call:
            if response.flight.HasField("gate"):
                return response.flight.gate
    finally:
        call.cancel()
    raise GateNotAssignedError(flight_id)
```

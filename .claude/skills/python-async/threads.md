# Threads and the Loop

The seam between a loop and a thread; the pools themselves are `python-sync`, and the correlation
id the context carries is `python-observability`.

### Work submitted to an executor carries the caller's context explicitly

**Why:** `asyncio.to_thread` copies the caller's `contextvars` into the thread; `run_in_executor`
does not, and every log line the thread writes loses its correlation id.

**Example:**
```python
# WRONG — the thread sees the variable's default: the stitching's log lines carry no capture id
async def build_mosaic(tile_ids: Sequence[TileId], *, executor: Executor) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, stitch_tiles, tile_ids)


# CORRECT — the caller's context travels with the call
async def build_mosaic(tile_ids: Sequence[TileId], *, executor: Executor) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor, functools.partial(contextvars.copy_context().run, stitch_tiles, tile_ids)
    )
```

### A thread reaches the loop only through `run_coroutine_threadsafe` or `call_soon_threadsafe`

**Why:** every other loop, `Future` and `asyncio.Queue` method is unsafe from another thread, and
only debug mode reports it — `Non-thread-safe operation invoked`. Without debug mode the call
corrupts the loop's state quietly or never wakes it.

**Example:**
```python
# WRONG — a receiver thread puts straight into an asyncio.Queue the loop is reading
def on_telemetry_frame(
    frame: TelemetryFrame, *, frames: asyncio.Queue[TelemetryFrame]
) -> None:
    frames.put_nowait(frame)


# CORRECT — the put is scheduled on the loop that owns the queue
def on_telemetry_frame(
    frame: TelemetryFrame,
    *,
    frames: asyncio.Queue[TelemetryFrame],
    loop: asyncio.AbstractEventLoop,
) -> None:
    loop.call_soon_threadsafe(frames.put_nowait, frame)
```

### `asyncio.Lock` only orders tasks; state a thread also touches takes a `threading.Lock`

**Why:** `asyncio.Lock` is not thread-safe — measured, a coroutine waiting on it from a loop in
another thread hung forever in one run and acquired it in the next. A `threading.Lock` is never held
across an `await`: it blocks every other task that needs it, and a thread waiting on it from the
loop's own thread stalls the loop.

**Example:**
```python
# WRONG — an asyncio.Lock guards a dict the executor's threads also write
@final
class StitchedMosaics:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._mosaic_by_id: dict[MosaicId, bytes] = {}

    async def remember(self, mosaic_id: MosaicId, mosaic: bytes) -> None:
        async with self._lock:
            self._mosaic_by_id[mosaic_id] = mosaic


# CORRECT — a threading.Lock, held only for the lines that touch the dict
@final
class StitchedMosaics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._mosaic_by_id: dict[MosaicId, bytes] = {}

    def remember(self, mosaic_id: MosaicId, mosaic: bytes) -> None:
        with self._lock:
            self._mosaic_by_id[mosaic_id] = mosaic
```

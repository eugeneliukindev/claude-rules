# Threads

The pools, locks between threads and process pools themselves are `python-sync`; this file is the
seam between them and the loop.

### Work submitted to an executor carries the caller's context explicitly

**Why:** `asyncio.to_thread` copies the caller's `contextvars` into the thread; `run_in_executor`
does not, and every log line the thread writes loses its correlation id (`python-observability`).

**Example:**
```python
# WRONG — the thread sees the variable's default: the report's log lines carry no request id
async def render_in_pool(report_ids: Sequence[ReportId], *, executor: Executor) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(executor, render_report, report_ids)


# CORRECT — the caller's context travels with the call
async def render_in_pool(report_ids: Sequence[ReportId], *, executor: Executor) -> bytes:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        executor, functools.partial(contextvars.copy_context().run, render_report, report_ids)
    )
```

### A thread reaches the loop only through `run_coroutine_threadsafe` or `call_soon_threadsafe`

**Why:** every other loop, `Future` and `asyncio.Queue` method is unsafe from another thread, and
only debug mode reports it — `Non-thread-safe operation invoked`. Without debug mode the call
corrupts the loop's state quietly or never wakes it.

**Example:**
```python
# WRONG — a callback thread puts straight into an asyncio.Queue the loop is reading
def on_sensor_reading(reading: Reading, *, readings: asyncio.Queue[Reading]) -> None:
    readings.put_nowait(reading)


# CORRECT — the put is scheduled on the loop that owns the queue
def on_sensor_reading(
    reading: Reading, *, readings: asyncio.Queue[Reading], loop: asyncio.AbstractEventLoop
) -> None:
    loop.call_soon_threadsafe(readings.put_nowait, reading)
```

### `asyncio.Lock` only orders tasks; state a thread also touches takes a `threading.Lock`

**Why:** `asyncio.Lock` is not thread-safe — measured, a coroutine waiting on it from a loop in
another thread hung forever in one run and acquired it in the next. A `threading.Lock` is never held
across an `await`:
it blocks every other task that needs it, and a thread waiting on it from the loop's own thread
stalls the loop.

**Example:**
```python
# WRONG — an asyncio.Lock guards a dict the executor's threads also write
@final
class RenderedReports:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._report_by_id: dict[ReportId, bytes] = {}

    async def remember(self, report_id: ReportId, report: bytes) -> None:
        async with self._lock:
            self._report_by_id[report_id] = report


# CORRECT — a threading.Lock, held only for the lines that touch the dict
@final
class RenderedReports:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._report_by_id: dict[ReportId, bytes] = {}

    def remember(self, report_id: ReportId, report: bytes) -> None:
        with self._lock:
            self._report_by_id[report_id] = report
```

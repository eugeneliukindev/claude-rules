# Threads

## Contents

- `run_in_executor` does not carry `contextvars`; `to_thread` does
- A thread reaches the loop only through the thread-safe calls
- State a thread also touches is guarded by `threading.Lock`
- A lock is held for the data, never for the I/O
- `threading.local` only for per-thread resources; thread-safety is documented

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

### State a thread also touches is guarded by `threading.Lock`; `asyncio.Lock` only orders tasks

**Why:** `asyncio.Lock` is not thread-safe — measured, a coroutine waiting on it from a loop in
another thread hung forever in one run and acquired it in the next. The GIL is not a lock either: a
check-then-set on a shared dict races between threads today, and on a free-threaded `3.13t` or
`3.14t` build every compound operation does. A `threading.Lock` is never held across an `await`:
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

### A lock covers the data, never the slow call that fills it

**Why:** a lock held across I/O makes every thread that wants any entry wait behind the slowest
fetch. The fetch runs outside; the lock covers the read and the write, and `setdefault` keeps the
first value if two threads fetched at once. No shared state at all is better still.

**Example:**
```python
# WRONG — every thread asking for any price waits behind one slow catalog call
@final
class PriceCache:
    def __init__(self, *, catalog: PriceCatalog) -> None:
        self._catalog = catalog
        self._lock = threading.Lock()
        self._price_by_sku: dict[Sku, Decimal] = {}

    def price(self, sku: Sku) -> Decimal:
        with self._lock:
            if sku not in self._price_by_sku:
                self._price_by_sku[sku] = self._catalog.fetch_price(sku)
            return self._price_by_sku[sku]


# CORRECT — the lock covers the dictionary only; the fetch runs outside it
@final
class PriceCache:
    def __init__(self, *, catalog: PriceCatalog) -> None:
        self._catalog = catalog
        self._lock = threading.Lock()
        self._price_by_sku: dict[Sku, Decimal] = {}

    def price(self, sku: Sku) -> Decimal:
        with self._lock:
            cached = self._price_by_sku.get(sku)
        if cached is not None:
            return cached
        fetched = self._catalog.fetch_price(sku)
        with self._lock:
            return self._price_by_sku.setdefault(sku, fetched)
```

### `threading.local` is for per-thread resources only, and thread-safety is documented

**Why:** in async code many tasks share one thread, so a thread-local leaks between them —
`contextvars` is the per-task store. A thread-local fits a resource that must not cross threads, a
connection a non-thread-safe driver hands out. Whether a class may be shared between threads is a
property its docstring states, never an assumption its callers make.

**Example:**
```python
# WRONG — a thread-local for the request id: every task on the loop thread shares it
_request_state = threading.local()


async def handle(request: Request, *, handler: Handler) -> Response:
    _request_state.request_id = request.headers.get("x-request-id", "")
    return await handler(request)


# CORRECT — one connection per worker thread, for a driver whose connections must not be shared
@final
class ThreadConnections:
    """Thread-safe: each thread gets and reuses its own connection."""

    def __init__(self, *, connect: Callable[[], Connection]) -> None:
        self._connect = connect
        self._local = threading.local()

    def connection(self) -> Connection:
        existing: Connection | None = getattr(self._local, "connection", None)
        if existing is None:
            existing = self._connect()
            self._local.connection = existing
        return existing
```

---
name: python-async
description: >-
  Python asyncio and concurrency: asyncio.run once in the entry point, one async library per
  codebase, never blocking the event loop, offloading sync and CPU-bound work to shared executors,
  a deadline on every await, structured concurrency with TaskGroup, cancellation and shielding,
  bounded fan-out, contextvars, graceful shutdown, and choosing between async, threads and
  processes. Use when writing async def, awaiting external I/O, using create_task, a semaphore or
  anyio, or moving Python work to threads or a process pool.
---

# Asyncio and Concurrency

## Asyncio

- **`asyncio.run(main())` once, in the entry point**, and nowhere else. No
  `asyncio.get_event_loop()` — since 3.14 it raises when no loop is running, and where one is,
  `asyncio.get_running_loop()` says so honestly — no `loop.run_until_complete`, and no
  `asyncio.run` inside library code, which fails the moment its caller is already async.

```python
# WRONG — raises on 3.14 when no loop is running, and never closes the loop or its tasks
loop = asyncio.get_event_loop()
loop.run_until_complete(main())

# CORRECT — creates the loop, runs main, cancels what is left and closes the loop
asyncio.run(main())
```

- **One async library per codebase**: `asyncio`, or `anyio` when a dependency is built on it or the
  code must also run under trio. Mixing them mixes two cancellation models — anyio's cancel scopes
  are level-triggered, asyncio's cancellation is delivered once — and a timeout written in one does
  not hold in the other's task group.
- **Never block the event loop**: no sync drivers, no `time.sleep`, no heavy CPU work inside
  `async def`.
- **Blocking calls are offloaded, not tolerated**: `await asyncio.to_thread(...)` for I/O-bound
  sync code. CPU-bound work goes to a **shared** process pool created once in the composition root
  and passed in — never an executor constructed per call, which pays pool startup every time and
  breaks concurrency limits.

```python
# WRONG — the whole event loop stops while the file is read
async def load_report(path: Path) -> bytes:
    return path.read_bytes()

# CORRECT — the read runs on a worker thread and the loop keeps serving
async def load_report(path: Path) -> bytes:
    return await asyncio.to_thread(path.read_bytes)

# WRONG — a pool per call: worker processes are started and torn down for every report
async def render_report(report_id: ReportId) -> bytes:
    with ProcessPoolExecutor() as pool:
        return await asyncio.get_running_loop().run_in_executor(pool, _render, report_id)

# CORRECT — one pool, sized and built by the composition root, passed in
async def render_report(pool: Executor, report_id: ReportId) -> bytes:
    return await asyncio.get_running_loop().run_in_executor(pool, _render, report_id)
```

- **Every `await` on external I/O runs under a deadline** — the client's configured timeout or an
  explicit `asyncio.timeout(...)` scope. An unbounded `await` is the async equivalent of an
  infinite loop.

```python
# WRONG — a peer that stops sending leaves this await, and its task, waiting forever
async def read_frame(reader: asyncio.StreamReader) -> bytes:
    return await reader.readuntil(_FRAME_SEPARATOR)

# CORRECT — at the deadline the scope cancels the read and raises TimeoutError
async def read_frame(reader: asyncio.StreamReader) -> bytes:
    async with asyncio.timeout(_FRAME_TIMEOUT_SECONDS):
        return await reader.readuntil(_FRAME_SEPARATOR)
```

- **`asyncio.timeout` around `to_thread` stops the waiting, not the thread.** A thread cannot be
  cancelled: the call runs to completion and keeps its executor slot, so a handful of hung calls
  exhausts the pool. The deadline for blocking work lives in the blocking client's own timeout.

```python
# WRONG — the caller gets TimeoutError, and the hung call keeps its worker thread regardless
async def fetch_invoice(client: BillingClient, invoice_id: InvoiceId) -> Invoice:
    async with asyncio.timeout(_FETCH_TIMEOUT_SECONDS):
        return await asyncio.to_thread(client.fetch_invoice, invoice_id)

# CORRECT — the blocking client enforces the deadline, so the thread itself gives up
async def fetch_invoice(client: BillingClient, invoice_id: InvoiceId) -> Invoice:
    return await asyncio.to_thread(
        client.fetch_invoice, invoice_id, timeout_seconds=_FETCH_TIMEOUT_SECONDS
    )
```

- **Structured concurrency by default**: `asyncio.TaskGroup` — tasks cannot leak, the first failure
  cancels siblings and raises an `ExceptionGroup`. **Fire-and-forget `create_task` without keeping
  a reference is forbidden**: the task can be garbage-collected mid-flight and its exception
  silently lost.

```python
# WRONG — nothing holds either task, and the caller never learns that one failed
async def complete_order(order: Order, mailer: Mailer, audit: AuditLog) -> None:
    asyncio.create_task(mailer.send_receipt(order))
    asyncio.create_task(audit.record(order))

# CORRECT — the group holds both, waits for both, and raises their failures together
async def complete_order(order: Order, mailer: Mailer, audit: AuditLog) -> None:
    async with asyncio.TaskGroup() as group:
        group.create_task(mailer.send_receipt(order))
        group.create_task(audit.record(order))
```

- **Cancellation is not an error to swallow.** On cancellation, clean up in `finally` and re-raise.
  Shielding is reserved for genuinely-must-finish commits, always combined with a timeout.

```python
# WRONG — swallowed: an enclosing timeout or TaskGroup sees a normal return and carries on
async def wait_until_finished(client: StatusClient, job_id: JobId) -> None:
    try:
        while not await client.is_finished(job_id):
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("polling stopped", extra={"job_id": job_id})

# CORRECT — the stop is recorded, and the cancellation travels on to whoever asked for it
async def wait_until_finished(client: StatusClient, job_id: JobId) -> None:
    try:
        while not await client.is_finished(job_id):
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("polling stopped", extra={"job_id": job_id})
        raise
```

- **Concurrency is bounded**: fan-outs go through a `Semaphore` with a named constant limit; queues
  between producers and consumers are bounded — an unbounded queue is a memory leak with extra
  steps.

```python
# WRONG — ten thousand SKUs open ten thousand requests at once
async def fetch_prices(catalog: CatalogClient, skus: Sequence[Sku]) -> list[Price]:
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(catalog.fetch_price(sku)) for sku in skus]
    return [task.result() for task in tasks]

# CORRECT — at most _MAX_CONCURRENT_FETCHES requests are in flight at any moment
async def fetch_prices(catalog: CatalogClient, skus: Sequence[Sku]) -> list[Price]:
    request_slots = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

    async def fetch_one(sku: Sku) -> Price:
        async with request_slots:
            return await catalog.fetch_price(sku)

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(fetch_one(sku)) for sku in skus]
    return [task.result() for task in tasks]
```

- **Request-scoped context travels via `contextvars`** — never module globals, never thread-locals
  in async code. Do not smuggle business parameters through it.
- **Graceful shutdown is designed, not hoped for**: handle `SIGTERM`/`SIGINT`, stop accepting work,
  drain or cancel with a deadline, then close resources in reverse order. Consumers acknowledge
  only after processing.

```python
# WRONG — SIGTERM's default action ends the process at once: no finally runs, nothing is closed
async def main() -> None:
    async with build_application() as application:
        await application.serve_forever()

# CORRECT — a signal sets the event; the application stops taking work, drains and closes
async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signal_number, stop.set)
    async with build_application() as application:
        await application.serve_until(stop)
```

- **Async generators are closed deterministically** — consume with `aclosing(...)` when the loop
  may break early, or cleanup runs at GC time on a dead loop.

```python
# WRONG — returning mid-loop leaves the generator open; its finally waits for the collector
async def find_first_disputed(invoices: InvoiceRepository) -> Invoice | None:
    async for invoice in invoices.stream_unpaid():
        if invoice.is_disputed:
            return invoice
    return None

# CORRECT — aclosing closes the generator on the way out, so its cursor is released here
async def find_first_disputed(invoices: InvoiceRepository) -> Invoice | None:
    async with aclosing(invoices.stream_unpaid()) as unpaid:
        async for invoice in unpaid:
            if invoice.is_disputed:
                return invoice
    return None
```

- **Locks protect state, not I/O.** Never hold a lock across an external `await` you do not control.
- **Sync and async versions of an API are separate, explicit functions** — no boolean, no
  auto-detection. Write the async core and delegate the sync wrapper at the edge, never the
  reverse.
- **`ExceptionGroup` / `except*` for concurrent failures** from a `TaskGroup`; do not flatten to
  the first exception.

```python
# WRONG — a TaskGroup raises ExceptionGroup, so this clause never matches and the failure escapes
async def refresh_rates(feeds: Sequence[RateFeed], cache: RateCache) -> None:
    try:
        async with asyncio.TaskGroup() as group:
            for feed in feeds:
                group.create_task(cache.refresh(feed))
    except FeedUnavailableError:
        logger.warning("rate refresh incomplete")

# CORRECT — except* matches inside the group, however many feeds failed
async def refresh_rates(feeds: Sequence[RateFeed], cache: RateCache) -> None:
    try:
        async with asyncio.TaskGroup() as group:
            for feed in feeds:
                group.create_task(cache.refresh(feed))
    except* FeedUnavailableError as failures:
        logger.warning("rate refresh incomplete", extra={"failed_feeds": len(failures.exceptions)})
```

## Threads, Processes, and the GIL

Pick the model by the workload, and measure before assuming parallelism helps — pool and pickling
overhead is real:

| Workload | Model |
|---|---|
| Many concurrent network / DB waits | async |
| A blocking library with no async API | threads |
| CPU-bound Python | processes |
| CPU-bound inside a C extension that releases the GIL | threads |

- **Executors are shared and injected**, sized by a named constant, and closed on shutdown.
- **Process pools receive picklable, small arguments** and return small results; pass ids and
  paths, not loaded objects. A function submitted to a process pool is a module-level function.
- **Shared mutable state between threads is protected by a lock**, held for the shortest time,
  never across I/O. Prefer no shared state at all.

```python
# WRONG — every thread asking for any price waits behind one slow catalog call
def fetch_price(self, sku: Sku) -> Decimal:
    with self._lock:
        if sku not in self._price_by_sku:
            self._price_by_sku[sku] = self._catalog.fetch_price(sku)
        return self._price_by_sku[sku]

# CORRECT — the lock covers the dictionary only; the fetch runs outside it
def fetch_price(self, sku: Sku) -> Decimal:
    with self._lock:
        cached = self._price_by_sku.get(sku)
    if cached is not None:
        return cached
    fetched = self._catalog.fetch_price(sku)
    with self._lock:
        return self._price_by_sku.setdefault(sku, fetched)
```

- **Thread-safety is a documented property of a class**, not an assumption.
- **`threading.local` only for genuinely per-thread resources**; in async code it is wrong — use
  `contextvars`.
- **Daemon threads are forbidden** for anything that does work; every thread is joined on shutdown
  with a timeout.

```python
# WRONG — a daemon thread is killed wherever it stands when the interpreter exits
writer = threading.Thread(target=flush_audit_log, args=(entries,), daemon=True)
writer.start()

# CORRECT — the thread watches a stop event, and shutdown waits for it with a deadline
stop = threading.Event()
writer = threading.Thread(target=flush_audit_log, args=(entries, stop))
writer.start()
...
stop.set()
writer.join(timeout=_SHUTDOWN_TIMEOUT_SECONDS)
```

- **The `multiprocessing` start method is `spawn` or `forkserver`, set explicitly** — never `fork`:
  forking a process that already has threads or an event loop is undefined behaviour in practice.
  Since 3.14 the Linux default is `forkserver` rather than `fork`, so code that silently relied on
  inherited globals breaks on upgrade; naming the method makes that dependence visible.

```python
# WRONG — the platform and the Python version pick the start method
with ProcessPoolExecutor(max_workers=_RENDER_WORKERS) as pool:
    ...

# CORRECT — named once, so the workers start the same way on every platform and version
with ProcessPoolExecutor(
    max_workers=_RENDER_WORKERS, mp_context=multiprocessing.get_context("spawn")
) as pool:
    ...
```
- **Signals are handled in the main thread only**; workers get a stop event, not a signal.

Testing coroutines — the plugin, its mode and loop scope — is in `python-pytest`.

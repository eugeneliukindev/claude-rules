---
name: python-async
description: >-
  Writes asyncio code that never blocks the loop, bounds every await and fan-out, and cleans up on
  cancellation. Use when writing async def, awaiting I/O, using create_task, gather, a semaphore,
  a queue or anyio, or handing work from a coroutine to a thread or a process pool. Not for
  threads or pools without a loop (python-sync).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Asyncio and Concurrency

Testing coroutines — the plugin, its mode and loop scope — is in `python-pytest`.

## Deadlines

### Every `await` on external I/O runs under a deadline

**Why:** an unbounded `await` is the async equivalent of an infinite loop: a peer that stops sending
holds the task forever. The deadline is the client's configured timeout or an `asyncio.timeout`
scope — one scope bounds every await in its block, where two `wait_for` calls in sequence each get
the whole budget. In an async generator the scope wraps the `await` and closes before the `yield`
(`python-streaming`).

### A deadline on blocking work lives in the blocking client, not around `to_thread`

**Why:** a thread cannot be cancelled. `asyncio.timeout` around `to_thread` stops the waiting; the
call runs to completion and keeps its executor slot, so a handful of hung calls exhausts the pool.

**Example:**
```python
# WRONG — the caller gets TimeoutError, and the hung call keeps its worker thread regardless
async def fetch_statement(statement_id: StatementId, *, bank: BankClient) -> Statement:
    async with asyncio.timeout(_FETCH_TIMEOUT_SECONDS):
        return await asyncio.to_thread(bank.fetch_statement, statement_id)


# CORRECT — the blocking client enforces the deadline, so the thread itself gives up
async def fetch_statement(statement_id: StatementId, *, bank: BankClient) -> Statement:
    return await asyncio.to_thread(
        bank.fetch_statement, statement_id, timeout_seconds=_FETCH_TIMEOUT_SECONDS
    )
```

## Tasks

### Concurrent tasks run in a `TaskGroup`; a bare `create_task` is never fired and forgotten

**Why:** a task nobody holds can be garbage-collected mid-flight and its exception silently lost.
The group holds every task, waits for all, cancels the siblings at the first failure and raises
the failures together. `asyncio.gather` with its default raises the first failure and leaves the
siblings running with nobody awaiting them — measured, the sibling ran to the end and printed;
`return_exceptions=True` is right only where a partial result is the contract, with every element
checked before use.

**Example:**
```python
# WRONG — nothing holds either task, and the caller never learns that one failed
async def complete_signup(account: Account, *, mailer: Mailer, audit: AuditLog) -> None:
    asyncio.create_task(mailer.send_welcome(account))
    asyncio.create_task(audit.record_signup(account))


# CORRECT — the group holds both, waits for both, and raises their failures together
async def complete_signup(account: Account, *, mailer: Mailer, audit: AuditLog) -> None:
    async with asyncio.TaskGroup() as group:
        group.create_task(mailer.send_welcome(account))
        group.create_task(audit.record_signup(account))
```

### A `TaskGroup`'s failures are caught with `except*`

**Why:** the group raises an `ExceptionGroup`, so a plain `except` clause never matches and the
failure escapes; flattening to the first exception loses the rest. Cancelling the task that owns
the group raises `CancelledError`, not an `ExceptionGroup`, and an `except*` for the children's
failures does not see it.

**Example:**
```python
# WRONG — a TaskGroup raises ExceptionGroup, so this clause never matches and the failure escapes
async def refresh_rates(feeds: Sequence[RateFeed], *, cache: RateCache) -> None:
    try:
        async with asyncio.TaskGroup() as group:
            for feed in feeds:
                group.create_task(cache.refresh(feed))
    except FeedUnavailableError:
        logger.warning("rate refresh incomplete")


# CORRECT — except* matches inside the group, however many feeds failed
async def refresh_rates(feeds: Sequence[RateFeed], *, cache: RateCache) -> None:
    try:
        async with asyncio.TaskGroup() as group:
            for feed in feeds:
                group.create_task(cache.refresh(feed))
    except* FeedUnavailableError as failures:
        logger.warning("rate refresh incomplete", extra={"failed_feeds": len(failures.exceptions)})
```

### A fan-out is bounded by a semaphore, and a queue between tasks has a size

**Why:** ten thousand items open ten thousand requests at once, and an unbounded queue is a memory
leak with extra steps. The limit is a named constant; a producer–consumer pair ends with
`asyncio.Queue.shutdown()` (3.13) — `put` raises `QueueShutDown` at once, `get` once the queue is
drained — or a sentinel on a 3.12 floor.

**Example:**
```python
# WRONG — ten thousand SKUs open ten thousand requests at once
async def fetch_prices(skus: Sequence[Sku], *, catalog: CatalogClient) -> list[Price]:
    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(catalog.fetch_price(sku)) for sku in skus]
    return [task.result() for task in tasks]


# CORRECT — at most _MAX_CONCURRENT_FETCHES requests are in flight at any moment
async def fetch_prices(skus: Sequence[Sku], *, catalog: CatalogClient) -> list[Price]:
    request_slots = asyncio.Semaphore(_MAX_CONCURRENT_FETCHES)

    async def fetch_one(sku: Sku) -> Price:
        async with request_slots:
            return await catalog.fetch_price(sku)

    async with asyncio.TaskGroup() as group:
        tasks = [group.create_task(fetch_one(sku)) for sku in skus]
    return [task.result() for task in tasks]
```

## Cancellation

### Cancellation is cleaned up after and re-raised, never swallowed

**Why:** swallowed, an enclosing timeout or `TaskGroup` sees a normal return and carries on.
`CancelledError` is a `BaseException`, so `except Exception` lets it through by design, and
`except BaseException` "for resilience" swallows it. Shielding is reserved for a commit that must
finish, always under a timeout of its own.

**Example:**
```python
# WRONG — swallowed: whoever cancelled this task believes it finished normally
async def wait_until_finished(job_id: JobId, *, client: StatusClient) -> None:
    try:
        while not await client.is_finished(job_id):
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("polling stopped", extra={"job_id": job_id})


# CORRECT — the stop is recorded, and the cancellation travels on to whoever asked for it
async def wait_until_finished(job_id: JobId, *, client: StatusClient) -> None:
    try:
        while not await client.is_finished(job_id):
            await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("polling stopped", extra={"job_id": job_id})
        raise
```

### An async generator left early is closed with `aclosing`

**Why:** left open, a generator is closed when it is collected, or at `asyncio.run`'s shutdown if
something still holds it — a moment nothing controls, and its file or cursor stays open until then.
`aclosing` needs `aclose()`, so a method whose result callers close returns `AsyncGenerator`, not
`AsyncIterator` — mypy rejects the latter.

**Example:**
```python
# WRONG — returning mid-loop leaves the generator open; its finally waits for the collector
async def find_first_disputed(*, invoices: InvoiceRepository) -> Invoice | None:
    async for invoice in invoices.stream_unpaid():
        if invoice.is_disputed:
            return invoice
    return None


# CORRECT — aclosing closes the generator on the way out, so its cursor is released here
async def find_first_disputed(*, invoices: InvoiceRepository) -> Invoice | None:
    async with aclosing(invoices.stream_unpaid()) as unpaid:
        async for invoice in unpaid:
            if invoice.is_disputed:
                return invoice
    return None
```

## Context and Locks

### Request-scoped context travels in `contextvars`, and a lock guards state, never I/O

**Why:** a module global or a thread-local is shared by every task on the loop, so one request's
id lands in another's log lines; a context variable is per task. It carries cross-cutting context —
a correlation id, a tenant — never business parameters smuggled past the signature. A lock held
across an external `await` you do not control makes every task that needs it wait for the network.

**Example:**
```python
# WRONG — one global for the whole loop: concurrent requests overwrite each other's id
_current_request_id = ""


async def handle(request: Request, *, handler: Handler) -> Response:
    global _current_request_id  # noqa: PLW0603  # the bug this example shows
    _current_request_id = request.headers.get("x-request-id", "")
    return await handler(request)


# CORRECT — each task sees the value set in its own context
_REQUEST_ID: Final = contextvars.ContextVar[str]("request_id", default="")


async def handle(request: Request, *, handler: Handler) -> Response:
    _REQUEST_ID.set(request.headers.get("x-request-id", ""))
    return await handler(request)
```

## Threads and the Loop

**Before handing work from a coroutine to a thread or a process pool, sharing state between threads
and tasks, or calling into the loop from a thread, read [threads.md](threads.md)** — `contextvars`
through `run_in_executor`, `run_coroutine_threadsafe`, `asyncio.Lock` against `threading.Lock`.
Which workload needs threads or processes, the pools themselves and locks between threads are
`python-sync`.

## Shutdown

**Before handling `SIGTERM` or `SIGINT` or writing the stop path of a service, read
[shutdown.md](shutdown.md)** — a signal that sets an event, drain with a deadline, signals in the
main thread only; a thread's stop event is `python-sync`.

---
name: python-async
description: >-
  Python asyncio and concurrency: never blocking the event loop, offloading sync and CPU-bound
  work to shared executors, a deadline on every await, structured concurrency with TaskGroup,
  cancellation and shielding, bounded fan-out, contextvars, graceful shutdown, and choosing
  between async, threads and processes. Use when writing async def, awaiting external I/O, using
  create_task or a semaphore, or moving Python work to threads or a process pool.
---

# Asyncio and Concurrency

## Asyncio

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
```

- **Every `await` on external I/O runs under a deadline** — the client's configured timeout or an
  explicit `asyncio.timeout(...)` scope. An unbounded `await` is the async equivalent of an
  infinite loop.
- **`asyncio.timeout` around `to_thread` stops the waiting, not the thread.** A thread cannot be
  cancelled: the call runs to completion and keeps its executor slot, so a handful of hung calls
  exhausts the pool. The deadline for blocking work lives in the blocking client's own timeout.
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
- **Concurrency is bounded**: fan-outs go through a `Semaphore` with a named constant limit; queues
  between producers and consumers are bounded — an unbounded queue is a memory leak with extra
  steps.
- **Request-scoped context travels via `contextvars`** — never module globals, never thread-locals
  in async code. Do not smuggle business parameters through it.
- **Graceful shutdown is designed, not hoped for**: handle `SIGTERM`/`SIGINT`, stop accepting work,
  drain or cancel with a deadline, then close resources in reverse order. Consumers acknowledge
  only after processing.
- **Async generators are closed deterministically** — consume with `aclosing(...)` when the loop
  may break early, or cleanup runs at GC time on a dead loop.
- **Locks protect state, not I/O.** Never hold a lock across an external `await` you do not control.
- **Sync and async versions of an API are separate, explicit functions** — no boolean, no
  auto-detection. Write the async core and delegate the sync wrapper at the edge, never the
  reverse.
- **`ExceptionGroup` / `except*` for concurrent failures** from a `TaskGroup`; do not flatten to
  the first exception.

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
- **Thread-safety is a documented property of a class**, not an assumption.
- **`threading.local` only for genuinely per-thread resources**; in async code it is wrong — use
  `contextvars`.
- **Daemon threads are forbidden** for anything that does work; every thread is joined on shutdown
  with a timeout.
- **The `multiprocessing` start method is `spawn` or `forkserver`, set explicitly** — never `fork`:
  forking a process that already has threads or an event loop is undefined behaviour in practice.
  Since 3.14 the Linux default is `forkserver` rather than `fork`, so code that silently relied on
  inherited globals breaks on upgrade; naming the method makes that dependence visible.
- **Signals are handled in the main thread only**; workers get a stop event, not a signal.

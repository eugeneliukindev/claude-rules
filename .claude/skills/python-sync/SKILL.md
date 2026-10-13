---
name: python-sync
description: >-
  Writes threaded and multiprocess Python: threads or processes for the workload, shared executors,
  every future read, bounded queues, threads that stop. Use when code imports threading,
  concurrent.futures, multiprocessing or queue, starts a thread or a pool, or handles a signal
  without an event loop.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Threads and Processes

Checked on Python 3.14. Handing work between an event loop and a thread — `to_thread`,
`run_in_executor`, `call_soon_threadsafe`, `asyncio.Lock` — is `python-async`; who builds and closes
an executor is `python-wiring`; how a container delivers `SIGTERM` is `python-container`.

| Workload | Model |
|---|---|
| Many concurrent network / DB waits | async |
| A blocking library with no async API | threads |
| CPU-bound Python | processes |
| CPU-bound inside a C extension that releases the GIL | threads |
| CPU-bound Python on 3.14, measured against processes | `InterpreterPoolExecutor`, or threads on a free-threaded `3.14t` build — if every C extension supports it |

Parallelism is measured before it is assumed: pool startup and pickling are real costs.

## Executors

### An executor is built once by the composition root, sized by a setting, and passed in

**Why:** a pool per call starts and tears down its workers every time and breaks every concurrency
limit; one pool shared by the process is sized once and closed on shutdown (`python-wiring`).

### Every submitted future is read; its exception is raised only by `result()`

**Why:** measured: a task that raised inside `submit` printed nothing, and the `with` block around
the pool exited normally — the failure lives in the future and nowhere else. `as_completed` reads
the futures as they finish; `map` raises a failure when iteration reaches its item.

**Example:**
```python
# WRONG — the futures are dropped: a photo whose thumbnail failed is never noticed
def render_thumbnails(
    photo_ids: Sequence[PhotoId], *, pool: Executor, renderer: ThumbnailRenderer
) -> None:
    for photo_id in photo_ids:
        pool.submit(renderer.render, photo_id)


# CORRECT — every future is read, and the first failure is raised here
def render_thumbnails(
    photo_ids: Sequence[PhotoId], *, pool: Executor, renderer: ThumbnailRenderer
) -> None:
    futures = [pool.submit(renderer.render, photo_id) for photo_id in photo_ids]
    for future in as_completed(futures):
        future.result()
```

### Work with an outcome runs through an executor; a bare `Thread` reports its exception to nobody

**Why:** measured: an exception in a `Thread`'s target went to `threading.excepthook`, which printed
it to stderr, and `join()` returned normally — the caller went on as if the work was done. A
long-lived thread of its own — a writer, a poller — catches at the top of its loop, logs, and
decides whether to go on (`errors.md`).

## Queues

### Threads hand work over through a bounded `queue.Queue`, ended with `shutdown()`

**Why:** an unbounded queue lets a fast producer pile up a backlog nobody drains in time; `maxsize`
makes `put` wait. From 3.13 `shutdown()` ends the queue — measured: `put` raised `queue.ShutDown`
at once, `get` returned what was left and then raised it, and a consumer blocked in `get` woke with
it — so no sentinel is put once per consumer, and none is forgotten. Before 3.13, one sentinel per
consumer.

**Example:**
```python
# WRONG — a None per consumer, and every producer must know how many consumers there are
def upload_until_none(pending: queue.Queue[Path | None], *, uploader: Uploader) -> None:
    while (path := pending.get()) is not None:
        uploader.upload(path)


# CORRECT — the consumer ends when the producer shuts the queue and the backlog is drained
def upload_until_shut_down(pending: queue.Queue[Path], *, uploader: Uploader) -> None:
    while True:
        try:
            path = pending.get()
        except queue.ShutDown:
            return
        uploader.upload(path)
```

## Shared State

**Before sharing a mutable object between threads, adding a lock or a thread-local, read
[locks.md](locks.md)** — `threading.Lock` because the GIL is not a lock, a lock held for the data
and never for the slow call, `threading.local` for per-thread resources only.

## Processes

**Before creating a process pool, passing work to one or picking a `multiprocessing` start method,
read [processes.md](processes.md)** — small picklable arguments to a module-level function, `spawn`
or `forkserver` by name, the `__main__` guard, and a broken pool.

## Stopping

**Before starting a thread that does work, handling `SIGTERM` or `SIGINT` without an event loop, or
closing a pool, read [shutdown.md](shutdown.md)** — no daemon threads, a stop event waited on
instead of `sleep`, a signal handler that only sets the event, and queued work cancelled on close.

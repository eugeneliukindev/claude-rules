# Stopping Threads and Pools

The drain inside the grace period is `python-workers`; a loop's signal handling is `python-async`.

## Contents

- A thread that does work is never a daemon
- A periodic thread waits on its stop event
- A signal handler only sets an event
- A pool closed on the way out cancels what it has not started

### A thread that does work is never a daemon; it watches a stop event and is joined with a deadline

**Why:** a daemon thread is killed wherever it stands when the interpreter exits — mid-write, with
its buffer unflushed. A thread that checks a stop event finishes its current item, and the join's
timeout bounds how long shutdown waits for it.

**Example:**
```python
# WRONG — a daemon thread is killed wherever it stands when the interpreter exits
def start_audit_writer(entries: queue.Queue[AuditEntry]) -> threading.Thread:
    writer = threading.Thread(target=flush_audit_log, args=(entries,), daemon=True)
    writer.start()
    return writer


# CORRECT — the thread watches a stop event, and shutdown waits for it with a deadline
@final
class AuditWriter:
    def __init__(
        self, *, entries: queue.Queue[AuditEntry], join_timeout_seconds: float = _JOIN_SECONDS
    ) -> None:
        self._stop = threading.Event()
        self._thread = threading.Thread(target=flush_audit_log, args=(entries, self._stop))
        self._join_timeout_seconds = join_timeout_seconds

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=self._join_timeout_seconds)
```

### A periodic thread waits on its stop event, never on `time.sleep`

**Why:** `stop.wait(interval)` returns `True` the moment the event is set; a `sleep` holds the
thread for the rest of the interval, and the join's deadline expires on a thread that was only
sleeping.

**Example:**
```python
# WRONG — a stop that arrives mid-sleep waits out the rest of the interval
def refresh_rates(*, rates: RateRefresher, stop: threading.Event, interval_seconds: float) -> None:
    while not stop.is_set():
        rates.refresh()
        time.sleep(interval_seconds)


# CORRECT — the wait ends the moment the event is set
def refresh_rates(*, rates: RateRefresher, stop: threading.Event, interval_seconds: float) -> None:
    while not stop.is_set():
        rates.refresh()
        stop.wait(interval_seconds)
```

### A signal handler only sets an event; the main thread does the stopping

**Why:** `SIGTERM`'s default action ends the process with no `finally` run. Python runs a handler in
the main thread between two bytecodes of whatever it was doing, so a handler that closes, logs or
writes re-enters code it interrupted — the `signal` documentation's `RuntimeError: reentrant call`
— and only the main thread may install one. The handler sets an event; the code it interrupted
checks the event at a safe point and leaves through its `with` blocks.

**Example:**
```python
# WRONG — the handler closes the importer at whatever line the main thread was on
def main() -> None:
    importer = build_importer()
    signal.signal(signal.SIGTERM, lambda signal_number, frame: importer.close())
    importer.run()


# CORRECT — the importer stops between files, and the with block closes it
def main() -> None:
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda signal_number, frame: stop.set())
    with build_importer() as importer:
        importer.run_until(stop)
```

### A pool closed on the way out cancels what it has not started

**Why:** measured: a `with ThreadPoolExecutor()` block left by `KeyboardInterrupt` with twenty tasks
queued ran all twenty before it exited, and the drain outlived every deadline;
`shutdown(wait=True, cancel_futures=True)` ran only the two already running. Work never started is
picked up by the next run (`python-workers`).

**Example:**
```python
# WRONG — leaving the block waits for every queued task, however the block was left
@contextmanager
def managed_thread_pool(*, max_workers: int = _MAX_WORKERS) -> Iterator[ThreadPoolExecutor]:
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        yield pool


# CORRECT — what has not started is cancelled, and what is running finishes
@contextmanager
def managed_thread_pool(*, max_workers: int = _MAX_WORKERS) -> Iterator[ThreadPoolExecutor]:
    pool = ThreadPoolExecutor(max_workers=max_workers)
    try:
        yield pool
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
```

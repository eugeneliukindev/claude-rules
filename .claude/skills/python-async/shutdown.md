# Shutdown

Consumers acknowledge only after processing, and drain inside the grace period — that is
`python-workers`. In a container the process is PID 1, which ignores a signal it has no handler for,
and only an exec-form start command lets the signal reach Python at all (`python-container`).

### A signal sets an event; the application stops taking work, drains with a deadline, and closes

**Why:** `SIGTERM`'s default action ends the process at once — no `finally` runs and nothing is
closed. A handler that sets an event lets the application stop accepting work, drain or cancel
what is in flight under a deadline, and close its resources in reverse order. Signals are handled
in the main thread only; worker threads get a stop event.

**Example:**
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

### A thread that does work is never a daemon; it watches a stop event and is joined with a deadline

**Why:** a daemon thread is killed wherever it stands when the interpreter exits — mid-write, with
its buffer unflushed. A thread that checks a stop event finishes its unit of work, and the join's
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

# Shutdown

On `SIGTERM` a worker stops fetching, lets the handlers in flight finish within a bound, abandons
the rest unacknowledged — the broker redelivers them, and the delivery limit counts each one — and
then closes its resources. The general shape is `python-async`'s; the worker's part is the numbers.
FastStream's drain timeout is in `python-faststream`.

### The handler deadline fits inside the drain, and the drain inside the orchestrator's grace period

**Why:** Kubernetes sends `SIGKILL` 30 seconds after `SIGTERM` by default; a drain longer than that
is killed mid-way, with nothing closed. The library's drain timeout is set explicitly, never left at
a default whose meaning is a library fact; a Celery warm shutdown waits for running tasks without a
limit, so the orchestrator decides for it. Room is left after the drain to close the pools.

**Example:**
```python
# WRONG — the orchestrator kills the worker at 30 seconds, mid-drain, and nothing is closed
_HANDLER_DEADLINE_SECONDS: Final = 20.0
_GRACEFUL_TIMEOUT_SECONDS: Final = 60.0


# CORRECT — handlers finish inside the drain, and the drain inside the 30-second grace period
_HANDLER_DEADLINE_SECONDS: Final = 20.0
_GRACEFUL_TIMEOUT_SECONDS: Final = 25.0
```

# Shutdown

On `SIGTERM` a worker stops fetching, lets the handlers in flight finish within a bound, abandons
the rest unacknowledged — the broker redelivers them, and the delivery limit counts each one — and
then closes its resources. The worker's part is the numbers.

### The handler deadline fits inside the drain, and the drain inside the orchestrator's grace period

**Why:** Kubernetes sends `SIGKILL` 30 seconds after `SIGTERM` by default; a drain longer than that
is killed mid-way, with nothing closed. The library's drain timeout is set explicitly, never left at
a default whose meaning is a library fact; a Celery warm shutdown waits for running tasks without a
limit, so the orchestrator decides for it. Room is left after the drain to close the pools.

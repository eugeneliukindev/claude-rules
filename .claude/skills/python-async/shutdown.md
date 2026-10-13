# Shutdown

Consumers acknowledge only after processing, and drain inside the grace period — that is
`python-workers`. In a container the process is PID 1, which ignores a signal it has no handler for,
and only an exec-form start command lets the signal reach Python at all (`python-container`).

### A signal sets an event; the application stops taking work, drains with a deadline, and closes

**Why:** `SIGTERM`'s default action ends the process at once — no `finally` runs and nothing is
closed. A handler that sets an event lets the application stop accepting work, drain or cancel
what is in flight under a deadline, and close its resources in reverse order. Signals are handled
in the main thread only; worker threads get a stop event (`python-sync`).

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

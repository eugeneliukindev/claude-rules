# The Worker's Composition Root

Settings, pools and clients are built once in `main()`, passed down and closed in reverse; nothing
connects at import time (why: `python-wiring`). FastStream's shape is in `python-faststream`.

### The handler gets its dependencies from a function `main()` calls, never from a module global

**Why:** a global built at import connects before the settings are read, cannot be replaced in a
test, and in a prefork worker is shared by every child. The library's wrapper is registered by a
function that receives the dependencies, so the handler stays the plain function `SKILL.md` asks
for.

**Example:**
```python
# WRONG — the inventory client is built at import, from the environment
_INVENTORY: Final = HttpRoomInventory(base_url=os.environ["INVENTORY_URL"])


async def on_booking_confirmed_task(body: str) -> None:
    await on_booking_confirmed(body.encode(), inventory=_INVENTORY)


# CORRECT — main() builds the inventory and registers the handler with it
def register_booking_handlers(consumer: Consumer, *, inventory: RoomInventory) -> None:
    async def on_booking_confirmed_task(body: str) -> None:
        await on_booking_confirmed(body.encode(), inventory=inventory)

    consumer.register("bookings.confirmed", on_booking_confirmed_task)
```

### A Celery or taskiq app object opens nothing; pools are built in the worker's startup hook

**Why:** both libraries decorate tasks with a module-level app object. It may stay a declaration as
long as it opens nothing; pools and clients are built in the worker's startup hook —
`TaskiqEvents.WORKER_STARTUP`, or Celery's `worker_process_init` in each prefork child, since a pool
built before the fork is shared by every child — and closed in the matching shutdown hook.

**Example:**
```python
# WRONG — the pool is created at import, before the fork: every child shares its sockets
celery_app = Celery("bookings")
_ENGINE: Final = create_engine(os.environ["DATABASE_URL"])


# CORRECT — each prefork child builds its own pool after the fork, and disposes it on exit
celery_app = Celery("bookings")
_resources = WorkerResources()


@worker_process_init.connect
def _open_resources(**_: object) -> None:
    _resources.open(Settings())


@worker_process_shutdown.connect
def _close_resources(**_: object) -> None:
    _resources.close()
```

# The Worker's Composition Root

Settings, pools and clients are built once in `main()`, passed down and closed in reverse; nothing
connects at import time (`modules.md`).

### The handler gets its dependencies from a function `main()` calls, never from a module global

**Why:** a global built at import connects before the settings are read, cannot be replaced in a
test, and in a prefork worker is shared by every child. The library's wrapper is registered by a
function that receives the dependencies, so the handler stays the plain function `SKILL.md` asks
for.

**Example:**
```python
# WRONG — the print station client is built at import, from the environment
_PRINT_STATION: Final = HttpPrintStation(base_url=os.environ["PRINT_STATION_URL"])


async def enlarge_scan(body: str) -> None:
    await on_enlargement_requested(body.encode(), print_station=_PRINT_STATION)


# CORRECT — main() builds the print station and registers the handler with it
def register_enlargement_handler(lab_queue: LabQueue, *, print_station: PrintStation) -> None:
    async def enlarge_scan(body: str) -> None:
        await on_enlargement_requested(body.encode(), print_station=print_station)

    lab_queue.register(_ENLARGEMENTS_QUEUE_NAME, enlarge_scan)
```

### A Celery or taskiq app object opens nothing; pools are built in the worker's startup hook

**Why:** both libraries decorate tasks with a module-level app object. It may stay a declaration as
long as it opens nothing; pools and clients are built in the worker's startup hook —
`TaskiqEvents.WORKER_STARTUP`, or Celery's `worker_process_init` in each prefork child, since a pool
built before the fork is shared by every child — and closed in the matching shutdown hook.

**Example:**
```python
# WRONG — the pool is created at import, before the fork: every child shares its sockets
photo_lab = Celery("photo_lab")
_SCAN_POOL: Final = connect_scan_pool(os.environ["SCAN_DATABASE_URL"])


# CORRECT — each prefork child builds its own pool after the fork, and disposes it on exit
photo_lab = Celery("photo_lab")
_lab = LabResources()


@worker_process_init.connect
def _open_lab(**_: object) -> None:
    settings = LabSettings()
    _lab.open(scan_database_url=settings.scan_database_url)


@worker_process_shutdown.connect
def _close_lab(**_: object) -> None:
    _lab.close()
```

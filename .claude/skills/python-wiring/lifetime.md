# Resource Lifetime

The root acquires, so the root releases; everything below it borrows.

## Contents

- A resource enters through its own context manager
- A known set of resources is one `with` statement, an item per resource
- An async root has the same shape
- A class closes only what it built
- Cleanup never raises over the block's own error
- No process-wide mutation in library or service code

### A resource enters through its own context manager

**Why:** a pool, a client or a session that is already a context manager needs no wrapper — a
hand-written one around it is one more name to learn, and copied into every project it becomes a
house convention nobody chose.
**Except:** an object with only `close()` enters through `contextlib.closing`; an acquire and
release pair the library leaves to the caller gets a `@contextmanager` named for what it yields,
releasing in `finally`; a class with `__enter__`/`__exit__` when the object has other methods
besides those two.

**Example:**
```python
# WRONG — a wrapper around a pool that is already a context manager
@contextmanager
def registry_pool_scope(registry_url: str) -> Iterator[RegistryPool]:
    pool = RegistryPool(registry_url)
    try:
        yield pool
    finally:
        pool.close()


def main() -> None:
    settings = Settings()
    with registry_pool_scope(settings.registry_url) as pool:
        print_loan_schedule(agreements=PostgresAgreementLedger(pool))


# CORRECT — the pool's own with
def main() -> None:
    settings = Settings()
    with RegistryPool(settings.registry_url) as pool:
        print_loan_schedule(agreements=PostgresAgreementLedger(pool))
```

### A known set of resources is one `with` statement, an item per resource

**Why:** the parenthesized form closes them in reverse order exactly as nesting would, and shows
what is open; `ExitStack` is for a count known only at runtime — one connection per configured
lender archive — and hides that for two or three fixed resources.

**Example:**
```python
# WRONG — an ExitStack for two fixed resources hides what is open and in which order it closes
def main() -> None:
    settings = Settings()
    with ExitStack() as resources:
        pool = resources.enter_context(RegistryPool(settings.registry_url))
        client = resources.enter_context(ValuationClient(base_url=settings.valuation_url))
        import_valuations(agreements=PostgresAgreementLedger(pool), valuations=client)


# CORRECT — one with item per resource, closed in reverse order
def main() -> None:
    settings = Settings()
    with (
        RegistryPool(settings.registry_url) as pool,
        ValuationClient(base_url=settings.valuation_url) as client,
    ):
        import_valuations(agreements=PostgresAgreementLedger(pool), valuations=client)
```

### An async root has the same shape

**Why:** `asyncio.run(main())` once, `async with` an item per resource, `AsyncExitStack` only for a
runtime count. A pool created with a bare `await` and never entered is closed by nobody: the process
exits with its connections open and the server logs them as dropped. In a web service the
framework's startup and shutdown hook is this root.

**Example:**
```python
# WRONG — the pool is created and never closed; shutdown drops its connections mid-protocol
async def main() -> None:
    settings = Settings()
    pool = await AsyncRegistryPool.open(settings.registry_url)
    office = LoanOffice(agreements=AsyncAgreementLedger(pool))
    await consume_loan_requests(office)


# CORRECT — entered like any resource, and closed on the way out whatever happened
async def main() -> None:
    settings = Settings()
    async with AsyncRegistryPool(settings.registry_url) as pool:
        office = LoanOffice(agreements=AsyncAgreementLedger(pool))
        await consume_loan_requests(office)
```

### A class closes only what it built

**Why:** a resource passed in belongs to whoever passed it, and closing it breaks every other user;
a store that built its own client and never closed it leaked a connection per instance.

**Example:**
```python
# WRONG — close() also shuts down an executor the caller passed in, and every other user of it
@final
class FacsimileRenderer:
    def __init__(
        self, *, executor: Executor | None = None, max_workers: int = _MAX_FACSIMILE_WORKERS
    ) -> None:
        self._executor = executor or ThreadPoolExecutor(max_workers=max_workers)

    def render(self, exhibit: Exhibit) -> Future[bytes]:
        return self._executor.submit(render_facsimile, exhibit)

    def close(self) -> None:
        self._executor.shutdown()


# CORRECT — remembers whether it built the executor, and shuts down only its own
@final
class FacsimileRenderer:
    def __init__(
        self, *, executor: Executor | None = None, max_workers: int = _MAX_FACSIMILE_WORKERS
    ) -> None:
        self._owns_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(max_workers=max_workers)

    def render(self, exhibit: Exhibit) -> Future[bytes]:
        return self._executor.submit(render_facsimile, exhibit)

    def close(self) -> None:
        if self._owns_executor:
            self._executor.shutdown()
```

### Cleanup never raises over the block's own error

**Why:** `__exit__` propagates by default, and a release that fails replaces the error the caller
needed — a failed two-phase commit once tried to roll back, a state guard refused the rollback, and
the guard's error was all the caller ever saw.

**Example:**
```python
# WRONG — a failed release replaces the block's own error, and the caller's except misses it
@contextmanager
def gallery_hold(gallery_id: GalleryId, *, holds: GalleryHolds) -> Iterator[GalleryHold]:
    hold = holds.place(gallery_id)
    try:
        yield hold
    finally:
        holds.lift(hold)


# CORRECT — the release failure is logged on its own, and the block's error propagates intact
@contextmanager
def gallery_hold(gallery_id: GalleryId, *, holds: GalleryHolds) -> Iterator[GalleryHold]:
    hold = holds.place(gallery_id)
    try:
        yield hold
    finally:
        try:
            holds.lift(hold)
        except HoldLiftError:
            logger.exception("gallery hold lift failed", extra={"gallery_id": gallery_id})
```

### No process-wide mutation in library or service code

**Why:** a context manager that flips process state — `chdir`, an environment variable, logging
configuration — changes every other caller for its duration; it belongs to tests and entry points
only.

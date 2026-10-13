---
name: python-wiring
description: >-
  Designs construction and configuration: one composition root, dependencies through the
  constructor, resource lifetime, settings passed as fields, constants, parameter objects. Use
  when writing an entry point or an application factory, deciding where an object is built, adding
  a settings field or a constant, or removing a global.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Wiring: Composition Root, Resource Lifetime

Which layer may import which is `python-layers`. In an ASGI service the composition root is the
application's lifespan (`python-fastapi`); a cashews `Cache` connects when the root calls `setup()`
(`python-cashews`).

## Composition Root

### All construction happens in one place — the composition root

**Why:** the entry point of a worker or CLI, or the application factory of a service, is the one
place that knows every concrete class; everywhere else a dependency arrives through a constructor or
a signature, so a test or a second entry point can hand in another.

**Example:**
```python
# WRONG — the service wires itself: a module-level pool, opened at import from the environment
pool = open_database_pool(os.environ["DATABASE_URL"])


@final
class InvoiceService:
    def __init__(self) -> None:
        self._invoices = PostgresInvoiceRepository(pool)

    def issue(self, draft: InvoiceDraft) -> InvoiceId:
        return self._invoices.add(Invoice.from_draft(draft))


# CORRECT — the root builds settings, resources, adapters and services, and hands them down
def main() -> None:
    settings = Settings()
    with managed_pool(settings.database_url) as pool:
        invoices = InvoiceService(invoices=PostgresInvoiceRepository(pool), clock=SystemClock())
        run_consumer(invoices, batch_size=settings.consumer_batch_size)
```

### A constructor only assigns; it never builds a collaborator or reads settings to choose one

**Why:** a collaborator built inside cannot be replaced by a fake, and the choice it makes from
settings is a second composition root hidden in a class.

**Example:**
```python
# WRONG — the notifier is chosen and built inside, from a setting the service should not know
@final
class ReminderService:
    def __init__(self, *, invoices: InvoiceRepository, settings: Settings) -> None:
        self._invoices = invoices
        self._notifier = (
            SmsNotifier(settings.sms_api_key) if settings.sms_enabled else EmailNotifier()
        )

    def remind_overdue(self, today: date) -> None:
        for invoice in self._invoices.overdue_on(today):
            self._notifier.send(invoice.customer_id, Message(f"Invoice {invoice.number} is due"))


# CORRECT — the root chose and built the notifier; the constructor assigns what it is given
@final
class ReminderService:
    def __init__(self, *, invoices: InvoiceRepository, notifier: Notifier) -> None:
        self._invoices = invoices
        self._notifier = notifier

    def remind_overdue(self, today: date) -> None:
        for invoice in self._invoices.overdue_on(today):
            self._notifier.send(invoice.customer_id, Message(f"Invoice {invoice.number} is due"))
```

### A default collaborator is the one exception, and it is what production runs

**Why:** `clock: Clock | None = None` then `clock or SystemClock()` is what pydantic
(`ns_resolver or NsResolver()`) and the OpenTelemetry SDK (`span_limits or SpanLimits()`) do: the
parameter is a seam for a test or a second root, and the default costs the caller nothing. A default
that needs a setting wastes that setting whenever the collaborator is passed.
**Except:** `is None` instead of `or` when a valid value can be falsy — an empty mapping, `0`. A
plain value — a path, a limit — is no collaborator: it is defaulted in the signature
(`functions.md`).

**Example:**
```python
# WRONG — the default needs a host, so smtp_host is wasted whenever a notifier is passed
@final
class InvoiceService:
    def __init__(
        self, *, smtp_host: str, notifier: Notifier | None = None, clock: Clock | None = None
    ) -> None:
        self._notifier = notifier or SmtpNotifier(host=smtp_host)
        self._clock = clock or SystemClock()

    def issue(self, draft: InvoiceDraft) -> Invoice:
        return Invoice.from_draft(draft, issued_at=self._clock.now())


# CORRECT — the clock defaults to what production runs; the notifier is built by the root
@final
class InvoiceService:
    def __init__(self, *, notifier: Notifier, clock: Clock | None = None) -> None:
        self._notifier = notifier
        self._clock = clock or SystemClock()

    def issue(self, draft: InvoiceDraft) -> Invoice:
        return Invoice.from_draft(draft, issued_at=self._clock.now())
```

### A class closes only what it built

**Why:** a resource passed in belongs to whoever passed it, and closing it breaks every other user;
a store that built its own client and never closed it leaked a connection per instance.

**Example:**
```python
# WRONG — close() also shuts down a pool the caller passed in, and every other user of it
@final
class ThumbnailRenderer:
    def __init__(
        self, executor: Executor | None = None, *, max_workers: int = _MAX_RENDER_WORKERS
    ) -> None:
        self._executor = executor or ThreadPoolExecutor(max_workers=max_workers)

    def render(self, document: Document) -> Future[bytes]:
        return self._executor.submit(render_thumbnail, document)

    def close(self) -> None:
        self._executor.shutdown()


# CORRECT — remembers whether it built the pool, and shuts down only its own
@final
class ThumbnailRenderer:
    def __init__(
        self, executor: Executor | None = None, *, max_workers: int = _MAX_RENDER_WORKERS
    ) -> None:
        self._owns_executor = executor is None
        self._executor = executor or ThreadPoolExecutor(max_workers=max_workers)

    def render(self, document: Document) -> Future[bytes]:
        return self._executor.submit(render_thumbnail, document)

    def close(self) -> None:
        if self._owns_executor:
            self._executor.shutdown()
```

### The wiring is plain code; a DI framework stays inside the root if one is used at all

**Why:** a container is unnecessary until wiring is measured in hundreds of objects, and one that is
reached from inside the code is a service locator — the hidden global below.

### No global singletons, no service locator

**Why:** a module-level connection or a globally reachable container is hidden global state:
import-time side effects, un-fakeable tests, ordering bugs.
**Except:** the module-level names that record nothing until the entry point configures them — the
logger, the tracer, the meter and its instruments, a context variable (`python-observability`); the
Celery or taskiq app object tasks are decorated with, whose pools are built in the worker's startup
hook (`python-workers`); a decorator library's cache object, which connects only when the root sets
it up.

**Example:**
```python
# WRONG — a module-level client connected at import: every importer shares it, no test replaces it
storage = ObjectStorageClient(os.environ["STORAGE_URL"])


def archive(document: Document) -> str:
    return storage.put(f"archive/{document.document_id}", document.content)


# CORRECT — the client is built by the root and passed to the one object that uses it
@final
class DocumentArchive:
    def __init__(self, *, storage: ObjectStorage, prefix: str = DEFAULT_ARCHIVE_PREFIX) -> None:
        self._storage = storage
        self._prefix = prefix

    def archive(self, document: Document) -> str:
        return self._storage.put(f"{self._prefix}/{document.document_id}", document.content)
```

### Scopes are explicit: application-scoped objects built once, request-scoped by a passed factory

**Why:** an object with per-request state built once is shared between requests; a pooled resource
built per request exhausts the pool.

**Example:**
```python
# WRONG — one request's catalog built once: the first request's language answers every request
@final
class ReceiptRenderer:
    def __init__(self, *, catalog: TranslationCatalog) -> None:
        self._catalog = catalog

    def render(self, receipt: Receipt) -> str:
        return self._catalog.translate("receipt.total", amount=receipt.total)


# CORRECT — the renderer holds the factory; each request builds the catalog for its own locale
@final
class ReceiptRenderer:
    def __init__(self, *, catalog_for: Callable[[Locale], TranslationCatalog]) -> None:
        self._catalog_for = catalog_for

    def render(self, receipt: Receipt, *, locale: Locale) -> str:
        return self._catalog_for(locale).translate("receipt.total", amount=receipt.total)
```

### Tests get their own root

**Why:** a helper that builds the graph with in-memory fakes and a fixed clock is the production
wiring with other leaves; if a test needs to patch a dependency, the production wiring is wrong.

**Example:**
```python
# WRONG — the test patches a module attribute the service reaches for
def test_overdue_invoices_are_reminded(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[Message] = []
    monkeypatch.setattr(reminders, "notifier", RecordingNotifier(sent))
    reminders.remind_overdue(date(2026, 3, 1))


# CORRECT — the test builds the same graph from fakes
def test_overdue_invoices_are_reminded() -> None:
    notifier = RecordingNotifier()
    invoices = InMemoryInvoiceRepository([overdue_invoice(due_on=date(2026, 2, 1))])
    service = ReminderService(invoices=invoices, notifier=notifier)

    service.remind_overdue(date(2026, 3, 1))

    assert len(notifier.sent) == 1
```

## Resource Lifetime

The root acquires, so the root releases; everything below it borrows.

### An own resource is a `@contextmanager` named for its lifecycle, releasing in `finally`

**Why:** `try/finally: close()` at every use site is the one that gets forgotten; a context manager
named for the lifecycle — `managed_pool` — yields exactly once and cleans up in `finally`, so an
exception in the block still releases.
**Except:** a class with `__enter__`/`__exit__` when the object has other methods besides those two.

### A known set of resources is one `with` statement, an item per resource

**Why:** the parenthesized form closes them in reverse order exactly as nesting would, and shows
what is open; `ExitStack` is for a count known only at runtime — one connection per configured shard
— and hides that for two or three fixed resources.

**Example:**
```python
# WRONG — an ExitStack for two fixed resources hides what is open and in which order it closes
def main() -> None:
    settings = Settings()
    with ExitStack() as resources:
        pool = resources.enter_context(managed_pool(settings.database_url))
        client = resources.enter_context(managed_http_client(settings.http_timeout_seconds))
        run_import(documents=PostgresDocumentRepository(pool), source=HttpDocumentSource(client))


# CORRECT — one with item per resource, closed in reverse order
def main() -> None:
    settings = Settings()
    with (
        managed_pool(settings.database_url) as pool,
        managed_http_client(settings.http_timeout_seconds) as client,
    ):
        run_import(documents=PostgresDocumentRepository(pool), source=HttpDocumentSource(client))
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
    pool = await AsyncConnectionPool.open(settings.database_url)
    documents = DocumentService(documents=PostgresDocumentRepository(pool))
    await run_consumer(documents)


# CORRECT — entered like any resource, and closed on the way out whatever happened
async def main() -> None:
    settings = Settings()
    async with managed_async_pool(settings.database_url) as pool:
        documents = DocumentService(documents=PostgresDocumentRepository(pool))
        await run_consumer(documents)
```

### Cleanup never raises over the block's own error

**Why:** `__exit__` propagates by default, and a release that fails replaces the error the caller
needed — a failed two-phase commit once tried to roll back, a state guard refused the rollback, and
the guard's error was all the caller ever saw.

**Example:**
```python
# WRONG — a failed release replaces the block's own error, and the caller's except misses it
@contextmanager
def managed_lock(name: str, *, locks: LockService) -> Iterator[Lock]:
    lock = locks.acquire(name)
    try:
        yield lock
    finally:
        locks.release(lock)


# CORRECT — the release failure is logged on its own, and the block's error propagates intact
@contextmanager
def managed_lock(name: str, *, locks: LockService) -> Iterator[Lock]:
    lock = locks.acquire(name)
    try:
        yield lock
    finally:
        try:
            locks.release(lock)
        except LockReleaseError:
            logger.exception("lock release failed", extra={"lock": name})
```

### No hidden global mutation in library or service code

**Why:** a context manager that flips process state — `chdir`, an environment variable, logging
configuration — changes every other caller for its duration; it belongs to tests and entry points
only.

## Constants

**Before adding a module constant or a constants module, read [constants.md](constants.md)** — a
constant lives beside the one module that owns its concept, never in a grab-bag.

## Settings and Startup

**Before adding or reading a settings field, an environment variable, a feature flag or a secret,
read [settings.md](settings.md)** — typed settings built at the root, the server's apart from the
application's, fields passed instead of the root, tests that never build them, validation at startup,
secrets without defaults.

## Parameter Objects

**Before grouping parameters into an options object or forwarding `**kwargs`, read
[parameter-objects.md](parameter-objects.md)** — a concept the callee uses whole, never the
configuration root renamed; typed options through `Unpack`.

---
name: python-wiring
description: >-
  Designs construction and configuration: one composition root, scopes, resource lifetime, settings,
  constants. ALWAYS invoke this skill when a task writes an entry point, main() or an application
  factory, opens a pool, client or connection, reads environment variables or a settings field, or
  fixes an import that connects. Do not wire objects directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Wiring: Composition Root, Resource Lifetime

In an ASGI service the composition root is the application's lifespan. Collaborators arrive
through the constructor (`classes.md`), plain values instead of the settings object
(`functions.md`), nothing runs at import (`modules.md`), and a test hands in fakes instead of
patching (`testing.md`).

## Composition Root

### All construction happens in plain code in one place — the composition root — and a container, if one is used at all, never leaves it

**Why:** the entry point of a worker or CLI, or the application factory of a service, is the one
place that knows every concrete class; a function below it that opens its own resources is a second
root, and no test or second entry point can hand it another. A container is unnecessary until
wiring is measured in hundreds of objects, and one handed below the root is a service locator: the
signature no longer lists what the class needs, and a test must register every lookup before the
first call.
**Except:** module-level names that hold nothing until the root configures them (`modules.md`) —
and the task-queue app object tasks are decorated with, whose pools the worker's startup hook
builds.

**Example:**
```python
# WRONG — a second root below main: the intake opens its own pool from a URL it was handed
def run_loan_intake(*, registry_url: str, batch_size: int) -> None:
    with RegistryPool(registry_url) as pool:
        office = LoanOffice(agreements=PostgresAgreementLedger(pool))
        consume_loan_requests(office, batch_size=batch_size)

def main() -> None:
    settings = Settings()
    run_loan_intake(registry_url=settings.registry_url, batch_size=settings.intake_batch_size)

# CORRECT — main builds settings, resources, adapters and services, and hands them down
def main() -> None:
    settings = Settings()
    with RegistryPool(settings.registry_url) as pool:
        office = LoanOffice(agreements=PostgresAgreementLedger(pool))
        consume_loan_requests(office, batch_size=settings.intake_batch_size)
```

### The root chooses an implementation from settings; a class never does

**Why:** a constructor that picks between two implementations from a flag is a second composition
root hidden in a class: it must know every implementation's settings, and a test has to set the
flag to reach the fake.

**Example:**
```python
# WRONG — the channel is chosen inside, from values the reminders should not know
@final
class ReturnReminders:
    def __init__(
        self, *, agreements: AgreementLedger, portal_enabled: bool, portal_url: str
    ) -> None:
        self._agreements = agreements
        self._lender_channel = (
            LenderPortalChannel(base_url=portal_url) if portal_enabled else LenderEmailChannel()
        )

    def remind_ending(self, today: date) -> None:
        for agreement in self._agreements.ending_on(today):
            self._lender_channel.send(agreement.lender_id, f"Loan {agreement.number} ends today")

# CORRECT — the root chose and built the channel; the reminders take the contract
@final
class ReturnReminders:
    def __init__(self, *, agreements: AgreementLedger, lender_channel: LenderChannel) -> None:
        self._agreements = agreements
        self._lender_channel = lender_channel

    def remind_ending(self, today: date) -> None:
        for agreement in self._agreements.ending_on(today):
            self._lender_channel.send(agreement.lender_id, f"Loan {agreement.number} ends today")
```

### A default collaborator is what production runs, and needs no setting

**Why:** `clock: Clock | None = None` then `clock or WallClock()` is what pydantic
(`ns_resolver or NsResolver()`) and the OpenTelemetry SDK (`span_limits or SpanLimits()`) do: the
parameter is a seam for a test or a second root, and the default costs the caller nothing. A default
that needs a setting wastes that setting whenever the collaborator is passed.
**Except:** `is None` instead of `or` when a valid value can be falsy — an empty mapping, `0`. A
plain value — a path, a limit — is no collaborator: it is defaulted in the signature
(`functions.md`).

**Example:**
```python
# WRONG — the default needs a URL, so courier_api_url is wasted whenever couriers are passed
@final
class CourierScheduler:
    def __init__(
        self,
        *,
        courier_api_url: str,
        couriers: CourierBooking | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._couriers = couriers or CourierApiBooking(base_url=courier_api_url)
        self._clock = clock or WallClock()

    def book_courier(self, agreement: LoanAgreement) -> CourierSlot:
        return self._couriers.book(agreement.exhibit_id, earliest=self._clock.now())

# CORRECT — the clock defaults to what production runs; the couriers are built by the root
@final
class CourierScheduler:
    def __init__(self, *, couriers: CourierBooking, clock: Clock | None = None) -> None:
        self._couriers = couriers
        self._clock = clock or WallClock()

    def book_courier(self, agreement: LoanAgreement) -> CourierSlot:
        return self._couriers.book(agreement.exhibit_id, earliest=self._clock.now())
```

### Scopes are explicit: application-scoped objects built once, request-scoped by a passed factory

**Why:** an object with per-request state built once is shared between requests; a pooled resource
built per request exhausts the pool.

**Example:**
```python
# WRONG — one request's glossary built once: the first request's language answers every request
@final
class WallLabelWriter:
    def __init__(self, *, glossary: LabelGlossary) -> None:
        self._glossary = glossary

    def write_label(self, exhibit: Exhibit) -> str:
        return self._glossary.caption(exhibit.title_key, lender=exhibit.lender_name)

# CORRECT — the writer holds the factory; each request builds the glossary for its own locale
@final
class WallLabelWriter:
    def __init__(self, *, glossary_for: Callable[[Locale], LabelGlossary]) -> None:
        self._glossary_for = glossary_for

    def write_label(self, exhibit: Exhibit, *, locale: Locale) -> str:
        return self._glossary_for(locale).caption(exhibit.title_key, lender=exhibit.lender_name)
```

## Resource Lifetime

The root acquires, so the root releases; everything below it borrows.

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

### A known set of resources is one `with` or `async with` statement, an item per resource, and an async root runs once under `asyncio.run`

**Why:** the parenthesized form closes them in reverse order exactly as nesting would, and shows
what is open; `ExitStack` and `AsyncExitStack` are for a count known only at runtime — one
connection per configured lender archive — and hide that for two or three fixed resources. A pool
created with a bare `await` and never entered is closed by nobody: the process exits with its
connections open and the server logs them as dropped. In a web service the framework's startup and
shutdown hook is this root.

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

## Constants

### A constant lives next to its single user

**Why:** a constant shared by several modules lives in the module that owns the concept; a global
grab-bag of constants is a module every other module imports and nobody owns.

## Settings and Startup

Below the root nothing takes the settings object (`functions.md`).

## The Settings Object
### Configuration is typed settings, built once at the root and unpacked there

**Why:** anything that varies by environment read from `os.environ` across the code is a dependency
nobody declared; a cached accessor behind `@lru_cache` is a module-level instance by another name,
global, and changed in a test only through `cache_clear()` and the environment.

**Example:**
```python
# WRONG — a global behind a function: every caller reaches it, and no test can hand in another
@lru_cache
def loan_settings() -> Settings:
    return Settings()

def fetch_insured_value(exhibit_id: ExhibitId, *, valuations: ValuationClient) -> Decimal:
    settings = loan_settings()
    return valuations.insured_value(exhibit_id, currency=settings.insurance_currency)

# CORRECT — built once by the root, which unpacks the fields each part needs
def fetch_insured_value(
    exhibit_id: ExhibitId, *, valuations: ValuationClient, currency: str
) -> Decimal:
    return valuations.insured_value(exhibit_id, currency=currency)

def main() -> None:
    settings = Settings()
    with ValuationClient(base_url=settings.valuation_url) as valuations:
        for exhibit_id in read_exhibit_ids(sys.stdin):
            insured_value = fetch_insured_value(
                exhibit_id, valuations=valuations, currency=settings.insurance_currency
            )
            print_insurance_certificate(exhibit_id, insured_value=insured_value)
```

### The server's settings are a class apart from the application's

**Why:** the host, the port and the drain configure the process that serves; the registry URL and
the limits configure what it serves. One class holding both makes every entry point supply all of
it — a worker running the same use cases cannot start without a port it never binds — and lets the
application's fields grow server knobs. Each entry point builds the classes of the parts it runs.

**Example:**
```python
# WRONG — one class: the worker needs HOST and PORT set before it starts
def serve_main() -> None:
    settings = Settings()
    serve_http(
        build_loan_api(registry_url=settings.registry_url), host=settings.host, port=settings.port
    )

def worker_main() -> None:
    settings = Settings()
    run_loan_worker(registry_url=settings.registry_url)

# CORRECT — each entry point builds what it runs, and the worker knows nothing of the server
def serve_main() -> None:
    listener_settings = ListenerSettings()
    registry_settings = LoanRegistrySettings()
    serve_http(
        build_loan_api(registry_url=registry_settings.registry_url),
        host=listener_settings.host,
        port=listener_settings.port,
    )

def worker_main() -> None:
    registry_settings = LoanRegistrySettings()
    run_loan_worker(registry_url=registry_settings.registry_url)
```

### Behaviour never branches on the deployment environment's name; each difference is a setting

**Why:** `if environment == "production"` is code that runs for the first time in the environment it
guards, and every new environment — a staging copy, a customer's install — must be added to every
such branch. Each difference becomes a setting of its own — a URL, a flag, a limit — that the entry
point reads with the rest and hands in. The environment's name is metadata only: a resource
attribute on traces and metrics, a log field.

**Example:**
```python
# WRONG — the sandbox is chosen by the environment's name, untested until production
def main() -> None:
    settings = Settings()
    if settings.environment == "production":
        insurer = TransitInsurer(base_url="https://api.insurer.example.com")
    else:
        insurer = TransitInsurer(base_url="https://sandbox.insurer.example.com")
    run_loan_intake(insurer=insurer)

# CORRECT — the difference is a setting of its own; every environment runs the same code
def main() -> None:
    settings = Settings()
    run_loan_intake(insurer=TransitInsurer(base_url=settings.insurer_url))
```

## Startup and Secrets

### Configuration is validated at startup, before serving

**Why:** a missing or malformed variable then stops the process with a clear message, instead of
failing the first request hours later; a feature flag is a typed field read once and injected,
never queried deep in the call stack. The settings class is tested alone, with
`monkeypatch.setenv` and `delenv`: a loader reads the environment even when it skips the `.env`
file — measured, a variable left in the shell filled a field the test never set.

**Example:**
```python
# WRONG — read on first use: a misspelt variable name surfaces as a 500 on the first request
def insurer_url() -> str:
    return os.environ["INSURER_URL"]

# CORRECT — every field parsed and validated at once, when main() builds the settings
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Settings:
    insurer_url: str
    valuation_timeout_seconds: float
    courier_tracking_enabled: bool

    @classmethod
    def from_environment(cls, environ: Mapping[str, str]) -> Self:
        timeout_seconds = float(environ["VALUATION_TIMEOUT_SECONDS"])
        if timeout_seconds <= 0:
            raise InvalidLoanSettingError("VALUATION_TIMEOUT_SECONDS", timeout_seconds)
        return cls(
            insurer_url=environ["INSURER_URL"],
            valuation_timeout_seconds=timeout_seconds,
            courier_tracking_enabled=environ.get("COURIER_TRACKING_ENABLED") == "true",
        )
```

### A secret never appears in code, in a default or in a log

**Why:** a placeholder default lets a deploy that forgot the variable start and run with
`"changeme"`; a plain `str` secret is printed by the first `repr` of the settings.

## Parameter Objects

### A cohesive group of values passed as one frozen object is encouraged

**Why:** `RetryPolicy(attempts, backoff, jitter)` is a concept the callee uses whole; the
configuration root is a namespace of unrelated groups. Three questions tell them apart: does the
callee use essentially every field; is the name a concept (`RetryPolicy`) rather than an origin
(`Settings`, `Config`, `Env`); could a test build it in one line from literals? Three yeses make a
value to pass; one no makes the configuration root wearing a smaller name.

### A dispatcher that forwards options forwards them typed

**Why:** a factory handing one option bundle to whichever builder it selected takes `**options:
Unpack[SomeOptions]`, a `TypedDict` naming every field, so a misspelt option is rejected at the call
site; what it cannot check is that the selected builder got every field it requires — that arrives
as a `TypeError` on the first call, so builders that share one signature are preferred.

**Example:**
```python
# WRONG — untyped options: a misspelt seal_ttl_secs passes the checker and the builder swallows it
def build_crate_tracker(kind: TrackerKind, **options: object) -> CrateTracker:
    return _TRACKER_BUILDER_BY_KIND[kind](**options)

# CORRECT — every option is named once, and the checker rejects a misspelt one at the call site
class TrackerOptions(TypedDict, total=False):
    courier_name: str
    seal_ttl_seconds: float

def build_crate_tracker(kind: TrackerKind, **options: Unpack[TrackerOptions]) -> CrateTracker:
    return _TRACKER_BUILDER_BY_KIND[kind](**options)
```


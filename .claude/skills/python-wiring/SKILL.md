---
name: python-wiring
description: >-
  Python composition root and configuration: all construction in one place, dependencies through
  the constructor, resource lifetime owned by the root, typed settings passed as fields rather than
  as a config object, constants versus configuration, cohesive parameter objects. Use when writing a
  Python entry point or application factory, deciding where an object is built, adding a settings
  field or a module constant, or removing a global singleton.
---

# Wiring: Composition Root, Configuration

Which layer may import which is `python-layers`.

## Composition Root

All object construction happens in **one place** — the composition root: the entry point for a
worker or CLI, the application factory for a service. Everywhere else, dependencies arrive through
the constructor or the function signature.

- **Classes never instantiate their collaborators.** A service receives its repository and its
  notifier; it never builds one, and never reads settings to decide which to build. The constructor
  only assigns.
- **A default collaborator is the one exception**: `clock: Clock | None = None`, then
  `self._clock = clock or SystemClock()` — what `pydantic`
  (`ns_resolver or NsResolver()`) and the OpenTelemetry SDK (`span_limits or SpanLimits()`) do.
  Only when the default is what production runs, is built from nothing the caller passes for it
  alone, and the parameter is a seam for a test or a second root. A default that needs settings
  makes them parameters wasted whenever the collaborator is passed — inject it, built by the root.
  `is None` rather than `or` when a valid value can be falsy — an empty mapping, `0`.

```python
# WRONG — the default needs a host, so smtp_host is wasted whenever a notifier is passed
@final
class InvoiceService:
    def __init__(
        self, *, smtp_host: str, notifier: Notifier | None = None, clock: Clock | None = None
    ) -> None:
        self._notifier = notifier or SmtpNotifier(host=smtp_host)
        self._clock = clock or SystemClock()

# CORRECT — the clock defaults to what production runs; the notifier is built by the root
@final
class InvoiceService:
    def __init__(self, *, notifier: Notifier, clock: Clock | None = None) -> None:
        self._notifier = notifier
        self._clock = clock or SystemClock()
```

- **The wiring is plain code**: build settings, build shared resources, build adapters, build
  services, hand them to the entry points. A DI framework is unnecessary until wiring is measured
  in hundreds of objects; if one is used, it is confined to the composition root.
- **Resource lifetime is owned by the root**: pools and clients are created once, passed down, and
  closed in reverse order on shutdown — one `with` statement or the framework's lifespan hook, never
  `atexit`, never per-request construction of pooled resources.
- **No global singletons, no service locator.** A module-level connection or a globally reachable
  container is hidden global state: import-time side effects, un-fakeable tests, ordering bugs. The
  only module-level objects are constants and the logger — and its kin, the tracer, the meter
  with its instruments and a context variable, which record nothing until the entry point
  configures them (`python-observability`).
- **Scopes are explicit**: application-scoped objects built once in the root; request-scoped
  objects built per request by an explicitly passed factory.
- **Tests get their own root**: a helper that builds the object graph with in-memory fakes and a
  fixed clock. If a test needs to patch a dependency, the production wiring is wrong.

```python
# WRONG — self-wiring class, module-level singleton, import-time side effect
engine = create_engine(os.environ["DATABASE_URL"])

class OrderService:
    def __init__(self) -> None:
        self._repository = PostgresOrderRepository(engine)

# CORRECT — one composition root owns construction and lifetime
def main() -> None:
    settings = Settings()  # fail fast
    with managed_engine(settings.database_url) as engine:
        order_service = OrderService(
            repository=PostgresOrderRepository(engine),
            now=lambda: datetime.now(UTC),
        )
        run_consumer(order_service, batch_size=settings.consumer_batch_size)
```

## Resource Lifetime

The root acquires, so the root releases; everything below it borrows.

- **Anything acquired is released by a context manager**: files, locks, sessions, transactions,
  clients, temporary state. `try/finally: close()` is only for *implementing* one.
- **Own resources get `@contextmanager`** (or the async form): yield exactly once, clean up in
  `finally`, and name it for the lifecycle — `managed_engine`. A class with `__enter__`/`__exit__`
  only when the object has other methods besides those two.

```python
# WRONG — an exception in the with block never reaches dispose(): the pool stays open
@contextmanager
def managed_engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    yield engine
    engine.dispose()

# CORRECT — finally runs whether the block returns or raises
@contextmanager
def managed_engine(database_url: str) -> Iterator[Engine]:
    engine = create_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
```

- **A known set of resources is one `with` statement with an item per resource** — the
  parenthesized form, which closes them in reverse order exactly as nesting would, and which ruff's
  `SIM117` asks for instead of nested blocks. `ExitStack` only when the number is known at runtime
  alone, such as one connection per configured shard; for two or three fixed resources it hides
  what the items of one `with` show.

```python
# WRONG — an ExitStack for two fixed resources hides what is open and in which order it closes
def main() -> None:
    settings = Settings()
    with ExitStack() as resources:
        engine = resources.enter_context(managed_engine(settings.database_url))
        client = resources.enter_context(managed_http_client(settings.http_timeout_seconds))
        run_import(orders=PostgresOrderRepository(engine), catalog=HttpCatalog(client))

# CORRECT — one with item per resource, closed in reverse order
def main() -> None:
    settings = Settings()
    with (
        managed_engine(settings.database_url) as engine,
        managed_http_client(settings.http_timeout_seconds) as client,
    ):
        run_import(orders=PostgresOrderRepository(engine), catalog=HttpCatalog(client))
```

- **`__exit__` propagates by default.** Cleanup must not raise over the original error; if it can
  fail, catch and log its failure separately. A failed two-phase commit once tried to roll back, a
  state guard refused the rollback, and the guard's error was all the caller ever saw — the
  database's reason was gone.

```python
# WRONG — a failed release replaces the block's own error, and the caller's except misses it
@contextmanager
def managed_lock(locks: LockService, name: str) -> Iterator[Lock]:
    lock = locks.acquire(name)
    try:
        yield lock
    finally:
        locks.release(lock)

# CORRECT — the release failure is logged on its own, and the block's error propagates intact
@contextmanager
def managed_lock(locks: LockService, name: str) -> Iterator[Lock]:
    lock = locks.acquire(name)
    try:
        yield lock
    finally:
        try:
            locks.release(lock)
        except LockReleaseError:
            logger.exception("lock release failed", extra={"lock": name})
```

- **No hidden global mutation managers.** One that flips module or process state (`chdir`,
  environment variables, logging config) is test poison — fine in tests and entry points, never in
  library or service code.

## Constants and Configuration

- **Constants live next to their single user**; a constant shared by several modules lives in the
  module that owns the concept, never in a global grab-bag.
- **Enum, not constant group.** Three or more related constants describing states or kinds are an
  `Enum`, with behaviour on the members if any exists.
- **Configuration is not constants.** Anything that varies by environment comes from a single typed
  settings object, constructed once at the composition root and **passed in** — never read from the
  environment scattered through the code, never a module-level settings instance imported
  everywhere.
- **Pass fields, never the configuration root.** A function takes `timeout_seconds: float`, not the
  object carrying everything the process was configured with. That object is a namespace of
  unrelated groups: the signature stops being a dependency list, the reader has to open the body to
  learn what is actually read, and a test has to build the whole configuration tree to make one
  call. An untyped `**kwargs` has the same defect — both say "something from over there" — so
  replacing one with the other is not a fix. Unpacking happens once, in the composition root, where
  the verbosity is the point.

```python
# WRONG — the signature hides what is read, and a test builds every settings group for one call
def fetch_rates(client: HttpClient, settings: Settings) -> RateTable: ...

# CORRECT — the signature is the dependency list; the root unpacks the settings
def fetch_rates(client: HttpClient, *, base_url: str, timeout_seconds: float) -> RateTable: ...
```

- **A cohesive group of parameters passed as one frozen value is a different thing, and it is
  encouraged.** `RetryPolicy(attempts, backoff, jitter)`, `PoolOptions(size, overflow, recycle)` —
  the callee uses all of it, and the type names a concept. What decides is cohesion, not the
  mechanism: a configuration root built out of frozen dataclasses is still a configuration root,
  and a parameter object validated at the boundary is still a parameter object. Three questions
  tell them apart — does the callee use essentially every field; is the name a concept
  (`RetryPolicy`) rather than an origin (`Settings`, `Config`, `Env`); could a test build it in one
  line from literals, with nothing read from the environment? Three yeses make it a value to pass;
  one no makes it the configuration root wearing a smaller name.
- **A dispatcher that forwards options is the exception, and it forwards them typed.** A factory
  that hands the same option bundle to whichever builder it selected takes `**options:
  Unpack[SomeOptions]`, with a `TypedDict` naming every field and marking the optional ones. Each
  builder then declares the fields it uses and swallows the rest. That keeps the call site naming
  concrete fields, keeps the checker able to reject a typo, and keeps the dispatcher from having to
  know the union of everything its builders might want. What it cannot check is that the selected
  builder got every field it requires: that arrives as a `TypeError` on the first call, so prefer
  builders that share one signature, and forward a bundle only when they genuinely cannot.

```python
# WRONG — untyped options: a misspelt timeout_secs passes the checker and the builder swallows it
def build_notifier(kind: NotifierKind, **options: object) -> Notifier:
    return _BUILDER_BY_KIND[kind](**options)

# CORRECT — every option is named once, and the checker rejects a misspelt one at the call site
class NotifierOptions(TypedDict, total=False):
    sender: str
    timeout_seconds: float

def build_notifier(kind: NotifierKind, **options: Unpack[NotifierOptions]) -> Notifier:
    return _BUILDER_BY_KIND[kind](**options)
```

- **Configuration is validated at startup, before serving.** A missing or malformed variable
  crashes the process immediately with a clear message — never a lazy read that fails on the first
  request hours later. Feature flags are typed fields, read once and injected, never queried ad hoc
  deep in the call stack.
- **Secrets never appear in code, defaults, or logs** — not even placeholder defaults.

```python
# WRONG — a placeholder default: a deploy that forgot the variable starts and uses "changeme"
@final
class Settings(BaseSettings):
    database_password: SecretStr = SecretStr("changeme")

# CORRECT — no default: a deploy that forgot the variable stops at startup, naming the field
@final
class Settings(BaseSettings):
    database_password: SecretStr
```

- Units, currencies, time zones and formats are constants or types, never repeated literals.
- Regular expressions are compiled once at module level, with a name describing what they match.

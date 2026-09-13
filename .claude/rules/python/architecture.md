---
paths:
  - "**/*.py"
---

# Architecture

Supplement to `core.md`. Governs module layout, encapsulation, imports, wiring, persistence,
external calls, compatibility, performance and security.

How directories are named and nested is a project decision, not a general rule: it follows the
domain, the team and the deployment shape, and a layout copied from elsewhere is a layout nobody
owns. What this file fixes is the part that does not vary — which way dependencies point, what a
package promises, and where construction happens.

## Module Layout

Every module has the same top-to-bottom order, so a reader always knows where to look:

1. Module docstring — one line, always.
2. `from __future__ import annotations`, when the target version needs it.
3. Imports.
4. `__all__` — in `__init__.py` only, and there it is the whole file.
5. Module-level constants.
6. Type aliases, `NewType`s, type parameters.
7. Module logger.
8. Exception classes.
9. Protocols and ABCs, then concrete classes, then the models private to this module. Public models
   used across the package live in their own module.
10. Public functions, high-level first — the step-down rule applies to modules as it does to
    classes.
11. Private functions, in call order.
12. The `__main__` guard — a single call to `main()`, nothing else.

Rules:

- **One reason to change per module.** A module that mixes I/O, domain rules and presentation must
  be split.
- **Size is a smell, not a limit.** When a module grows past what a reader can hold, look for a
  seam. The linters enforce a hard ceiling; the seam is your judgement.
- **No executable statements at import time** other than constants and the logger. No network calls,
  no file reads, no settings construction at module level — these make imports slow,
  order-dependent and untestable.
- **`main()` is a function, never module-level code.**

**A module name that reaches `sys.path` directly must not shadow a standard-library module** —
`types`, `typing`, `email`, `http`, `json`, `logging`, `queue`, `io`, `secrets`, `abc` and their
neighbours. This bites for a top-level module of a distribution, a loose script, or a scheduler DAG
file. Nested inside a package the name is only ever visible as `mypackage.types`, so `import types`
still resolves to the stdlib and there is nothing to shadow — there, name the module after its
contents.

## Module and Package Encapsulation

Python has no `private` keyword: encapsulation is a convention plus `__all__`, and it works only if
applied deliberately. Decide the public surface of every package **once**, write it down, and hide
everything else.

**The three levels of visibility**

| Level | How it is marked | Who may import it | What it guarantees |
|---|---|---|---|
| Public | listed in the package's `__init__.py` `__all__` | anyone | follows the deprecation rules |
| Package-internal | a module named `_name.py`, or an `_internal/` sub-package | only modules inside that package | may change in any release |
| Module-private | a name prefixed `_` inside a module | only that module | may change at any time |

**What the underscore actually does**: nothing at runtime except excluding the name from a star
import. Its value is entirely social and static — the linters flag imports of private names across
module boundaries. That is enough, provided the convention is followed consistently.

**When to encapsulate a module**

- **Always, for a package other code imports** — a shared kernel, an SDK, a library. Consumers must
  read one file and see everything they may rely on.
- **Whenever a module exists only to serve its siblings** — prefix it with `_` so nobody outside
  grows a dependency on it.
- **Whenever the implementation is expected to move** — the flat-façade pattern below makes the
  eventual split a non-event for callers.
- **Underscoring every module is not needed inside an application package** whose only consumer is
  itself, when layer boundaries are already enforced. There, contracts do the work and a prefix on
  two hundred modules is noise. This is a carve-out for the underscore, not for `__all__`: the
  `__init__.py` still declares the surface, because a layer contract enforces *direction* and says
  nothing about *which names* a neighbouring layer may use.

**How to hide a whole subsystem**

- **Name the private area `_internal/`, with the underscore.** That is what `pydantic` and `pip`
  ship. `internal/` without it is a trap: NumPy shipped `numpy/core/` documented as private but
  named public, downstream imported from it for years, and undoing that took a dedicated NEP,
  compatibility stubs and a lint rule to fix other people's code. A docstring saying "this is
  private" is not a boundary; the name is.
- **The underscore goes on the boundary once and is not repeated inside.** `pip/_internal/` contains
  plain `cli/`, `index/`, `models/`. PEP 8 says it outright: *"An interface is also internal if any
  containing namespace is internal."*
- **The private area's `__init__.py` is empty.** `pydantic/_internal/__init__.py` is zero bytes —
  internal code imports the module it needs directly. A façade declares a contract, and there is no
  contract to declare here.

**The flat public façade** — how the standard library, `pydantic` and `attrs` are built:

- Implementation lives in private modules: `_client.py`, `_models.py`, `_transport.py`.
- `__init__.py` imports the public names from them and lists exactly those in `__all__`.
- Consumers write one stable path regardless of which private module the name currently lives in.
  Deep paths are unsupported by construction.
- Internal code imports from the private modules directly — never through the package's own
  `__init__`, which would create a cycle and make module load order significant.

  ```python
  # acme_core/__init__.py — the whole public surface, and nothing else
  from ._identifiers import OrderId as OrderId, UserId as UserId
  from ._models import Order as Order, User as User
  from ._repository import UserRepository as UserRepository

  __all__ = ["UserRepository", "Order", "OrderId", "User", "UserId"]
  ```

**Rules**

- **`__all__` is a sorted list of string literals** — not a tuple, not computed, not appended to
  conditionally.
- **A name is either in `__all__` or private.** There is no third state: a public-looking name that
  is not exported is a promise nobody made and everybody will rely on.
- **`__init__.py` contains imports and `__all__` only** — no logic, no side effects, no
  configuration.
- **NEVER import a private name across a package boundary.** If another package needs it, it is not
  private: promote it deliberately, with the deprecation guarantees that implies. Copying it is
  worse.
- **Deep paths that must stay importable** (plugin entry points) are an explicit, documented part of
  the public surface, not an accident.
- **`py.typed` ships with every typed package**, or consumers get `Any` for the whole API.
- **Module-level `__getattr__` is the one sanctioned dynamic hook**: for lazily importing a heavy
  optional submodule, or for keeping a renamed name working while emitting a deprecation warning.
  Never for building an API at runtime — the surface must be readable statically.
- **A test asserts that `__all__` matches the intended surface**, so an accidental export fails.

## Imports and Dependencies

- **Import modules for modules, names for classes and functions.** Then call `invoices.issue(...)`
  or `issue_invoice(...)` — never a three-level attribute chain, which hides what is used.
- **Absolute imports.** Relative imports are allowed only within a single package for sibling
  modules, and never upward.
- **NEVER import inside a function**, with exactly three exceptions, each carrying a suppression and
  a comment naming the reason: breaking a genuine circular import, loading a heavy or optional
  implementation on demand, and a façade that exports implementations whose libraries are separate
  extras. Do not use function-level imports for generic "lazy loading" — restructure instead.
- **Annotations that would create a cycle or pull a heavy dependency go under `TYPE_CHECKING`.**
- **NEVER rename on import** except for community-standard aliases and to resolve an actual clash;
  never alias to shorten.
- **No side effects on import.** Importing a module must be free, idempotent and order-independent.
- **Never depend transitively on something you import.** Every direct dependency is declared, with a
  lower bound.
- **Never feature-detect with `try: import x`** in application code; declare the dependency. In
  libraries, isolate optional dependencies in one module with a clear error naming what to install.
- **Domain code imports the standard library and other domain modules only.** Frameworks, drivers
  and clients enter through adapters.

### Implementation-Specific Dependencies Live in the Implementation

When an interface has several implementations and each needs its own library, that library is
imported **only in the module of the implementation that uses it** — never in the interface module,
the factory, the package `__init__.py`, or anything above the implementation.

- **One implementation — one module — its own imports at the top of that module.**
- **The interface module imports nothing implementation-specific.** If it needs a type from a
  library for a signature, that is a leak — define a domain type or a `Protocol` instead.
- **The factory does not import all implementations at module top.** Doing so makes importing the
  package pull in every driver, so a service that only ever uses the local implementation still pays
  the import cost and must have the library installed. The dispatch mapping holds *local builders*,
  and each builder imports its own driver inside itself — the second permitted function-level
  import. For an open set of implementations, invert it: a registry each implementation module
  registers itself with, or entry points.
- **Optional libraries are optional extras**, and the implementation module is the only place that
  fails when the extra is missing. Convert the import failure into the package's own error, naming
  the extra to install.
- **A façade over per-extra modules moves the import into the function.** When the package exports
  its implementations by name — `from acme.instrumentation import instrument_fastapi` — the
  package's `__init__` executes *every* implementation module, and a consumer holding one extra
  gets `ImportError` on a library it never asked for. Two shapes work, and only these two:
  - **No façade**: `__init__` stays empty and consumers import the module they need
    (`acme.instrumentation.fastapi`). Imports stay at module top; nothing is lazy.
  - **Façade, and the library is imported inside the function that uses it.** The module then
    imports cleanly without its library, and the failure arrives to whoever called the function —
    with the extra named. This is the third permitted function-level import.

  Do not reach for a module-level `__getattr__` here: the checker cannot type names that arrive
  through it, and every call site loses its signature.
- **Tests for an implementation are skipped, not failed, when its library is absent.**
- **The same rule applies to implementation-specific settings**: they belong to that implementation,
  not to the shared settings root.

  ```python
  # WRONG — the package __init__ loads and requires every driver just to be imported
  from .local import LocalBlobStore
  from .s3 import S3BlobStore          # pulls the cloud SDK in with it

  def create_blob_store(kind: str) -> BlobStore: ...
  ```

  ```python
  # CORRECT — the contract knows nothing, and only the chosen driver is ever imported
  class BlobStore(Protocol):
      def put(self, key: str, data: bytes) -> None: ...
      def get(self, key: str) -> bytes: ...


  class _BlobStoreOptions(TypedDict):
      bucket: NotRequired[str]
      region: NotRequired[str]
      root: NotRequired[Path]


  type _Factory = Callable[..., BlobStore]


  # Each builder declares the options it uses and swallows the rest, so the dispatcher never
  # has to know the union of what its builders might want.
  def _s3(*, bucket: str, region: str, **_: object) -> BlobStore:
      from .s3 import S3BlobStore   # noqa: PLC0415  # optional extra, loaded on demand
      return S3BlobStore.create(bucket, region)


  def _local(*, root: Path, **_: object) -> BlobStore:
      from .local import LocalBlobStore   # noqa: PLC0415
      return LocalBlobStore(root)


  _FACTORY: Final[Mapping[BlobStoreKind, _Factory]] = MappingProxyType(
      {
          BlobStoreKind.S3: _s3,
          BlobStoreKind.LOCAL: _local,
      }
  )


  def create_blob_store(kind: BlobStoreKind, **options: Unpack[_BlobStoreOptions]) -> BlobStore:
      return _FACTORY[kind](**options)
  ```

  The mapping is built at import time out of *local* functions, so nothing heavy is loaded; the
  driver arrives only when the builder that needs it runs. Callers name concrete fields, never a
  settings object:

  ```python
  store = create_blob_store(
      settings.blob_store_kind,
      bucket=settings.s3_bucket,
      region=settings.s3_region,
      root=settings.blob_root,
  )
  ```

### Enforced Layer Boundaries

**Dependency direction is enforced by tooling, not by review vigilance.** Contracts live next to the
type-checker configuration and run beside it: a layered contract fixes the order of the layers, and
a forbidden contract keeps the domain free of frameworks, drivers and adapters.

- Higher layers depend on lower ones; the domain depends on nothing in the package.
- A boundary violation is fixed by moving code or inverting the dependency — a `Protocol` plus an
  adapter — **never** by adding the module to an allowlist. A contract exception needs the same
  justification as a type suppression.
- Ban the APIs that must never be used directly at the linter level, with a message naming the
  replacement.

## Composition Root and Dependency Injection

All object construction happens in **one place** — the composition root: the entry point for a
worker or CLI, the application factory for a service. Everywhere else, dependencies arrive through
the constructor or the function signature.

- **Classes never instantiate their collaborators.** A service receives its repository and its
  notifier; it never builds one, and never reads settings to decide which to build. The constructor
  only assigns.
- **The wiring is plain code**: build settings, build shared resources, build adapters, build
  services, hand them to the entry points. A DI framework is unnecessary until wiring is measured in
  hundreds of objects; if one is used, it is confined to the composition root.
- **Resource lifetime is owned by the root**: pools and clients are created once, passed down, and
  closed in reverse order on shutdown — an exit stack or the framework's lifespan hook, never
  `atexit`, never per-request construction of pooled resources.
- **No global singletons, no service locator.** A module-level connection or a globally reachable
  container is hidden global state: import-time side effects, un-fakeable tests, ordering bugs. The
  only module-level objects are constants and the logger.
- **Scopes are explicit**: application-scoped objects built once in the root; request-scoped objects
  built per request by an explicitly passed factory.
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
      settings = Settings()                     # fail fast
      with ExitStack() as resources:
          engine = resources.enter_context(managed_engine(settings.database_url))

          order_service = OrderService(
              repository=PostgresOrderRepository(engine),
              now=lambda: datetime.now(UTC),
          )
          run_consumer(order_service, settings)
  ```

## Constants and Configuration

- **No magic values.** Any literal with meaning beyond `0`, `1`, `""`, `None` is a named constant or
  an `Enum` member.
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
- **A cohesive group of parameters passed as one frozen value is a different thing, and it is
  encouraged.** `RetryPolicy(attempts, backoff, jitter)`, `PoolOptions(size, overflow, recycle)` —
  the callee uses all of it, and the type names a concept. What decides is cohesion, not the
  mechanism: a configuration root built out of frozen dataclasses is still a configuration root, and
  a parameter object validated at the boundary is still a parameter object. Three questions tell
  them apart — does the callee use essentially every field; is the name a concept (`RetryPolicy`)
  rather than an origin (`Settings`, `Config`, `Env`); could a test build it in one line from
  literals, with nothing read from the environment? Three yeses make it a value to pass; one no
  makes it the configuration root wearing a smaller name.
- **A dispatcher that forwards options is the exception, and it forwards them typed.** A factory
  that hands the same option bundle to whichever builder it selected takes `**options:
  Unpack[SomeOptions]`, with a `TypedDict` naming every field and marking the optional ones. Each
  builder then declares the fields it uses and swallows the rest. That keeps the call site naming
  concrete fields, keeps the checker able to reject a typo, and keeps the dispatcher from having to
  know the union of everything its builders might want.
- **Configuration is validated at startup, before serving.** A missing or malformed variable crashes
  the process immediately with a clear message — never a lazy read that fails on the first request
  hours later. Feature flags are typed fields, read once and injected, never queried ad hoc deep in
  the call stack.
- **Secrets never appear in code, defaults, or logs** — not even placeholder defaults.
- Units, currencies, time zones and formats are constants or types, never repeated literals.
- Regular expressions are compiled once at module level, with a name describing what they match.

## Transactions and Unit of Work

- **One use-case — one transaction.** The service method is the transaction boundary. Entry points
  do not manage transactions; repositories do not commit.
- **The Unit of Work owns the transaction**: a context manager that opens the session, exposes the
  repositories bound to it, commits on clean exit and rolls back on exception.
- **Explicit is the default**: the `with` is written in the service — not a decorator, not
  middleware that silently wraps everything. Implicit transactions hide their boundary and make
  two-transaction use-cases impossible to see.
- **Nothing slow or irreversible inside a transaction**: no HTTP calls, no message publishing, no
  mail while holding it. Side effects run after commit; if they must be atomic with the data, write
  an outbox row in the same transaction and publish separately.
- **Read-only paths don't open write transactions.**
- **Retries wrap the whole unit of work.** The use-case must be re-runnable from the start, which it
  is when side effects are after-commit.
- **Domain objects do not hold sessions**; a detached entity passed outward never lazy-loads.

## Database Access and Migrations

**Access**

- **The engine is built once** in the composition root, with an explicit pool size, liveness check
  and statement timeout; sessions are short-lived and request-scoped.
- **Every relationship is loaded explicitly.** Lazy loading is disabled so an N+1 is an error, not a
  slow page. Design as if it always raises.
- **ORM models are not domain models.** They map to tables and are converted to frozen domain
  objects at the repository boundary. Domain code never imports the ORM.
- **Repositories return and accept domain objects**; they contain query construction only — no
  business rules, no commits.
- **Bulk operations are bulk.** Looping single-row writes for thousands of rows is a bug.
- **Raw SQL is parameterized, always**, and is reserved for reports and migrations.
- **Column types are the specific ones**: timestamps with time zone, decimal for money, native UUID
  for ids — never a float for money, never text for typed data.
- **Indexes are part of the model** and are reviewed with the query that needs them, never added
  "just in case".

**Migrations**

- **One migration per logical schema change**, generated and then **read and edited** —
  autogeneration misses renames, server defaults and constraint changes.
- **Every migration has a working downgrade**; an irreversible change is split so the destructive
  step is its own, clearly named revision.
- **Schema migrations never contain data migrations.** A backfill is a separate revision or a
  one-off script: batched, bounded, idempotent, re-runnable after failure.
- **Migrations are backward compatible with the deployed code** — expand, migrate, contract. A
  migration that breaks the running version is an outage.
- **Revision messages are imperative and specific**, not `update` or `fix`.
- **No ORM models inside migrations**: use the migration DSL and inline table definitions, so a
  migration written today still runs after the model changes tomorrow.
- **The whole chain is exercised** against an empty database, up and back down, and a drift between
  models and migrations is a failure.
- **Long locks are planned**: concurrent index creation, batched backfills, type changes via a new
  column.

## External Calls: Timeouts, Retries, Idempotency

Every call that leaves the process — HTTP, database, queue, cache, DNS — follows the same
discipline:

- **A timeout is mandatory and explicit.** Client-level defaults set once in the composition root,
  overridden per call only with a named constant. A call with no timeout turns a dependency's outage
  into your own.
- **Retry only transient failures**: connect and read timeouts, rate limits, server errors,
  deadlocks, broker disconnects. **Never retry** business rejections, validation errors or auth
  failures — retrying a conflict is a loop, not resilience.
- **The adapter translates upstream errors into a transient and a permanent error type first**;
  retry policy then keys on the type, not on status-code checks scattered around.
- **Retries are bounded, exponential, and jittered.** Set the jitter explicitly rather than trusting
  a library default — a default measured in seconds can dwarf a backoff measured in milliseconds and
  silently flatten the curve.
- **Retry a write only if it is idempotent.** Carry an idempotency key when the API supports one;
  otherwise make the operation idempotent on your side or do not retry it.
- **Consumers are idempotent**: at-least-once delivery means every handler must tolerate the same
  message twice.
- **Budgets nest.** An operation retried inside a caller that also retries multiplies; the outermost
  boundary owns the total deadline. When in doubt, retry at one layer only — the adapter.
- **Fail fast when the dependency is down.** After repeated failures stop hammering and surface a
  clear unavailability error, so callers degrade deliberately instead of queueing timeouts.
- **Retrying is an adapter concern.** Services see one call that either succeeded or raised a final
  error; they never contain retry loops.

## Command-Line Interfaces

- **Never hand-parse arguments.** Use an argument parser whose declarations *are* the interface.
- **`main()` builds, `run()` executes**: the entry point constructs settings and the object graph,
  then calls a function that contains no construction.
- **Exit codes are the contract**: success, generic failure, usage error; further codes are named
  constants. Exit is called once, in `main()`, with the code returned by `run()` — never scattered
  through the code, never inside library functions.
- **stdout is the product, stderr is the conversation**: results go to stdout so they can be piped;
  logs, progress and errors go to stderr.
- **A dry-run mode for every command with side effects**; a verbosity flag mapped to log level; a
  machine-readable output mode where a human might not be the reader.
- **Subcommands are verbs, options are nouns**; boolean options are paired flags, never positional
  booleans.
- **Configuration precedence is fixed and documented**: explicit flag, then environment, then config
  file, then default. The CLI does not invent a fourth source.
- **Interrupts are graceful**: caught in `main()` only, cleanup runs, and no traceback is printed
  for them.
- **Long-running commands report progress**, are resumable where the work is batched, and never
  buffer all output until the end.
- **CLIs are tested through `run()`.** The argument layer contains no logic worth testing on its
  own.

## API Compatibility and Deprecation

Applies to anything code you do not control imports or calls.

- **`__all__` is the contract.** Anything not in it may change freely; anything in it follows the
  rules below. Keep the public surface as small as viable — every exported name is a promise.
- **Semantic versioning semantics**: breaking change → major; new capability → minor; fix → patch.
  "Breaking" includes removing or renaming an exported name, tightening accepted types, loosening
  returned types, changing defaults, reordering positional parameters, and raising a new exception
  type from an existing flow.
- **Deprecate, then remove — never surprise.** Emit a deprecation warning *and* mark the name so
  type checkers and IDEs surface it; state the replacement and the removal version in the message;
  keep the old path working for at least one minor release; remove only in a major.
- **Design for extension without breakage**: keyword-only parameters can be added freely — another
  reason for `*` in signatures. Returned objects grow fields, so callers must not destructure
  exhaustively.
- **Renames are re-exports first**: the old name lives on as a deprecated alias of the new one, not
  a copy.

## Performance

- **Measure before optimizing.** Any performance change references a measurement — a profile for
  CPU, an allocation profile for memory, a benchmark to pin the improvement. An optimization
  without a before-and-after number is refactoring risk with no proven benefit.
- **Optimize the algorithm, then the constants.** A quadratic membership scan beats any
  micro-tuning: set and dict lookups, precomputed indexes, and batching are where real wins live.
  N+1 query patterns are bugs, not tuning opportunities.
- **Stream, don't materialize**: generators and chunked reads for anything larger than
  memory-trivial; never build a list from a stream just to iterate it once.
- **`slots=True` on every dataclass** — and `__slots__` on hand-written classes with fixed
  attributes — as the default, not an optimization: less memory per instance, faster attribute
  access, and typo-attributes become errors. `slots` is about the *attribute set*, `frozen` about
  *mutability*; real immutability needs both. Skip slots only for classes needing dynamic
  attributes, multiple inheritance from slotted bases, framework classes that require `__dict__`,
  and cached-property users.
- **Caching is a contract, not a sprinkle.** Memoize only **pure** functions of hashable arguments,
  with an explicit bound — an unbounded cache is a leak. **Never on methods**: the cache keeps the
  instance alive and grows per instance; cache a module-level function, or use a cached property for
  a one-per-instance lazy value. Any cross-process cache states its invalidation rule in the design,
  or it is a stale-data bug scheduled for later.
- **Precompile and hoist**: compiled patterns at module level; no attribute chain or dict lookup
  repeated in a hot loop that a local would hoist.
- **Concurrency follows the workload**, and is measured before assuming parallelism helps — pool and
  pickling overhead is real.
- **Performance-sensitive paths are marked and tested** with a stated budget, so a regression fails
  a check instead of arriving as an incident.

## Security

- **Cryptographically secure randomness for anything capability-bearing** — tokens, salts, nonces,
  ids. Never a general-purpose random generator.
- **TLS verification stays on.** Never disable it "to make it work".
- **Passwords are hashed with a vetted adaptive algorithm**, never a fast hash and never a
  hand-rolled scheme. Secrets are compared in constant time, never with `==`.
- **Dependencies are scanned for known vulnerabilities**, and a finding blocks the upgrade path it came in on.
- **SQL is always parameterized** — including order-by clauses and table names, which are chosen
  from a whitelist of constants, never interpolated.
- **Subprocesses take an argument list, never a shell string.** Executable paths and arguments are
  validated, not concatenated from input.
- **Parse untrusted formats defensively**: safe loaders only, hardened XML, and no evaluation of
  untrusted input.
- **Path traversal**: any path derived from external input is resolved and checked to be contained
  within its base. Filenames from users are data — a sanitized display name plus a generated storage
  name, never used raw.
- **Server-side request forgery**: URLs from users are validated against an allowlist of schemes and
  hosts before fetching; redirects are re-validated; internal metadata ranges and loopback are
  blocked by default.
- **Every external input is bounded**: body size limits, pagination caps, collection length limits,
  decompression ratio limits. Validation includes *size*, not just shape.
- **Secrets come from the environment or a secret manager**, wrapped in a type that does not render
  them, never committed, and never present in URLs, logs or error messages.
- **Fail closed**: authorization lives in the service layer, not only at the transport edge; it
  denies by default, and an error inside the check denies rather than allows.

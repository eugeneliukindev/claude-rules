# Wiring: Composition Root, Configuration, Layers

Not loaded automatically — open it when writing an entry point, deciding where an object is built,
introducing a settings field, or arguing about which layer something belongs to.

## Composition Root and Dependency Injection

All object construction happens in **one place** — the composition root: the entry point for a
worker or CLI, the application factory for a service. Everywhere else, dependencies arrive through
the constructor or the function signature.

- **Classes never instantiate their collaborators.** A service receives its repository and its
  notifier; it never builds one, and never reads settings to decide which to build. The constructor
  only assigns.
- **The wiring is plain code**: build settings, build shared resources, build adapters, build
  services, hand them to the entry points. A DI framework is unnecessary until wiring is measured
  in hundreds of objects; if one is used, it is confined to the composition root.
- **Resource lifetime is owned by the root**: pools and clients are created once, passed down, and
  closed in reverse order on shutdown — an exit stack or the framework's lifespan hook, never
  `atexit`, never per-request construction of pooled resources.
- **No global singletons, no service locator.** A module-level connection or a globally reachable
  container is hidden global state: import-time side effects, un-fakeable tests, ordering bugs. The
  only module-level objects are constants and the logger.
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
  know the union of everything its builders might want.
- **Configuration is validated at startup, before serving.** A missing or malformed variable
  crashes the process immediately with a clear message — never a lazy read that fails on the first
  request hours later. Feature flags are typed fields, read once and injected, never queried ad hoc
  deep in the call stack.
- **Secrets never appear in code, defaults, or logs** — not even placeholder defaults.
- Units, currencies, time zones and formats are constants or types, never repeated literals.
- Regular expressions are compiled once at module level, with a name describing what they match.

## Enforced Layer Boundaries

**Dependency direction is enforced by tooling, not by review vigilance.** Contracts live next to
the type-checker configuration and run beside it: a layered contract fixes the order of the layers,
and a forbidden contract keeps the domain free of frameworks, drivers and adapters.

- Higher layers depend on lower ones; the domain depends on nothing in the package.
- **Domain code imports the standard library and other domain modules only.** Frameworks, drivers
  and clients enter through adapters.
- A boundary violation is fixed by moving code or inverting the dependency — a contract plus an
  adapter — **never** by adding the module to an allowlist. A contract exception needs the same
  justification as a type suppression.
- Ban the APIs that must never be used directly at the linter level, with a message naming the
  replacement.

How directories are named and nested is a project decision, not a general rule: it follows the
domain, the team and the deployment shape, and a layout copied from elsewhere is a layout nobody
owns. What is fixed is which way dependencies point, what a package promises, where construction
happens, and that a contract and its implementations share one directory (`core.md`).

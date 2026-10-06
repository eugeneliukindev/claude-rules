---
name: go-wiring
description: >-
  Go composition root, configuration and layering: main as a thin shell over run, all construction
  in one place, dependencies as struct fields set by a constructor, resource lifetime owned by the
  root and closed in reverse, typed configuration loaded and validated once and passed as fields,
  constants versus configuration, functional options versus an options struct, and layer
  boundaries enforced by depguard. Use when writing func main, a constructor, an application
  struct, a config field, removing a package-level global or init, or arguing about which layer
  code belongs to.
---

# Wiring: Composition Root, Configuration, Layers

## Composition Root

All construction happens in **one place**: the function `run` hands the parsed settings to, in
the `main` package. The shape of `main` and `run` — the context, the arguments, the streams, the
exit code — is in `go-cli`; this is what happens inside. Everywhere else, dependencies arrive as
constructor arguments and stay as unexported fields.

- **Types never build their collaborators.** A service receives its repository and its notifier
  in `NewService`; it never opens a connection, and never reads configuration to decide what to
  build. The constructor assigns and validates; it does not do I/O.
- **The wiring is plain code**: load configuration, open shared resources, build adapters, build
  services, start the servers. A DI framework is unnecessary until the graph is measured in
  hundreds of objects; if one is used, it stays inside the composition root.
- **No package-level singletons** (`packages.md`): a package-level `*sql.DB` is a dependency
  nothing in a signature admits, and tests that cannot run in parallel.
- **Tests get their own root**: a helper that builds the graph with fakes and a fixed clock.

```go
// WRONG — a package-level pool opened at import, and a service that finds it by itself
var db = mustOpen(os.Getenv("DATABASE_URL"))

func NewOrderService() *OrderService {
	return &OrderService{repository: postgres.NewOrderRepository(db)}
}

// CORRECT — the root opens, passes, and closes
func serve(ctx context.Context, settings serverSettings) error {
	db, err := sql.Open("pgx", settings.databaseURL)
	if err != nil {
		return fmt.Errorf("open database: %w", err)
	}
	defer db.Close()

	orders := NewOrderService(postgres.NewOrderRepository(db), time.Now)
	return listenAndServe(ctx, settings.listenAddress, NewOrderHandler(orders))
}
```

## Resource Lifetime

The root acquires, so the root releases; everything below borrows.

- **`defer` the release on the line after acquisition succeeds**, in the function that owns it.
  Defers run in reverse, so resources close in the reverse of the order they were opened — the
  server stops before the pool it uses is closed.
- **A constructor that acquires returns a `Close` with it**, or a type with a `Close` method. A
  value that owns a goroutine owns its shutdown too: `Close` stops it and waits.
- **The error from closing a writer is returned, not deferred away.** For a file being written, a
  transaction, a buffered writer, close is where the data is committed:

  ```go
  defer func() { err = errors.Join(err, f.Close()) }()
  ```
- **Shutdown is ordered and bounded**: stop accepting work, drain with a deadline
  (`server.Shutdown(ctx)` with `context.WithTimeout`), then close stores. `go-concurrency` has
  the pattern.

## Constants and Configuration

- **Constants live next to their single user**; one shared by several packages lives in the
  package that owns the concept, never in a `constants` package.
- **Configuration is not constants.** Anything that varies by environment is a field of one typed
  settings struct, loaded once in `run` from flags and the environment, **validated before
  anything starts**, and passed down — never `os.Getenv` scattered through the code, never a
  package-level `Config` everything imports.
- **Pass fields, never the configuration root.** `NewClient(baseURL string, timeout
  time.Duration)` or a cohesive `ClientOptions` — not `NewClient(cfg *Config)`. The root struct is
  a namespace of unrelated groups: the signature stops being a dependency list, and a test has to
  build everything to construct one thing. Unpacking happens once, in the root, where the
  verbosity is the point.
- **A cohesive group of parameters is one struct, and that is encouraged.** `RetryPolicy{Attempts,
  BaseDelay, MaxDelay}` — the callee uses all of it, and its name is a concept, not an origin. Three
  questions tell it from a config root in disguise: does the callee use essentially every field;
  is the name a concept rather than `Config`, `Settings`, `Env`; could a test build it in one line
  from literals?
- **Functional options are for a published constructor with many optional settings** —
  `NewServer(addr, WithTLS(cert), WithLogger(l))` — where adding an option must not break callers.
  Inside an application an options struct is simpler, shows every setting in one place, and its
  zero value documents the defaults.
- **Secrets never appear in code or defaults** — not even a placeholder — and a settings type with
  a secret field redacts itself in logs (`errors.md`).
- **Regular expressions are compiled once, at package level**, with a name saying what they match:
  `var semverPattern = regexp.MustCompile(…)`.

## Enforced Layer Boundaries

**Dependency direction is enforced by a linter, not by review vigilance.** Go already refuses import
cycles; what it does not refuse is the domain importing the database driver, or one notifier
importing another.

- **`depguard` lists, per set of files, the imports that are denied** — the domain packages may not
  import `database/sql`, `net/http` or any driver; an implementation package may not import its
  siblings. Every allowed exception carries its reason in the configuration.
- **`internal/` is the boundary Go enforces by itself**: nothing outside the parent directory can
  import it. Use the nesting — `orders/internal/pricing` is invisible even to `payments`.
- **The domain imports the standard library and other domain packages only.** Frameworks, drivers
  and clients enter through adapters that implement interfaces the domain declares.
- **A boundary violation is fixed by moving code or inverting the dependency** — an interface plus
  an adapter — never by adding the import to an allowlist without a reason on the line.

How directories are named and nested is a project decision: it follows the domain, the team and
the deployment. A layout copied from a template is a layout nobody owns. What is fixed is which
way dependencies point, where construction happens, and that `main` stays thin.

---
name: go-wiring
description: >-
  Go composition root and configuration: main as a thin shell over run, all construction in one
  place, dependencies as struct fields set by a constructor, resource lifetime owned by the root and
  closed in reverse, typed configuration loaded and validated once and passed as fields, constants
  versus configuration, functional options versus an options struct. Use when writing func main, a
  constructor, an application struct, a config field, or removing a package-level global or init.
paths:
  - "**/*.go"
  - "**/go.mod"
---

# Wiring: Composition Root, Configuration

Which package may import which is `go-layers`.

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
func serve(ctx context.Context, settings serverSettings) (err error) {
	db, err := sql.Open("pgx", settings.databaseURL)
	if err != nil {
		return fmt.Errorf("open database: %w", err)
	}
	defer func() {
		if closeErr := db.Close(); closeErr != nil {
			err = errors.Join(err, fmt.Errorf("close database: %w", closeErr))
		}
	}()

	orders := NewOrderService(postgres.NewOrderRepository(db), time.Now)
	return listenAndServe(ctx, settings.listenAddress, NewOrderHandler(orders))
}
```

## Resource Lifetime

The root acquires, so the root releases; everything below borrows.

- **`defer` the release on the line after acquisition succeeds**, in the function that owns it.
  Defers run in reverse, so resources close in the reverse of the order they were opened — the
  server stops before the pool it uses is closed.

  ```go
  // WRONG — a failed dial returns with the pool still open, and so does any panic
  func run(ctx context.Context, settings appSettings) error {
  	db, err := sql.Open("pgx", settings.databaseURL)
  	if err != nil {
  		return fmt.Errorf("open database: %w", err)
  	}
  	queue, err := dialQueue(ctx, settings.queueAddress)
  	if err != nil {
  		return fmt.Errorf("dial queue: %w", err)
  	}

  	err = consumeOrders(ctx, queue, db)
  	return errors.Join(err, queue.Close(), db.Close())
  }

  // CORRECT — each release deferred on the line after its acquisition; defers run in reverse
  func run(ctx context.Context, settings appSettings) (err error) {
  	db, err := sql.Open("pgx", settings.databaseURL)
  	if err != nil {
  		return fmt.Errorf("open database: %w", err)
  	}
  	defer func() {
  		if closeErr := db.Close(); closeErr != nil {
  			err = errors.Join(err, fmt.Errorf("close database: %w", closeErr))
  		}
  	}()

  	queue, err := dialQueue(ctx, settings.queueAddress)
  	if err != nil {
  		return fmt.Errorf("dial queue: %w", err)
  	}
  	defer func() {
  		if closeErr := queue.Close(); closeErr != nil {
  			err = errors.Join(err, fmt.Errorf("close queue: %w", closeErr))
  		}
  	}()

  	return consumeOrders(ctx, queue, db)
  }
  ```
- **A constructor that acquires returns a `Close` with it**, or a type with a `Close` method. A
  value that owns a goroutine owns its shutdown too: `Close` stops it and waits.
- **The error from closing a writer is returned, not deferred away.** For a file being written, a
  transaction, a buffered writer, close is where the data is committed:

  ```go
  // WRONG — Close writes the buffered data and the gzip footer; when that write fails, the
  // deferred call discards the error and the caller gets a truncated archive and nil
  func compressReport(w io.Writer, report []byte) error {
  	zw := gzip.NewWriter(w)
  	defer zw.Close()

  	if _, err := zw.Write(report); err != nil {
  		return fmt.Errorf("compress report: %w", err)
  	}
  	return nil
  }

  // CORRECT — the named result collects the error from Close, wrapped with what was closing
  func compressReport(w io.Writer, report []byte) (err error) {
  	zw := gzip.NewWriter(w)
  	defer func() {
  		if closeErr := zw.Close(); closeErr != nil {
  			err = errors.Join(err, fmt.Errorf("close gzip writer: %w", closeErr))
  		}
  	}()

  	if _, err := zw.Write(report); err != nil {
  		return fmt.Errorf("compress report: %w", err)
  	}
  	return nil
  }
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

  ```go
  // WRONG — the whole configuration for one client: the signature hides what it reads, and a
  // test must fill every section to build it
  func NewPaymentClient(settings *Settings) *PaymentClient

  // CORRECT — exactly what it uses; the root unpacks settings.Payments once
  func NewPaymentClient(baseURL string, timeout time.Duration) *PaymentClient
  ```
- **A cohesive group of parameters is one struct, and that is encouraged.** `RetryPolicy{Attempts,
  BaseDelay, MaxDelay}` — the callee uses all of it, and its name is a concept, not an origin. Three
  questions tell it from a config root in disguise: does the callee use essentially every field;
  is the name a concept rather than `Config`, `Settings`, `Env`; could a test build it in one line
  from literals?
- **Functional options are for a published constructor with many optional settings** —
  `NewServer(addr, WithTLS(cert), WithLogger(l))` — where adding an option must not break callers.
  Inside an application an options struct is simpler, shows every setting in one place, and its
  zero value documents the defaults.

  ```go
  // WRONG — inside an application: a type and a closure per setting, and the defaults are
  // nowhere in sight
  type WorkerOption func(*Worker)

  func WithBatchSize(size int) WorkerOption {
  	return func(w *Worker) { w.batchSize = size }
  }

  func WithPollInterval(interval time.Duration) WorkerOption {
  	return func(w *Worker) { w.pollInterval = interval }
  }

  func NewWorker(queue Queue, options ...WorkerOption) *Worker

  // CORRECT — one struct shows every setting, and its zero value is the default
  type WorkerOptions struct {
  	BatchSize    int           // zero means defaultBatchSize
  	PollInterval time.Duration // zero means defaultPollInterval
  }

  func NewWorker(queue Queue, options WorkerOptions) *Worker
  ```
- **Secrets never appear in code or defaults** — not even a placeholder — and a settings type with
  a secret field redacts itself in logs (`logging.md`).
- **Regular expressions are compiled once, at package level**, with a name saying what they match:
  `var semverPattern = regexp.MustCompile(…)`.

  ```go
  // WRONG — the pattern is compiled again on every call
  func isSemver(version string) bool {
  	return regexp.MustCompile(`^v\d+\.\d+\.\d+$`).MatchString(version)
  }

  // CORRECT — compiled once, and named for what it matches
  var semverPattern = regexp.MustCompile(`^v\d+\.\d+\.\d+$`)

  func isSemver(version string) bool {
  	return semverPattern.MatchString(version)
  }
  ```

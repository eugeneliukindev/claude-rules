---
name: go-concurrency
description: >-
  Go concurrency: every goroutine with an owner that waits for it and a way to stop it, context
  cancellation and deadlines, errgroup for structured fan-out with a limit, sync.WaitGroup.Go,
  channels versus mutexes, channel ownership and closing, bounded queues and backpressure, timers,
  data races and atomics, sync.Once and OnceValue, graceful shutdown with signal.NotifyContext,
  goroutine leaks, and testing concurrent code with testing/synctest. Use when Go code has a go
  statement, a channel, a select, a sync or sync/atomic type, errgroup, a worker pool, a ticker,
  or a server that must shut down cleanly.
---

# Concurrency

## Every Goroutine Has an Owner

**A `go` statement is a promise to answer two questions: who waits for it, and what makes it
stop.** A goroutine with no answer is a leak — it holds its stack, everything it references and
often a connection, and nothing reports it until memory runs out.

- **The function that starts goroutines waits for them before it returns**, unless it hands that
  duty to a value whose `Close` does the waiting. Concurrency is an implementation detail: callers
  of a synchronous-looking API never inherit a goroutine.
- **Every goroutine watches a `ctx` or a channel that its owner closes.** A blocking send, receive
  or call inside it takes the same `ctx` — a goroutine blocked on a send nobody will receive is the
  most common leak there is.
- **`errgroup.WithContext` is the default for related work that can fail**: the first error
  cancels the others, and `Wait` returns it. `sync.WaitGroup` with `wg.Go(f)` is for work that
  cannot fail or reports through its own channel — in a test that uses testify, `wg.Add(1)`, `go`
  and `defer wg.Done()` instead, which `testifylint` can read (`go-testify`).
- **A panic in a goroutine kills the process**; no caller can recover it. Code that must survive a
  panicking task — a server's request handler does this for you — recovers inside the goroutine
  and turns it into an error.

```go
// WRONG — nothing waits: an error is lost, and a slow fetch outlives the request that wanted it
for _, id := range ids {
	go func() {
		if err := c.refresh(ctx, id); err != nil {
			c.logger.ErrorContext(ctx, "refresh failed", "id", id, "error", err)
		}
	}()
}
return nil

// CORRECT — the group owns them, bounds them, and returns the first failure after all have stopped
group, ctx := errgroup.WithContext(ctx)
group.SetLimit(maxConcurrentRefreshes)
for _, id := range ids {
	group.Go(func() error {
		return c.refresh(ctx, id)
	})
}
return group.Wait()
```

## Bounded, Always

- **Fan-out has a limit**: `group.SetLimit(n)`, a fixed pool of workers reading one channel, or a
  `semaphore.Weighted`. One goroutine per input item is unbounded the day the input is.
- **A queue has a capacity and a policy when full** — block the producer (backpressure), drop with
  a counter, or reject with an error. An unbuffered or small buffered channel is the policy
  "block"; a huge buffer is the same policy with the failure postponed and hidden.

```go
// WRONG — p.events has a buffer of 100 000: "block", postponed until that many sit in memory
func (p *Publisher) Enqueue(event Event) {
	p.events <- event
}

// CORRECT — a buffer of 1 and a stated policy: when the consumer is behind, drop and count
func (p *Publisher) Enqueue(event Event) {
	select {
	case p.events <- event:
	default:
		p.dropped.Add(1)
	}
}
```

- **Buffer sizes are 0 or 1 unless a number is justified** — by a measured burst, or by the count
  of senders that must never block. A buffer that "makes it faster" usually hides a race.

## Channels or a Mutex

- **A mutex protects state; a channel transfers ownership.** A counter, a cache, a map read by many
  goroutines — `sync.Mutex` beside the fields it guards. Handing work to a worker, streaming
  results, signalling "done" — a channel.
- **The sender closes, never the receiver**, and exactly one sender closes. Several senders close
  through their owner after `wg.Wait()`. Closing is a broadcast — "no more values" — not a resource
  release; an unclosed channel nobody references is collected.

```go
// WRONG — every worker closes results when it finishes: the second close panics
for range workers {
	wg.Go(func() {
		r.work(ctx, requests, results)
		close(results)
	})
}

// CORRECT — the owner closes once, after the last sender has returned
for range workers {
	wg.Go(func() {
		r.work(ctx, requests, results)
	})
}
go func() {
	wg.Wait()
	close(results)
}()
```

- **A function's channel parameters state their direction**: `requests <-chan ResizeRequest`,
  `thumbnails chan<- Thumbnail`. The compiler then enforces who may send and who may close.
- **`sync.Mutex` is a named field above the fields it guards** (`types.md`). Hold it for the shortest region, never across I/O or a call into unknown code, and never
  copy a struct containing one (`go vet` `copylocks`).

```go
// WRONG — the lock is held across the network call: every reader waits for the slowest fetch
c.mu.Lock()
defer c.mu.Unlock()
if price, ok := c.priceBySKU[sku]; ok {
	return price, nil
}
price, err := c.supplier.FetchPrice(ctx, sku)
if err != nil {
	return 0, fmt.Errorf("price %s: %w", sku, err)
}
c.priceBySKU[sku] = price
return price, nil

// CORRECT — locked to read and to store, never while the fetch is in flight
c.mu.Lock()
price, ok := c.priceBySKU[sku]
c.mu.Unlock()
if ok {
	return price, nil
}
price, err := c.supplier.FetchPrice(ctx, sku)
if err != nil {
	return 0, fmt.Errorf("price %s: %w", sku, err)
}
c.mu.Lock()
c.priceBySKU[sku] = price
c.mu.Unlock()
return price, nil
```

Two callers may both miss and both fetch; where that matters, `golang.org/x/sync/singleflight`
merges them — still without holding the lock.

- **`sync/atomic` types for a single word** — `atomic.Int64`, `atomic.Bool`, `atomic.Pointer[T]` —
  never the function forms on a bare `int64`. Two related atomics are a race between them; that is
  a mutex.

```go
// WRONG — the function form on a bare int64: one plain read of processed elsewhere is a race
type Stats struct {
	processed int64
}

func (s *Stats) RecordProcessed() {
	atomic.AddInt64(&s.processed, 1)
}

// CORRECT — atomic.Int64 offers no way to read or write it non-atomically
type Stats struct {
	processed atomic.Int64
}

func (s *Stats) RecordProcessed() {
	s.processed.Add(1)
}
```

- **`sync.OnceValue` and `sync.OnceValues` for lazy, once-only initialisation** that returns a
  value and an error; a hand-rolled check-then-set is a race.

```go
// WRONG — two requests both see nil and both parse; the race detector reports the write
func (r *Renderer) templates() (*template.Template, error) {
	if r.parsed == nil {
		parsed, err := template.ParseFS(r.files, "*.html")
		if err != nil {
			return nil, fmt.Errorf("parse templates: %w", err)
		}
		r.parsed = parsed
	}
	return r.parsed, nil
}

// CORRECT — parsed once, by whichever call comes first; every other call waits for its result
func NewRenderer(files fs.FS) *Renderer {
	return &Renderer{templates: sync.OnceValues(func() (*template.Template, error) {
		parsed, err := template.ParseFS(files, "*.html")
		if err != nil {
			return nil, fmt.Errorf("parse templates: %w", err)
		}
		return parsed, nil
	})}
}
```

## Context, Cancellation, Deadlines

- **Cancellation flows down, never up.** A function derives a child context for its own deadline
  and always calls the `cancel` it got — `defer cancel()` on the next line; `go vet` `lostcancel`
  reports the one forgotten.
- **Stop at `ctx.Done()` in every loop that blocks**, and return `ctx.Err()` — or
  `context.Cause(ctx)` where a cause was set — so the caller can tell cancellation from failure.
- **`select` on `ctx.Done()` beside every send and receive** that could block forever.
- **Work that must outlive the request** — an audit write after the response — runs on
  `context.WithoutCancel(ctx)`, which keeps the values and drops the cancellation, with its own
  timeout. Never `context.Background()`, which also drops the trace.

```go
// WRONG — Background drops the trace and the request ID along with the cancellation
auditCtx, cancel := context.WithTimeout(context.Background(), auditTimeout)

// CORRECT — the request's values stay; only its cancellation is dropped
auditCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), auditTimeout)
```

```go
func (r *Resizer) run(ctx context.Context, requests <-chan ResizeRequest, thumbnails chan<- Thumbnail) error {
	for {
		select {
		case <-ctx.Done():
			return context.Cause(ctx)
		case request, ok := <-requests:
			if !ok {
				return nil
			}
			thumbnail := r.resize(ctx, request)
			select {
			case thumbnails <- thumbnail:
			case <-ctx.Done():
				return context.Cause(ctx)
			}
		}
	}
}
```

## Timers

- **`time.After` in a loop is fine since Go 1.23** — an unreferenced timer is collected — but a
  `time.NewTimer` reused with `Reset` states the intent and allocates once.
- **A `time.Ticker` is stopped** with `defer ticker.Stop()`; ticks do not queue, so a slow loop
  sees fewer ticks, never a burst.
- **A deadline is a `context.WithTimeout`**, not a `select` on `time.After` — the context
  propagates to every call below, the timer does not.

## Graceful Shutdown

```go
ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
defer stop()

group, ctx := errgroup.WithContext(ctx)
group.Go(func() error {
	if err := server.ListenAndServe(); !errors.Is(err, http.ErrServerClosed) {
		return err
	}
	return nil
})
group.Go(func() error {
	<-ctx.Done()
	stop()
	shutdownCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), shutdownTimeout)
	defer cancel()
	return server.Shutdown(shutdownCtx)
})
return group.Wait()
```

Stop accepting, drain with a deadline shorter than the orchestrator's kill timeout, then close
what the drained work was using. Calling `stop` as soon as the signal arrives restores the default
handling, so a second Ctrl-C kills a shutdown that hangs.

## Races

- **`go test -race` runs in CI on every package**, and a race report is a bug, never a flake. The
  detector finds only races that execute, so tests exercise the concurrent paths.
- **A loop variable is per-iteration since Go 1.22**: the `id := id` copy before a closure is dead
  code, and `go fix` removes it.

## Leaks

- **Leaks are found by the `goroutineleak` profile** (Go 1.27, `/debug/pprof/goroutineleak`) in a
  running service, and by asserting in tests that the goroutine count returns to its baseline —
  or with `testing/synctest`, which waits for every goroutine in the bubble to exit and fails the
  test when they deadlock instead.

## Testing Concurrent Code

`synctest.Test(t, func(t *testing.T) { … })` runs the function in a bubble with a fake clock that
advances only when every goroutine in it is blocked. `time.Sleep(time.Hour)` returns instantly and
deterministically, `synctest.Wait()` waits until everything else is blocked, and on Go 1.27
`httptest.NewTestServer` gives the bubble an in-memory network. Prefer it to real sleeps and
polling: a test that sleeps is slow when it passes and flaky when the machine is busy.

```go
// WRONG — every run waits two real seconds, and a one-minute timeout would make it a minute
func TestQuoteGivesUpAfterTimeout(t *testing.T) {
	quoter := NewQuoter(blockingSupplier{}, 2*time.Second)

	_, err := quoter.Quote(t.Context(), "sku-1")

	if !errors.Is(err, context.DeadlineExceeded) {
		t.Errorf("Quote() error = %v, want %v", err, context.DeadlineExceeded)
	}
}

// CORRECT — the bubble's clock jumps to the deadline as soon as every goroutine is blocked
func TestQuoteGivesUpAfterTimeout(t *testing.T) {
	synctest.Test(t, func(t *testing.T) {
		quoter := NewQuoter(blockingSupplier{}, 2*time.Second)

		_, err := quoter.Quote(t.Context(), "sku-1")

		if !errors.Is(err, context.DeadlineExceeded) {
			t.Errorf("Quote() error = %v, want %v", err, context.DeadlineExceeded)
		}
	})
}
```

`blockingSupplier` is a fake whose `FetchPrice` waits for `<-ctx.Done()` and returns `ctx.Err()`.

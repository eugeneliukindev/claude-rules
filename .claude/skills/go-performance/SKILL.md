---
name: go-performance
description: >-
  Go performance work, measure first: benchmarks with b.Loop and benchstat, CPU and allocation
  profiles with pprof, the execution tracer, escape analysis with -gcflags=-m, fixing the
  algorithm before the constants, preallocating slices and maps, strings.Builder and the Append
  form, sync.Pool and its traps, profile-guided optimization with default.pgo, GOMAXPROCS and
  GOMEMLIMIT in containers, and pinning a budget with a test. Use when Go code is slow or must be
  sped up, when asked to optimize, profile or benchmark it, when writing a Benchmark function, or
  when reviewing a proposed optimization.
---

# Performance

## Measure First

**No optimization without a number before and a number after.** Intuition about what is slow in Go
is wrong most of the time — the allocation you worried about is on the stack, the loop you
rewrote was 2% of the profile, and the time went to a lock or a syscall.

1. **A benchmark reproduces the slow case** — with realistic sizes, not ten elements.
2. **A profile says where the time goes**: `go test -bench=Encode -cpuprofile=cpu.out
   -memprofile=mem.out`, then `go tool pprof -http=: cpu.out`. In a running service,
   `net/http/pprof` on an internal port — never on the public listener.
3. **The change is made where the profile points**, and nowhere else.
4. **`benchstat` compares the runs**: `go test -bench=. -count=10 > old.txt`, the change, the same
   into `new.txt`, then `benchstat old.txt new.txt`. A difference inside the noise is no
   difference, and one run of each is anecdote.

## Benchmarks

```go
// WRONG — b.N reruns the whole function, so newOrder is timed with every run of the work
func BenchmarkEncodeOrder(b *testing.B) {
	order := newOrder(b, withLines(100))

	for range b.N {
		if _, err := EncodeOrder(order); err != nil {
			b.Fatal(err)
		}
	}
}

// CORRECT — b.Loop starts the timer at its first call, and keeps the loop body alive
func BenchmarkEncodeOrder(b *testing.B) {
	order := newOrder(b, withLines(100))

	for b.Loop() {
		if _, err := EncodeOrder(order); err != nil {
			b.Fatal(err)
		}
	}
}
```

- **`for b.Loop()`** (Go 1.24), not `for range b.N`: setup above the loop is excluded from the
  timing automatically, and the loop body is kept alive so the compiler cannot delete the work
  being measured.
- **`b.ReportAllocs()` or `-benchmem`** — allocations per operation are often the number that
  moves, and the cheaper one to fix.
- **Sub-benchmarks for sizes**: `b.Run(fmt.Sprintf("lines=%d", n), …)` over 10, 1 000, 100 000,
  so a quadratic step shows as a curve rather than one slow number.

## The Order of Fixes

1. **The algorithm** — a map lookup instead of a scan inside a loop, a sort once instead of a
   search per item, one query instead of N. Nothing below competes with an O(n²) that became O(n).

```go
// WRONG — a scan of every customer per order: 10 000 of each is 100 million comparisons
for _, order := range orders {
	i := slices.IndexFunc(customers, func(c Customer) bool { return c.ID == order.CustomerID })
	if i < 0 {
		return nil, fmt.Errorf("invoice order %s: customer %s: %w",
			order.ID, order.CustomerID, ErrNotFound)
	}
	invoices = append(invoices, newInvoice(order, customers[i]))
}

// CORRECT — the customers indexed once, then one lookup per order
customerByID := make(map[CustomerID]Customer, len(customers))
for _, customer := range customers {
	customerByID[customer.ID] = customer
}
for _, order := range orders {
	customer, ok := customerByID[order.CustomerID]
	if !ok {
		return nil, fmt.Errorf("invoice order %s: customer %s: %w",
			order.ID, order.CustomerID, ErrNotFound)
	}
	invoices = append(invoices, newInvoice(order, customer))
}
```

2. **I/O** — batching, buffering (`bufio.Writer` around a file or a socket), fewer round trips,
   streaming instead of reading everything into memory first.
3. **Allocations** — in a hot path, each one is GC work later:
   - **Preallocate** when the size is known: `make([]Line, 0, len(items))`, `make(map[K]V, n)`.

```go
// WRONG — the slice outgrows its array again and again, copying everything each time
var lines []Line
for _, item := range items {
	lines = append(lines, toLine(item))
}

// CORRECT — one allocation of the size already known
lines := make([]Line, 0, len(items))
for _, item := range items {
	lines = append(lines, toLine(item))
}
```

   - **Build strings with `strings.Builder`** and the `Append` functions (`strconv.AppendInt`)
     rather than `+` in a loop or `fmt.Sprintf` for a number.

```go
// WRONG — each += copies the report so far, and Sprintf allocates for every line
var report string
for _, order := range orders {
	report += fmt.Sprintf("%s %d\n", order.ID, order.TotalCents)
}

// CORRECT — one growing buffer, and the number appended in place
report := make([]byte, 0, len(orders)*32)
for _, order := range orders {
	report = append(report, order.ID...)
	report = append(report, ' ')
	report = strconv.AppendInt(report, int64(order.TotalCents), 10)
	report = append(report, '\n')
}
```

   - **Avoid converting between `string` and `[]byte`** back and forth in a loop; pick one.
   - **Pointers that escape** move values to the heap — `go build -gcflags=-m` says which and why.
4. **Contention** — a `sync.Mutex` everyone waits on shows in the mutex and block profiles, not
   the CPU profile. Shard the state, or hold the lock for less.
5. **The constants** — only now, and only with a benchmark guarding the change.

## Tools and Their Traps

- **`sync.Pool` is for short-lived, same-sized buffers on a measured hot path.** Reset what you get,
  return only what you got, never pool an object something still references, and never pool a
  buffer that grew huge once — it keeps the memory. The GC empties the pool, so it is a cache,
  never a store.

```go
// WRONG — the buffer arrives holding the last order's bytes, and one that grew for a huge order
// keeps all that memory in the pool
buf, ok := e.buffers.Get().(*bytes.Buffer)
if !ok {
	buf = new(bytes.Buffer)
}
defer e.buffers.Put(buf)

// CORRECT — reset on the way in, and an outsized buffer is left to the GC
buf, ok := e.buffers.Get().(*bytes.Buffer)
if !ok {
	buf = new(bytes.Buffer)
}
buf.Reset()
defer func() {
	if buf.Cap() <= maxPooledBufferBytes {
		e.buffers.Put(buf)
	}
}()
```

`e.buffers` is a `sync.Pool` field with no `New`, so an empty pool returns `nil` and the failed
assertion allocates.
- **Profile-guided optimization**: a CPU profile from production saved as `default.pgo` in the main
  package's directory is picked up by `go build` automatically, typically a few percent for free.
  Refresh it when the hot paths change.
- **The execution tracer** (`go test -trace`, or `runtime/trace.FlightRecorder` in a service) shows
  what the CPU profile cannot: goroutines waiting on each other, GC pauses, scheduler latency.
- **Containers**: the runtime sets `GOMAXPROCS` from the cgroup CPU limit (Go 1.25), so a manual
  setting is now usually wrong. `GOMEMLIMIT` set to ~90% of the memory limit lets the GC work
  harder before the kernel kills the process.
- **`unsafe` and assembly are not optimizations, they are maintenance costs** — justified only by a
  benchmark, a comment linking it, and a test that runs the portable fallback.

## Pin the Budget

A speedup nobody guards is undone by the next refactor. Keep the benchmark next to the code, run
it in CI with `benchstat` against the main branch where the project can afford the time, and for
allocation counts — which are deterministic — assert them in an ordinary test:

```go
func TestEncodeOrderAllocations(t *testing.T) {
	order := newOrder(t, withLines(100))

	allocations := testing.AllocsPerRun(100, func() {
		_, _ = EncodeOrder(order) // only the count matters here; the output is tested elsewhere
	})

	if allocations > maxEncodeAllocations {
		t.Errorf("EncodeOrder allocates %v times per call, want at most %d", allocations, maxEncodeAllocations)
	}
}
```

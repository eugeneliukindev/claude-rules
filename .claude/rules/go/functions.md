---
paths:
  - "**/*.go"
---

# Go — Functions

- **Does one thing** — "and" in its description means split it. SRP is a different rule.
- **`ctx context.Context` is the first parameter of anything that blocks, does I/O or calls
  something that does.** Never stored in a struct, never `nil` — `context.TODO()` marks the call
  site still to be plumbed. A function that cannot be cancelled is a goroutine that cannot be
  stopped.
- **Group related parameters into a struct** rather than growing the signature — the fourth
  `string` in a row is a swapped call waiting to happen.

## Extraction Must Pay for Itself

A helper's name and signature are an **interface**; it pays only by hiding more than it exposes.

**Extract when at least one is true:**

1. **Real reuse** — two or more call sites *today*.
2. **Required as a value** — an `http.HandlerFunc`, a `less` for `slices.SortFunc`, a map entry.
3. **It hides genuine complexity** — the body is non-obvious, and afterwards the **name is enough**.
4. **The parent would otherwise break its limits**, and the extraction restores one level of
   abstraction rather than moving lines out of sight.
5. **It needs its own test seam.**
6. **It is a named predicate** — naming a condition *is* the abstraction.
7. **A `defer` must run per iteration** — the loop body becomes a function so each file closes
   before the next opens.

**Otherwise keep it inline**, as its own paragraph with at most one "why" comment.

**Shallow-helper tests — if any fires, inline it:**

- **Interface** — the signature and its doc comment are longer than the body.
- **Name** — to know what happens, the reader opens the body anyway.
- **Entanglement** — reading the parent requires flipping into the helper and back.
- **Parameter** — three or more parameters exist only to rebuild the parent's context.
- **Wrapper** — the body is one library call, one log line, or one `fmt.Errorf`.
- **Stage** — the name is a moment (`stepTwo`, `afterParse`, `logOutcome`), not an action.

```go
// WRONG — a stage name, one call site, a comment several times the size of the body

// logOutcome logs both counts. Zero imports alone is ambiguous: an expired key,
// a rate limit and an empty feed look alike, so the request count is logged too.
func (i *Importer) logOutcome(ctx context.Context, imported, requests int) {
	i.logger.InfoContext(ctx, "import finished", "imported", imported, "requests", requests)
}

// CORRECT — the same call inline, the reason in one line
// requests tells an expired key or a rate limit apart from an honestly empty feed
i.logger.InfoContext(ctx, "import finished", "imported", imported, "requests", requests)
```

## Body Layout

**Guards → work → result.** Guard clauses first, each returning immediately; the work at the left
margin; one blank line between logical steps, none inside a step; more than three steps → extract;
the result computed into a well-named variable and returned last.

- **A boolean parameter is two functions.** `Export(orders, true)` reads as nothing at the call
  site, and Go has no keyword to rescue it. Take a defined type — `Export(orders, FormatCSV)` — or
  write both functions.
- **Errors are the last result, and the other results are zero when it is non-nil** — a caller
  never reads a value beside a non-nil error.
- **Parameters are ordered `ctx`, dependencies, subject, inputs, options.** Once several functions
  share the same dependencies, they become a struct's fields (trigger 4 in `methods.md`).
- **Do not reach outside.** A function uses only its parameters, its receiver and package-level
  constants: no package-level mutable variable, no `os.Getenv`. Where the result depends on the
  date or on chance, the clock is an injected `now func() time.Time` — a timestamp only logged is
  not a result.
- **Compute or do, not both.** A function returning a value has no side effects; a function with
  side effects returns only an `error`, or a small value describing what happened.
- **One level of abstraction per function.** An orchestrator contains only calls at its own level.
- **No output parameters, except a buffer the caller owns.** Return a new slice rather than filling
  one passed in. The carve-out is the standard library's own shape: `Read(p []byte)`,
  `AppendText(b []byte)`, `Unmarshal(data, &v)`, `Scan(&dest)` — the caller supplies the memory so
  that a hot path does not allocate.
- **Named results only where they document** — two results of one type, `(lat, long float64, err
  error)`, or one a deferred closure sets — and naked returns only where the function fits on screen.

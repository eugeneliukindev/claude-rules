---
paths:
  - "**/*.go"
---

# Go — Functions and Control Flow

## Control Flow

- **The happy path runs down the left margin.** Handle the error or the edge case first and
  return; the normal flow continues unindented — never nested inside `if err == nil`.
- **Extract any condition with more than two operands into a named predicate.** The linter counts
  the branches but cannot name the concept: `if isEligibleForRefund(order) {` says what the three
  clauses meant.
- **A `switch` replaces an `if`–`else if` chain**; never `fallthrough` to share code — list the
  cases together: `case StatusPaid, StatusShipped:`.
- **Every `switch` over an enum or a closed set of types ends with a `default` that fails**:
  `return fmt.Errorf("unknown status %v", s)`, or a `panic` where reaching it is a bug in this
  package. A silent fall-through is forbidden; the `exhaustive` linter checks the cases, the
  `default` catches the value nobody declared.
- **A factory over an open set dispatches through a map**: `build, ok :=
  buildersByKind[source.Kind]` — adding a kind is one entry. A closed enum stays a `switch`, which
  `exhaustive` can check.
- **A loop that filters or maps into a new slice stays a loop** — a chain of generic helpers
  standing in for a comprehension Go does not have is harder to read than the loop.
- **Write an iterator (`iter.Seq`) for any sequence a caller may stop early** or that reads from a
  stream, a file, a cursor or a paginated API — the caller's `break` then stops the reading. The
  details are in `go-types`.

## Functions

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
  share the same dependencies, they become a struct's fields (trigger 4 in `interfaces.md`).
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

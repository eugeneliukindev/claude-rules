---
paths:
  - "**/*.go"
---

# Go — Core

What applies to every Go edit, one topic per file here, all loaded together; `testing.md` loads
in test files. Everything else is a skill, invoked by its description or by name:

| Skill | When |
|---|---|
| `go-types` | choosing between a string, a defined type, an `iota` enum and a struct; a generic function or type; a closed set of variants; writing an iterator |
| `go-interfaces` | a second implementation, a test fake, where implementations live, embedding, a compile-time assertion |
| `go-boundaries` | HTTP, queues, caches, serialization, timeouts, retries, time, money, identifiers |
| `go-wiring` | `main`, where an object is built, a config field, a layer argument, closing what was opened |
| `go-concurrency` | a `go` statement, channels, `sync`, `errgroup`, cancellation, graceful shutdown |
| `go-persistence` | `database/sql`, a transaction boundary, a repository, a migration |
| `go-http` | a `net/http` server, handler, middleware or client |
| `go-json` | `encoding/json` or `encoding/json/v2`, struct tags, a custom marshaler, unknown fields |
| `go-packaging` | a module other code imports: exported surface, `internal/`, semver, `/v2`, deprecation |
| `go-cli` | a `main` package with flags, exit codes, stdout and stderr |
| `go-security` | input from outside: a body, a filename, a URL, an `exec.Command` argument, a credential |
| `go-performance` | a path already measured and found slow, a benchmark, a profile, allocations |
| `go-examples` | an example that ships — an `Example` function, a README snippet, `examples/` |
| `go-rules-authoring` | editing these rules or skills |
| `go-<library>` | the code imports that library — `testify`, `pgx`, `gin` |

Formatting, vet checks and mechanical complexity belong to `gofmt`, `go vet` and the linters.
**Nothing here restates what a tool decides**; a tool that disagrees wins, and this file gets a PR.
Three things about living with those tools do belong here:

- **A suppression names its linter and its reason on its line** — `//nolint:gosec // the path is
  from the embedded FS` — never a bare `//nolint`. The count only ever ratchets down.
- **A limit is named, not raised.** One forty-line function must not buy every other package the
  right to forty lines: the limit stays and the file is excluded by name, with a reason. When three
  files need the same escape, the rule is describing something real.
- **Write for the `go` directive in `go.mod`, not for the Go you remember.** Every idiom the
  declared version offers is the default — `min`/`max`, `for i := range n`, `slices`, `maps`,
  `errors.AsType`, `wg.Go`, `t.Context()`, `new(expr)` — and nothing newer, which `stdversion`
  rejects. `go fix ./...` rewrites the old idioms; its modernizers are the list of what changed.

## When Rules Conflict

1. An explicit instruction from the person you are working with, for this task.
2. A rule these files state without qualification.
3. What the standard library does in the same situation — it is the largest body of reviewed Go
   there is, and Effective Go and the Go Code Review Comments describe it.
4. Consistency with the surrounding code of the same package.
5. The default (*prefer*) in these files.
6. Your own judgement — and say so, rather than letting it read as a rule.

A rule wrong for the situation is changed here, with the reasoning — never worked around in code.

## Principles

Five, in priority order; the earlier wins a conflict. **Correct** — the code does what its name
and signature promise for every input the types allow, and returns an error otherwise. **Clear** —
a teammate understands the file top-down without opening others; clear beats clever. **Simple** —
the least machinery that solves today's problem. **Typed** — what Go can say in a type is said
there. **Fast enough, by measurement** — algorithmic sanity always, the rest with a profile.

And three properties of the system as a whole:

- **A failure stays where it happened.** One bad input or one unreachable dependency never stops
  the run: name what is protected — this row, this request — and handle the error at exactly that
  boundary, recording why. Degradation has a stated direction — skip, retry later, serve stale,
  return partial — written where the code makes the choice.

  ```go
  // WRONG — the boundary is the whole run: one unreachable SKU and nothing after it is updated
  for _, sku := range skus {
  	price, err := r.supplier.FetchPrice(ctx, sku)
  	if err != nil {
  		return fmt.Errorf("fetch price of %s: %w", sku, err)
  	}
  	r.prices[sku] = price
  }

  // CORRECT — the boundary is one SKU: it is recorded and skipped, the run goes on
  for _, sku := range skus {
  	price, err := r.supplier.FetchPrice(ctx, sku)
  	if errors.Is(err, ErrSupplierUnavailable) {
  		r.logger.WarnContext(ctx, "price fetch failed", "sku", sku, "error", err)
  		continue
  	}
  	if err != nil {
  		return fmt.Errorf("fetch price of %s: %w", sku, err)
  	}
  	r.prices[sku] = price
  }
  ```
- **Cost grows slower than the work.** Every external collection has a limit, every fan-out a
  bound, every goroutine an exit, every request a deadline. "It has always been small" is not one.
- **The next person is you, without the context.** One actor per package; a new case is data or a
  new file, never a new branch in something that already works. Deleting must be as easy as adding.

## YAGNI, KISS, DRY

- **Build what today's requirement needs.** A generalisation built for one case is a guess about
  the second, and a wrong abstraction outlives the duplication it prevented. An option nobody sets
  and an interface with one implementation and no fake are branches never known to work.
- **The simplest construction that fully solves the problem**, which is not the shortest one.
  Prefer the boring mechanism: a function over a type with methods, a `map` over a registry, a
  `switch` over a strategy. Simplicity is measured at the point of *use*.
- **DRY is about knowledge, not text.** Two fragments that look identical but answer to different
  actors are not duplication — merged, the next change arrives as a parameter, then a flag, then a
  branch. Two fragments that must change together are duplication even when they look nothing
  alike: a limit enforced in a validator and repeated in a migration. **Wait for the third
  occurrence**; a little copying is better than a little dependency.

## Definition of Done

`gofmt`, `go vet`, the linters and `go test -race` run first, clean with no new suppression. Then
the eight checks no tool makes, skipped first under pressure:

- [ ] Every new identifier passes `naming.md`'s Self-Check and survives the relocation test
- [ ] Every new package and type answers to one actor — name who would ask to change it
- [ ] Every helper passes the extraction tests; every type with methods has a trigger
- [ ] **Every exported name is used outside its package** — `find_overexported.go` reports nothing
- [ ] No generically named unit holds concrete logic; no concrete rule lives in two places
- [ ] No `any` or `map[string]any` crossing a package, no magic literal, no unkeyed struct literal
- [ ] Every error handled once — wrapped, translated, or logged where decided — never both
- [ ] Every goroutine has an owner who waits for it; every blocking call takes a `ctx`

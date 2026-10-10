---
name: go-packaging
description: >-
  The public surface of a Go module: what to export and what to keep in internal/, finding
  exported names nobody outside uses, semantic import versioning and the /v2 suffix, what counts
  as a breaking change, deprecation with a Deprecated paragraph and //go:fix inline, go.mod
  hygiene — the go directive, toolchain, tool directives, replace and retract — keeping an
  optional dependency in its own package or module, and checking compatibility with apidiff and
  gorelease. Use when building a Go module other code imports — a library, an SDK, a shared
  package — or when working with go.mod, a release tag, a major version or a deprecation.
paths:
  - "**/*.go"
  - "**/go.mod"
---

# Packaging and Public Surface

## What Is Exported

Go has two levels of visibility and one directory rule, and together they are the whole access
model:

- **Unexported** — lower-case, visible in its own package only. The default for everything.
- **Exported** — upper-case, visible to every importer, and part of the API the day the module is
  tagged.
- **`internal/`** — exported names in a package under `internal/` are visible only to code rooted
  at `internal/`'s parent. This is how a module shares code between its own packages without
  publishing it.

**A module's public packages are the ones a user is meant to import, and they are few.** Everything
else is under `internal/`. Moving a package out of `internal/` is a one-way door; moving one in is
a breaking change.

### Finding Names That Should Be Unexported

`scripts/find_overexported.go` lists every top-level exported constant, variable, function and type
that no file in another package of the module references. Run it from anywhere:

```
go run <this skill's directory>/scripts/find_overexported.go ROOT
```

It reads `go.mod` under `ROOT` for the module path, parses every package with the standard
library's `go/parser`, and counts a name as used when another package's file selects it through
the import. External test packages (`package x_test`) count as outside, because they see only the
exported API. Methods and struct fields are not reported — an interface or a reflection-based
encoder can need them with no visible reference. The script needs Go 1.21 and nothing else; it
exits 0 when nothing is found, 1 when names are, 2 when `ROOT` is not a module or a file does not
parse — `go run` prints that status and itself exits 1 for any non-zero one.

**It answers a different question in a library.** There, an exported name with no internal user may
well be the API. Run it on the module's `internal/` tree and on applications, and judge a library's
public packages by the API review below.

## Semantic Import Versioning

- **`v0` promises nothing, `v1` promises everything.** From `v1.0.0`, no tagged minor or patch
  release may break a caller that compiled against an earlier one.
- **A breaking change is a new major version with a new import path**: `module
  example.com/billing/v2` in `go.mod`, and every importer changes its import. Two majors can be
  imported side by side, which is the point.

  ```
  // WRONG — v2.0.0 tagged with the v1 path in go.mod: the go command rejects it as invalid
  module example.com/billing

  // CORRECT — the major version is part of the module path, and of every import of it
  module example.com/billing/v2
  ```
- **What breaks a caller is more than removal**: a changed signature, a new method on an exported
  interface (every implementation outside breaks), a new field in a struct callers construct
  positionally, a changed constant value, a narrowed accepted input, a type that stops being
  comparable. Adding a function, a type, a method to a struct or an optional field is safe.

  ```go
  // WRONG — v1.4.0 adds a method: every Store implemented outside the module stops compiling
  type Store interface {
  	Find(ctx context.Context, id OrderID) (Order, error)
  	Archive(ctx context.Context, id OrderID) error
  }

  // CORRECT — the new method is a new interface, discovered by assertion (go-interfaces)
  type Store interface {
  	Find(ctx context.Context, id OrderID) (Order, error)
  }

  type Archiver interface {
  	Archive(ctx context.Context, id OrderID) error
  }
  ```
- **`apidiff` or `gorelease` runs before every tag**, comparing against the last release, and
  reports exactly these. A human reviewing a diff does not.
- **A retracted version is declared in `go.mod`** — `retract v1.4.2 // publishes a broken
  migration` — and a fix is released above it. A tag is never moved or deleted: the module proxy
  and every `go.sum` already have it.

## Deprecation

```go
// WRONG — no paragraph starts "Deprecated:", so no tool sees it, and callers migrate by hand

// Charge charges amount with a fresh idempotency key. It is deprecated: use
// [ChargeWithKey], which makes retries idempotent.
func Charge(ctx context.Context, amount Cents) error {
	return ChargeWithKey(ctx, amount, NewIdempotencyKey())
}

// CORRECT — staticcheck reports every caller, and go fix rewrites each call to the body

// Charge charges amount with a fresh idempotency key.
//
// Deprecated: Use [ChargeWithKey], which makes retries idempotent.
//
//go:fix inline
func Charge(ctx context.Context, amount Cents) error {
	return ChargeWithKey(ctx, amount, NewIdempotencyKey())
}
```

- **The `Deprecated:` paragraph names the replacement** — editors strike the name through,
  `staticcheck` reports callers, and `pkg.go.dev` hides it.
- **`//go:fix inline` turns the deprecation into a migration**: `go fix` replaces every call with the
  body, so a caller upgrades by running one command. Keep the old body a single call to the new
  API, so that what gets inlined is exactly the code a caller would have written.
- **A deprecated name stays until the next major version.** Removing it in a minor release is the
  break the deprecation was meant to avoid.

## go.mod Hygiene

- **The `go` directive is the oldest Go the module supports**, and it decides the language
  features and `GODEBUG` defaults the code gets. Raise it deliberately, in its own change, when a
  feature is needed — not because the developer's toolchain is newer. A library's `go` line is a
  floor every importer must meet.
- **A `toolchain` line is for applications**, pinning the toolchain CI builds with. A library
  leaves it out.
- **Tools the build runs are `tool` directives**: `go get -tool golang.org/x/tools/cmd/stringer`,
  run as `go tool stringer`. Their versions are then in `go.mod` and `go.sum` like any dependency.
- **No `replace` in a published module** — it is ignored by importers and so only hides a
  dependency the published module does not actually build with. `replace` to a local path is a
  development aid; `go.work` is the tool for that and stays out of the repository.
- **`go mod tidy` leaves no diff** — CI checks it. A dependency used only by tests is still
  declared; an unused one is not.
- **`govulncheck ./...` runs in CI** (`go-security`).

## Optional Dependencies

Go has no optional extras: a dependency of any package in the module is a dependency of the module
for everyone who resolves it, and a dependency of an imported package is linked into the binary.

- **A heavy or vendor-specific dependency lives in its own package**, which only the users of that
  integration import — `billing/stripebilling` beside `billing`. The core package never imports
  it, so a binary that does not use the integration never links it.
- **A dependency that drags in a large graph gets its own module** — a nested `go.mod` in
  `billing/stripebilling/` — so that even resolving the core module does not fetch it. This costs
  a separate version and release; pay it only when the graph is genuinely large.
- **`depguard` lists the packages allowed to import each such dependency**, so the inventory of
  where it is used is a configuration file reviewed when it grows.

## A Package Named Like a Standard One

A package called `errors`, `log`, `context` or `http` forces every file that needs both to alias
one of them, and each file picks a different alias. Name the package for what it adds —
`apperrors` is still a kind-of-declaration name; `problems`, `httperror`, `auditlog` say what is
inside.

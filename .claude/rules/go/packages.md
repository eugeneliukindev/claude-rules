---
paths:
  - "**/*.go"
---

# Go — Packages and Files

## File Layout

Every file has the same order, so a reader always knows where to look:

1. The package comment — once per package, in `doc.go` or the file named after the package.
2. The package clause and the imports, grouped as `goimports` writes them.
3. **Constants.**
4. Package-level variables — sentinel errors, compile-time assertions, a `regexp.MustCompile`, a
   lookup table nobody writes to. Nothing else.
5. Error types, then interfaces this package consumes.
6. Each type, immediately followed by its constructor, then its exported methods, then its
   unexported ones.
7. Exported functions, high-level first — the step-down rule applies to files as to functions.
8. Unexported functions, in call order.

**A file's name says which part of the package it holds** — `order.go`, `refund.go`; one that
would need two names is two files. Size is a smell, not a limit: the seam is your judgement.

- **No `init` and no mutable package-level state.** `init` runs at import, in an order the reader
  cannot see, and makes the package untestable in isolation; a package-level `var` someone writes
  to is a global with a nicer name. The carve-out is registration a framework requires by design —
  a `database/sql` driver, an `image` format — and it lives in its own file. `main` is where
  everything else is built.

## Every Name Not Used Outside Is Unexported

Types, functions, constants, variables, struct fields and methods alike. A config section only the
root struct holds, a row shape only its own repository scans into, a limit only its own function
reads: each starts lower-case — `retrySettings`, `orderRow`, `maxBatchRows`. Without it the name
reads as part of the package's surface, and the first import from another package makes it one for
good. **Constants and struct fields are the ones that get missed**: a constant quietly read from
a second package ends up with two homes and no owner.

The test is mechanical: for each exported name, search the module outside the package that
declares it, and unexport everything with no hits. A script does it:
`go run ~/.claude/skills/go-packaging/scripts/find_overexported.go ROOT`. Run it **after** the move
that made a name internal — that is when an exported name quietly stops being one. A method that
satisfies an interface, a field a marshaler reads by reflection and a symbol in a published module
have callers the search cannot see; the script skips methods and fields, and a library's API is
judged by `go-packaging`, not by it.

## Package Boundaries

- **`internal/` holds everything no other module should import.** An application's packages live
  under it by default; a package moves out only when something outside the module is meant to
  depend on it.
- **An import cycle is a design error, not a build error.** Go refuses it, and the fix is never a
  third package named `common` that both import: it is an interface the lower package declares, or
  a type that belongs to one side.
- **No dot imports; a blank import only in `main` or a test** — a driver, a pprof handler. An alias
  only on a collision, and then the same alias everywhere.
- **Never depend on what you only import transitively**; `go mod tidy` keeps `go.mod` the honest
  list, and a tool the build runs is a `tool` directive in `go.mod`, not a global install.

## Resources

- **Release on the line after acquisition succeeds**: `f, err := os.Open(name)`, the error check,
  then `defer f.Close()` — for what is only read, a project whose `errcheck` reports that excludes
  reader `Close` once in its configuration, never per call. For anything written — a file, a
  transaction, a buffered writer — the error from `Close` or `Commit` says whether the data
  arrived, and it is returned. Who owns what, and closing in reverse order: `go-wiring`.

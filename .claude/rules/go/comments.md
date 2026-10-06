---
paths:
  - "**/*.go"
---

# Go — Comments and Doc Comments

## Documentation

**Which names need a doc comment is the linter's decision** — every exported one, in most
configurations; what goes inside one, and whether a comment is written at all, is not.

**A doc comment is a sentence that starts with the name it documents** and states the contract —
what it returns, what it does, which errors a caller may test for — and stops. `// ShortestRoute
returns the cheapest path between two stops.`, never `// Runs Dijkstra over the adjacency map.`
Its length follows publication, not complexity: a package others import gets full paragraphs, doc
links (`[io.Reader]`, `[ErrNotFound]`) and an `Example`; inside an application one sentence is the
norm. The package comment starts `// Package orders …` and exists once per package.

- **`Deprecated:` opens its own paragraph** and names the replacement — tools read exactly that;
  the mechanics are in `go-packaging`. A directive — `//go:generate`, `//nolint` — is not a comment.

**A comment inside a function is one line, in one of four forms** — anything else restates the
code:

```go
// Retry budget for transient errors:
const idleTimeout = 30 * time.Second // the load balancer drops idle connections at 35
// TODO: drop the fallback once every client sends the version header
// NOTE: mirrored in limits.h, which cannot import this package
```

A caption ends in a colon and indexes the lines below. A reason says why *this* value, never what
the line does. A `TODO` names the condition that removes it, not an owner — the owner leaves, the
condition does not. A `NOTE` marks a coupling code cannot express — make it real first with one
shared constant, type or call, and keep the prefix for what crosses languages, where it makes the
debt greppable. A paragraph is earned only by enumerated cases a reader cannot recover from the
code, or by a recorded limitation that ends honestly: "not supported for now".

Forbidden — a licence header exempt: commented-out code, restating the code, section banners, author or date stamps, change
logs, and comments that describe a name instead of fixing it.

## Comments Are Local

A comment describes **only the code in its own block**; a doc comment describes **only the
contract of the thing it is attached to**. Both must stay true when anything outside changes.

- **Scope equals placement.** A comment inside a loop body is about that iteration. A function's
  doc comment covers its parameters, results, errors and side effects — never wider.
- **No callers, no collaborators, no ordering.** `// called by Service.PlaceOrder`, `// must run
  before flush`, `// used by the nightly job` — each rots the moment the other side changes, and
  nothing checks it. The single carve-out is the `NOTE:` above: a coupling between artefacts that
  cannot import each other.
- **No cross-comment continuity** — never "as above", "see the interface", "same as `Save` but
  batched". Either a method adds nothing to the interface's contract and repeats its one sentence,
  or it states its own contract in full.
- **The relocation test.** Cut the block and paste it into another package: if the comment becomes
  wrong, meaningless or unverifiable, it was leaking. **If a comment can only be written by
  referring elsewhere, the design is wrong**, not the comment.

```go
// WRONG — a caller and an ordering in prose, and a comment restating the check

// ValidateOrder reports why the order cannot be placed, or nil.
func ValidateOrder(order Order) error {
	// called by PlaceOrder before persist; do not reorder
	// check the order does not have too many items
	if len(order.Items) > 100 {
		return ErrTooManyItems
	}
	return nil
}

// CORRECT — the number is named, and one line says why this value
const maxOrderItems = 100 // the payment provider rejects longer baskets

// ValidateOrder reports why the order cannot be placed, or nil.
func ValidateOrder(order Order) error {
	if len(order.Items) > maxOrderItems {
		return ErrTooManyItems
	}
	return nil
}
```

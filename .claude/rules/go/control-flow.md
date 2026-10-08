---
paths:
  - "**/*.go"
---

# Go — Control Flow

- **The happy path runs down the left margin.** Handle the error or the edge case first and
  return; the normal flow continues unindented — never nested inside `if err == nil`.
- **Extract any condition with more than two operands into a named predicate.** The linter counts
  branches, not the concept: `if isEligibleForRefund(order) {` says what the three clauses meant.
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

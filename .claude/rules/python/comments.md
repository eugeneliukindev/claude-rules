---
paths:
  - "**/*.py"
---

# Python — Comments and Docstrings

## Documentation

**Which names need a docstring is the linter's decision**; what goes inside one — and whether a
comment is written at all — is not.

**A comment is one line.** In both reference libraries two thirds of comment blocks are a single
line and fewer than one in ten runs past three; that ratio is the budget. The common failure is
not a missing comment but a five-line paragraph restating the statement below it.

**A paragraph is earned by one of two things.** *Enumerated cases* — branches a reader cannot
recover from the code, as a numbered list. *A recorded limitation* — what was deliberately not
supported and what happens to whoever tries it, ending honestly: "not supported for now".

**Four forms, and a comment takes no others:**

- **A caption** — a few words ending in a colon, above the lines it introduces: `# Cookies that
  are not fully described:`. It indexes the code rather than explaining it.
- **A reason** — why *this* value, on the same line when it fits and directly above when it does
  not. Never what the line does.
- **`# TODO:` naming the condition that removes it** — "when support for the old runtime is
  dropped" — never an owner, which rots at the first handover. It may be an open question.
- **`# NOTE:` marking a coupling that code cannot express** — a constant mirrored in a native
  extension, a type alias duplicated in a stub. Make the coupling real first: one shared constant,
  one shared type, one call. Across two languages that is impossible, and the prefix is the value:
  it makes the debt greppable.

A legal header is exempt; where a suppression's reason goes is in `core.md`.

Forbidden: commented-out code, restating the code, section banners, author or date stamps, change
logs, and comments that describe a name instead of fixing it.

**A docstring's length follows publication, not complexity.** Where a generator renders it for
outside readers it is full — summary, parameters, return value, the errors this function's own
logic raises. Everywhere else it is one line and often absent: one reference library leaves nearly
half its public names undocumented. It states the contract and stops — `"""Return the shortest
route between two stops."""`, never `"""Run Dijkstra over the adjacency map."""`

## Comments and Docstrings Are Local

A comment describes **only the code in its own block**; a docstring describes **only the contract
of the thing it is attached to**. Both must stay true when anything outside changes.

- **Scope equals placement.** A comment inside a loop body is about that iteration. A function
  docstring covers its parameters, return value, raised errors and side effects — never wider.
- **No callers, no collaborators, no ordering.** `# called by OrderService.place_order()`,
  `# must run before _flush()`, `"""Called by the nightly batch job."""` — each rots the moment
  the other side changes, and nothing checks it. The single carve-out is the `NOTE:` above: a
  coupling between artefacts that cannot import each other.
- **No cross-docstring continuity** — never "as described above", "see the base class", "same as
  `save()` but async". Either the override adds nothing and gets no docstring, or it states its
  own contract in full.
- **The relocation test.** Cut the block and paste it into another module: if the comment becomes
  wrong, meaningless or unverifiable, it was leaking. **If a comment can only be written by
  referring elsewhere, the design is wrong**, not the comment.

```python
# WRONG — a caller and an ordering in prose, and a comment restating the check
def validate_order(order: Order) -> None:
    # called by place_order() before _persist(); do not reorder
    # check the order does not have too many items
    if len(order.items) > 100: ...

# CORRECT — the number is named, and one line says why this value
_MAX_ORDER_ITEMS: Final = 100  # the payment provider rejects longer baskets

def validate_order(order: Order) -> None:
    if len(order.items) > _MAX_ORDER_ITEMS: ...
```

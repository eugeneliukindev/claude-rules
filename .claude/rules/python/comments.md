---
paths:
  - "**/*.py"
---

# Python — Comments and Docstrings

## Documentation

**Which names need a docstring is the linter's decision**; what goes inside one — and whether a
comment is written at all — is not.

**A comment is one line, in one of four forms** — anything else restates the code:

```python
# Cookies that are not fully described:
_IDLE_TIMEOUT_SECONDS: Final = 30  # the gateway drops idle connections at 35
# TODO: drop the fallback once the old runtime is no longer supported
# NOTE: mirrored in limits.h, which cannot import this module
```

A caption ends in a colon and indexes the lines below. A reason says why *this* value, never what
the line does. A `TODO` names the condition that removes it, never an owner. A `NOTE` marks a
coupling code cannot express — make it real first with one shared constant, type or call, and keep
the prefix for what crosses languages, where it makes the debt greppable. A paragraph is earned only
by enumerated cases a reader cannot recover from the code, or by a recorded limitation that ends
honestly: "not supported for now".

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

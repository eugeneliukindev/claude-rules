---
paths:
  - "**/*.py"
---

# Python — Functions and Control Flow

## Control Flow

- **Extract any condition with more than two operands into a named predicate.** The linter measures
  the complexity but cannot name the concept: `if _is_eligible_for_refund(order):` says what the
  three clauses meant.
- **`match` is structural pattern matching, not a `switch`.** Use it to destructure a closed union
  of variants or nested data; not to compare one scalar against constants, and not for two branches.
- **A bare name in a pattern binds, it does not compare**, whatever its case — the one thing about
  `match` worth memorising. Constants in patterns are dotted:

  ```python
  case Order(status=PAID): ...              # WRONG — matches every order and binds PAID
  case Order(status=OrderStatus.PAID): ...  # CORRECT — compares
  ```
- **Every `match` over a union or `Enum` ends with exhaustiveness**: `case _: assert_never(value)`,
  or a named error. A silent fall-through is forbidden.
- **A factory dispatches through a mapping, not through `match`.** Kind in, builder out:
  `_BUILDER_BY_KIND[source.kind](**options)`. Adding a kind is one entry, and the set is readable
  in one place instead of spread over branches.
- **A comprehension holds one transformation; anything more is a loop.** The judgement is about
  how much the reader can hold, not how much fits.
- **Write a generator function for any lazy sequence longer than a one-line expression**, and for
  anything reading from a stream, file, cursor or paginated API.

## Functions

- **Does one thing.** If describing it needs "and", split it. SRP is a different rule, for modules.
- **Group related parameters into a frozen dataclass** rather than growing the signature.

## Extraction Must Pay for Itself

A helper's name, signature and docstring are an **interface**; it pays only by hiding more than it
exposes.

**Extract when at least one is true:**

1. **Real reuse** — two or more call sites *today*.
2. **Required as an object** — a callback, a `key=` function, a dispatch-table value, a hook.
3. **It hides genuine complexity** — the body is non-obvious, and afterwards the **name is enough**.
4. **The parent would otherwise break its limits**, and the extraction restores one level of
   abstraction rather than moving lines out of sight.
5. **It needs its own test seam.**
6. **It is a named predicate** — naming a condition *is* the abstraction.

**Otherwise keep it inline**, as its own paragraph with at most one "why" comment.

**Shallow-helper tests — if any fires, inline it:**

- **Interface** — signature plus docstring is longer than the body.
- **Name** — to know what happens, the reader opens the body anyway.
- **Entanglement** — reading the parent requires flipping into the helper and back.
- **Parameter** — three or more parameters exist only to rebuild the parent's context.
- **Wrapper** — the body is one library call, one `logger.*`, or one arithmetic expression.
- **Stage** — the name is a moment (`_step_two`, `_after_parse`, `_log_outcome`), not an action.

**Never extract a function to have somewhere to put a docstring** — reasoning that does not fit
the code is one inline "why" comment, not a comment with call overhead.

```python
# WRONG — a stage name, one call site, a docstring several times the size of the body
def _log_outcome(imported: int, requests: int) -> None:
    """Log both counts.

    Zero imports alone is ambiguous: an expired key, a rate limit and an empty feed look alike.
    """
    logger.info("import finished", extra={"imported": imported, "requests": requests})

# CORRECT — the same call inline, the reason in one line
# requests tells an expired key or a rate limit apart from an honestly empty feed
logger.info("import finished", extra={"imported": imported, "requests": requests})
```

## Body Layout

**Guards → work → result.** Guard clauses first, with an immediate `return` or `raise`; the happy
path at indentation level 1 — if it is nested inside an `if`, invert the condition and return
early; one blank line between logical steps, none inside a step; more than three steps → extract;
the result computed into a well-named local and returned last.

- **A boolean parameter that gets past the linter is still two functions.** Made keyword-only it
  stops being a boolean trap and stays a design fault: `export(orders, *, as_csv=True)` does two
  things under one name. Take a `Literal` or `Enum` format instead, or write both functions.
- **The branch does not pick the return type.** `str` on one path and `list[str]` on another
  forces every caller to re-discover which it got. A union is fine when it is a **named closed
  type** — `type PaymentOutcome = Captured | Declined`, matched exhaustively — never an accident of
  which branch ran. `None` is legitimate only for `find_…`-style lookups and procedures.
- **Parameters are ordered subject, required inputs, optional configuration**; injected
  dependencies come first — they are the function's environment.
- **Do not reach outside.** A function uses only its parameters and module-level constants: no
  global mutable state, no `settings` import, no clock or randomness buried inside.
- **Compute or do, not both.** A function returning a value has no side effects; a function with
  side effects returns `None` or a small object describing what happened.
- **One level of abstraction per function.** An orchestrator contains only calls at its own level.
- **No output parameters**: never pass a collection to be filled. Return a new one.

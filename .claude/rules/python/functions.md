---
paths:
  - "**/*.py"
---

# Python — Functions

- **Does one thing.** If describing it needs "and", split it. SRP is a different rule, for modules.
- **Values that travel together become one frozen dataclass** (the test is in `python-wiring`);
  collaborators that travel together are a constructor instead (`classes.md`, trigger 4).

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

```python
# WRONG — extracted to make room for a docstring: a stage name, one call site, a one-line body
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
early; one blank line between logical steps, none inside a step; a step below its siblings' level
is extracted (reason 4), and length alone never is; the result returned last.

- **A boolean parameter that gets past the linter is still two functions.** Made keyword-only it
  stops being a boolean trap and stays a design fault. Take a `Literal` or `Enum`, or write both.
  ```python
  # WRONG — keyword-only, and still two functions behind one name
  def export(orders: Sequence[Order], *, as_csv: bool) -> bytes: ...
  # CORRECT — the format is a closed set the caller names
  def export(orders: Sequence[Order], export_format: ExportFormat) -> bytes: ...
  ```
- **The branch does not pick the return type.** `str` on one path and `list[str]` on another
  forces every caller to re-discover which it got. A union is fine when it is a **named closed
  type** — `type PaymentOutcome = Captured | Declined`, matched exhaustively — never an accident of
  which branch ran. `None` is legitimate only for lookups where absence is normal, and procedures.
- **Parameters are ordered subject, required inputs, optional configuration**; injected
  dependencies come first — they are the function's environment.
- **Do not reach outside.** A function uses only its parameters and module-level constants: no
  global mutable state, no `settings` import, no clock or randomness buried inside.
  ```python
  # WRONG — the clock and the lifetime come from outside, and no test can fix either
  def is_expired(token: Token) -> bool:
      return datetime.now(UTC) > token.issued_at + settings.token_lifetime
  # CORRECT — both arrive as parameters
  def is_expired(token: Token, *, now: datetime, lifetime: timedelta) -> bool:
      return now > token.issued_at + lifetime
  ```
- **Compute or do, not both.** A function returning a value has no side effects; a function with
  side effects returns `None` or a small object describing what happened.
- **One level of abstraction per function.** An orchestrator contains only calls at its own level.
- **No output parameters**: never pass a collection to be filled. Return a new one.

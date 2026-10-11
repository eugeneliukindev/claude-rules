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
exposes. **What every caller would repeat lives inside**; a parameter is for values callers vary.

**Extract when at least one is true:**

1. **Real reuse** — two or more call sites *today*.
2. **Required as an object** — a callback, a `key=` function, a dispatch-table value, a hook.
3. **It hides genuine complexity** — the body is non-obvious, and afterwards the **name is enough**.
4. **The parent would otherwise break its limits**, and the extraction restores one level of
   abstraction rather than moving lines out of sight.
5. **It needs its own test seam.**
6. **It is a named predicate** for a concept the condition only implies (`control-flow.md`).

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

- **A boolean that selects between two behaviours is two functions**, or a `Literal` or `Enum` the
  caller names, keyword-only or not; a keyword-only one tuning one behaviour — `sorted(reverse=)`,
  `subprocess.run(check=)`, `zip(strict=)` — is fine. The test is whether the branches share a body.
  ```python
  # WRONG — keyword-only, and still two behaviours behind one name
  def export(orders: Sequence[Order], *, as_csv: bool) -> bytes: ...
  # CORRECT — the format is a closed set the caller names
  def export(orders: Sequence[Order], export_format: ExportFormat) -> bytes: ...
  # CORRECT — one behaviour, tuned: both orders share the whole body
  def rank(orders: Sequence[Order], *, descending: bool = False) -> list[Order]: ...
  ```
- **The branch does not pick the return type.** `str` on one path and `list[str]` on another
  forces every caller to re-discover which it got. A union is fine when it is a **named closed
  type** — `type PaymentOutcome = Captured | Declined`, matched exhaustively — never an accident of
  which branch ran. `None` is legitimate only for lookups where absence is normal, and procedures.
- **The subject first, then the other required inputs; after `*`, by keyword, the injected
  dependencies and optional configuration** — a new one never shifts a position, and the root binds
  them with `partial(f, mailer=...)`. A payload a library hands in, its name meaning nothing to the
  caller, is positional-only; a signature a framework dictates keeps the framework's order.
  ```python
  def send_receipt(mailer: Mailer, payment: Payment) -> None: ...  # WRONG — reads as about mail
  def send_receipt(payment: Payment, *, mailer: Mailer) -> None: ...  # CORRECT — a named dependency
  async def on_webhook(body: bytes, /, *, verifier: SignatureVerifier) -> None: ...  # CORRECT
  ```
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
- **Compute or do, not both.** A query has no side effects. A command returns `None` or the outcome
  of its own effect — the id it assigned, the row count, the item it removed — never a value a
  reader would mistake for a lookup, and never behind a `get_` (`naming.md`).
  ```python
  def get_session(user_id: UserId) -> Session: ...  # WRONG — opens one when none exists
  def open_session(user_id: UserId) -> SessionId: ...  # CORRECT — a command, returning its id
  ```
- **One level of abstraction per function.** An orchestrator contains only calls at its own level.
- **No output parameters**: never pass a collection to be filled. Return a new one.

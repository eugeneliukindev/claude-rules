---
paths:
  - "**/*.py"
---

# Python — Core

What applies to every Python edit. `naming.md` loads with it; `testing.md` loads in test files.
Everything else is a skill, invoked when the work reaches it — by its own description, or by name:

| Skill | When |
|---|---|
| `python-types` | choosing between `Literal`/`Enum`/`NewType`/`TypedDict`, writing a generic, narrowing an unknown, reaching for `collections.abc`, a dunder |
| `python-boundaries` | HTTP, queues, caches, serialization, timeouts, retries, time, money, identifiers |
| `python-wiring` | an entry point, where an object is built, a settings field, a layer argument |
| `python-contracts` | an ABC or `Protocol`, a second implementation, a test fake, where implementations live |
| `python-async` | `async def`, threads, processes |
| `python-persistence` | a transaction boundary, a repository, a migration plan |
| `python-packaging` | a package other code imports: `__all__`, façade, `_internal`, optional extras, deprecation, a module named like a stdlib one |
| `python-cli` | an entry point with an argument parser |
| `python-security` | input from outside: a body, a filename, a URL, a subprocess argument, a credential |
| `python-performance` | a path already measured and found slow |
| `python-examples` | an example that ships — docstring, README, `examples/` |
| `python-rules-authoring` | editing these rules or skills |
| `python-<library>` | the code imports that library — `pydantic`, `sqlalchemy`, `tenacity`, `niquests`, `orjson` |

Style, layout and mechanical complexity belong to the formatter, the linters and the type checker.
**Nothing here restates what a tool decides**, and which tools a project runs is the project's
business. When a tool and this file disagree, the tool wins and this file gets a PR.

Two things about living with those tools are not configuration and do belong here:

- **A suppression carries its rule code and its reason on the same line.** An unexplained one is a
  defect in its own right, and the count only ever ratchets down.
- **A limit is named, not raised.** One module with fifteen members must not buy every other
  module the right to fifteen: the limit stays and the file is named, with a checkable reason. When
  three files need the same escape, the rule is describing something real about the architecture.

## When Rules Conflict

1. An explicit instruction from the person you are working with, for this task.
2. A rule these files state without qualification.
3. What `pydantic` or `sqlalchemy` does in the same situation — they are large, long-lived, and
   have paid for their choices.
4. Consistency with the surrounding code of the same package.
5. The default (*prefer*) in these files.
6. Your own judgement — and say so, rather than letting it read as a rule.

A rule that is wrong for the situation gets changed here, with the reasoning — not worked around
silently in code. A rule that is regularly worked around is a rule that needs changing.

## Principles

Five, in priority order; when two rules conflict the earlier principle wins. **Correct** — the code
does what its name and signature promise, for every input the types allow, and fails loudly
otherwise. **Readable** — a teammate who has never seen the file understands it top-down without
opening other files; names carry the meaning, comments are the exception. **Simple** — the least
machinery that solves today's problem. **Typed** — illegal states are unrepresentable, and the
checker catches the mistake rather than the reviewer. **Fast enough, by measurement** — algorithmic
sanity always, anything beyond that with a profile in hand.

And three properties of the system as a whole:

- **A failure stays where it happened.** One bad input, one unreachable dependency must never stop
  the run. Decide the blast radius *before* writing the `try` — name what is being protected, this
  row, this source, this request — and catch at exactly that boundary; a `try` around the whole
  loop turns one bad item into zero results. A failure is recorded with its reason and the run
  continues. Degradation has a stated direction — skips, retries later, serves stale, returns
  partial — written where the code makes the choice.
- **Cost grows slower than the work.** Nothing unbounded: every external collection has a limit,
  every fan-out a semaphore, every run a deadline. Stream what can be streamed. "It has always been
  small" is not a bound.
- **The next person is you, without the context.** One actor per module; a new case is data or a
  new file, never a new branch in something that already works. Deleting must be as easy as adding.

## YAGNI, KISS, DRY

- **Build what today's requirement needs.** The cost of a speculative feature is not the hour spent
  writing it; it is that everything afterwards must keep it working. A generalisation built for one
  case is a guess about the second, and a wrong abstraction is harder to remove than the
  duplication it prevented, because callers have grown into it. A configuration option nobody sets
  and a parameter that is always the default are branches never known to work.
- **The simplest construction that fully solves the problem**, which is not the shortest one.
  Prefer the boring mechanism: a function over a class, a dict over a registry. Simplicity is
  measured at the point of *use*.
- **DRY is about knowledge, not text.** Two fragments that look identical but answer to different
  actors are not duplication — merging them couples two things that must be free to move apart,
  and the next change arrives as a parameter, then a flag, then a branch. Two fragments that must
  change together are duplication even when they look nothing alike: a limit enforced in a
  validator and repeated in a schema. **Wait for the third occurrence.** The cure is often a shared
  constant or a shared type, not a new unit that has to be named.

## Control Flow

- **Extract any condition with more than two operands into a named predicate.** The linter measures
  the complexity but cannot name the concept: `if _is_eligible_for_refund(order):` says what the
  three clauses meant.
- **`match` is structural pattern matching, not a `switch`.** Use it to destructure a closed union
  of variants or nested data; not to compare one scalar against constants, and not for two branches.
- **A bare name in a pattern binds, it does not compare** — whatever its case. Constants in
  patterns are dotted: `case Order(status=OrderStatus.PAID):`. Nested, `case Order(status=PAID):`
  matches every order and binds `PAID`; it is the one thing about `match` worth memorising.
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

### Extraction Must Pay for Itself

The name, the signature, the docstring and the jump the reader makes are an **interface**, paid for
by everything around it. Deep functions hide a lot behind a small interface; shallow ones expose an
interface as complex as their body and hide nothing.

**Extract when at least one is true:**

1. **Real reuse** — two or more call sites *today*.
2. **Required as an object** — a callback, a `key=` function, a dispatch-table value, a framework
   hook. No choice, and size is irrelevant.
3. **It hides genuine complexity** — the body is non-obvious, and afterwards the **name is enough**.
4. **The parent would otherwise break its limits**, and the extraction restores one level of
   abstraction rather than moving lines out of sight.
5. **It needs its own test seam.**
6. **It is a named predicate** — naming a condition *is* the abstraction.

**Otherwise keep it inline**, separated by a blank line as its own paragraph, with at most one
"why" comment.

**Shallow-helper tests — if any fires, inline it:**

- **Interface** — signature plus docstring is longer than the body.
- **Name** — to know what happens, the reader opens the body anyway.
- **Entanglement** — reading the parent requires flipping into the helper and back.
- **Parameter** — three or more parameters exist only to rebuild the parent's context.
- **Wrapper** — the body is one library call, one `logger.*`, or one arithmetic expression. That is
  a rename, not an abstraction.
- **Temporal decomposition** — the name describes a *stage* (`_step_two`, `_after_parse`,
  `_log_outcome`) rather than a standalone action. Splitting along time instead of knowledge
  produces helpers that can never be understood alone.

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

### Body Layout

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

## Classes

Functions are the default; a class is an upgrade that must be triggered. A module is already a
namespace with "methods", so a class has to offer something a module does not.

**Write a class when at least one is true:**

1. **State survives between calls** — a token bucket, a pool, an accumulator, an open session.
2. **Invariants tie values together** — `Money`, `DateRange`. That is a frozen dataclass with
   methods, not a "service" class.
3. **The behaviour must be swappable** — two or more implementations behind one contract, or a test
   needs a fake.
4. **Several operations share the same dependencies** — three or more functions in a module taking
   the same two or more parameters. Those repeated parameters *are* a constructor.
5. **There is a lifecycle** — acquire/release, `__enter__`/`__exit__`, `close()`.
6. **A framework demands it** — `Enum`, `Exception`, a dataclass.

**Reliable signs of a class that should not exist**: `__init__` plus one method
(`Calculator(x).calculate()` is `calculate(x)`); only `@staticmethod`s; a box for constants; a
stateless "service" with no dependencies. And one more, visible only while reading: **a class whose
methods want to be grouped by who asks for their changes** rather than by visibility answers to
more than one actor — split the class, do not reorder it.

Before reaching for a class, consider `functools.partial` or a closure, a frozen dataclass of
options as a parameter, or **splitting the module** — a long module of independent functions is
idiomatic Python and does not improve by growing a `self`.

```python
# WRONG — the same client and base URL threaded through every function
def fetch_product_urls(client: Client, base_url: str, page_number: int) -> list[str]: ...
def fetch_product(client: Client, base_url: str, product_id: ProductId) -> Product: ...
def fetch_price(client: Client, base_url: str, product_id: ProductId) -> Money: ...

# CORRECT — trigger 4: the repeated parameters were the constructor
class ProductCatalogue:
    def __init__(self, client: Client, base_url: str) -> None: ...
    def fetch_product_urls(self, page_number: int) -> list[str]: ...
    def fetch_product(self, product_id: ProductId) -> Product: ...
    def fetch_price(self, product_id: ProductId) -> Money: ...
```

**The rest of SOLID, where it breaks**: depend on abstractions — inject, never instantiate a
collaborator inside a class. A subclass is usable wherever its parent is: it never narrows a return
type or widens a parameter.

### One Actor per Module and Class

This is SRP, and it is not "does one thing" — that rule is for functions. A responsibility is an
**actor**: whoever asks for the change — finance for pay rules, HR for the hours report, the DBA
for the schema. Code answering to two actors does not share a module or a class even when it shares
the data, or a fix one of them asks for ships to the other. **The test is who, not which layer**:
name who would ask to change each function, and two answers are two modules; splitting I/O, domain
and presentation follows from it and does not replace it. The data stays one frozen dataclass, each
actor gets a module of functions over it, and old entry points survive as a façade that delegates.

```python
# WRONG — one module, two actors: finance changes _regular_hours for pay, HR's report moves too
def _regular_hours(timesheet: Timesheet) -> Decimal: ...
def calculate_pay(timesheet: Timesheet) -> Money: ...        # finance
def report_hours(timesheet: Timesheet) -> HoursReport: ...   # HR

# CORRECT — payroll.py and hours_report.py, each with its own private _regular_hours;
# what they share is the frozen Timesheet, never the rule
```

The layer split alone would have passed the wrong version: both functions are pure domain logic.
That is the duplication DRY tells you to keep.

**A contract is a base class with `@abstractmethod` that implementations inherit** — a missing
method fails where the class is defined, not at a distant call site. `Protocol` is for code you
cannot make inherit; the rest is in `python-contracts`.

## Module Layout and Encapsulation

Every module has the same order, so a reader always knows where to look:

1. Module docstring — one line, always.
2. `from __future__ import annotations`, when the target version needs it.
3. Imports.
4. `__all__` — in `__init__.py` only, and there it is the whole file.
5. **Module-level constants.**
6. Type aliases, `NewType`s, type parameters.
7. Module logger.
8. Exception classes.
9. Contract-ABCs and protocols, then concrete classes, then the models private to this module.
10. Public functions, high-level first — the step-down rule applies to modules as to classes.
11. Private functions, in call order.
12. The `__main__` guard — a single call to `main()`, nothing else.

**Where Python's definition order overrides this one, it wins** — a validator comes before the
type alias built from it. Anything else that will not fit is a seam: a constant derived from a class
means the module holds the shape and what is computed from it, so **split it** rather than
renumber the list.

- **Size is a smell, not a limit.** The linters enforce a ceiling; the seam is your judgement.
- **No executable statements at import time** other than constants and the logger. No network
  calls, no file reads, no settings construction — these make imports slow, order-dependent and
  untestable. **`main()` is a function, never module-level code.**

### Every Top-Level Name Not Used Outside Takes an Underscore

Classes, functions, constants and type aliases alike. A settings section that only appears as a
field of the root, a row shape only its own repository builds, a policy only its own service
applies, a limit only its own function reads, an alias only its own signatures mention: each takes
the prefix — `_RetrySettings`, `_OrderRow`, `_RefundPolicy`, `_MAX_BATCH_ROWS`, `_Headers`. Without
it the name reads as part of the module's surface, and the first import from another module makes it
one for good.
**Constants and aliases are the ones that get missed**: a class draws attention once imported, a
constant is quietly read from a second module and ends up with two homes and no owner.

The test is mechanical: for each top-level name, search the tree without the file that defines
it, and prefix everything with no hits. A script does it:
`python ~/.claude/skills/python-packaging/scripts/find_unprefixed_names.py ROOT`. Run it **after**
the move that made a name internal — that is when a public name quietly stops being one. A name a
framework reaches through a decorator — a CLI command, a route handler, a fixture — has a caller
the search cannot see; the script lists those separately, and exempts `main`, `run` and `logger`.

### Imports

- **Import modules for modules, names for classes and functions.** Then call `invoices.issue(...)`
  or `issue_invoice(...)` — never a three-level attribute chain, which hides what is used.
- **A function-level import is flagged, and exactly three reasons buy the suppression**: breaking a
  genuine circular import, loading a heavy or optional implementation on demand, and a façade that
  exports implementations whose libraries are separate extras. Each carries the reason on the line.
  Generic "lazy loading" is not one of them — restructure instead.
- **Annotations that would create a cycle or pull a heavy dependency go under `TYPE_CHECKING`.**
- **Never depend transitively on something you import**; every direct dependency is declared, with
  a lower bound. **Never feature-detect with `try: import x`** in application code.

## Types and Data — Defaults

The decisions behind these are in the `python-types` skill; these are the ones that apply everywhere.

- **mypy `--strict` clean**, which is what makes the annotations mandatory. `T | None`, never
  `Optional[T]`; on a 3.12+ floor PEP 695 generics (`class Repository[T: Entity]`), never
  `TypeVar` + `Generic`.
- **Parameters take `collections.abc` ABCs, returns are concrete.** `Mapping[str, int]` in,
  `dict[str, int]` out. This is also what handles variance.
- **"Unknown" is spelled `object`, which forces narrowing; `Any` means "stop checking"**, and a
  function *returning* it spreads that silence to every caller. `Any` stays in the one position
  where a library fixes the signature and there is nothing to narrow to.
- **`@dataclass(frozen=True, slots=True, kw_only=True)` by default.** `frozen` is about mutability,
  `slots` about the attribute set, `kw_only` about the call site — the one usually forgotten:
  `Transfer(recipient_id, sender_id, amount)` type-checks and moves the money backwards. Positional
  construction survives only where the order is the concept — `Point(x, y)`, `Range(low, high)`.
  Drop `frozen` only for a genuine aggregate root that must change over time, and say so in its
  name — `Cart`, `Session`; derive copies with `dataclasses.replace()`.
- **`@override` on every overriding method**; `@final` on classes not designed for subclassing;
  `-> Never` on functions that always raise. **`Final` on module- and class-level constants** —
  worth the annotation because the checker then rejects reassignment and infers the literal type;
  a codebase that decides the reverse decides it once, not per constant.
- **`tuple` over `list` for fixed sequences**, `frozenset` over `set`, `MappingProxyType` to expose
  a dict read-only. **Never mutate arguments** — a function that does is named for it and annotated
  `MutableSequence`; everything else copies and returns. **Never return internal mutable state**
  from a getter.
- **A string that is user-facing or used twice is a constant** or an `Enum` member. The linter
  catches the magic *number*; a repeated literal string it will not.
- **`os` is correct where `pathlib` has no answer**, and only there: permission probing
  (`os.access`), process state (`os.getcwd`, `os.environ`), raw file descriptors — there is no
  `Path.can_write()`, and the linter that rewrites `os.path` into `Path` says nothing about these.

## Errors

- **Catch the most specific exception the guarded lines can actually raise.**
- **Messages include the identifying values**: `f"Order {order_id} cannot be shipped: status is
  {status}"`, not `"Invalid order"`.
- **Every package defines one root exception**, `<Package>Error(Exception)`, and all its own
  exceptions inherit from it, so callers can catch "anything from this library" with one clause.
  Inherit the closest stdlib type as well when the meaning matches:
  `UserNotFoundError(AppError, LookupError)`. Exceptions **carry data as attributes**, not only
  text.
- **Domain code raises domain exceptions.** A driver's or client's exception never escapes a public
  function — translate at the boundary, and preserve the cause with `raise … from`.
- **Never return `None`, `False`, `-1` or an empty collection to signal an error** in a function
  whose name promises a value. `None` is for `find_…`-style lookups where absent is normal.
- **Keep `try` blocks minimal**: only the statements that can raise; everything else before the
  `try` or in `else:`.
- **EAFP when the failure is rare and checking would race; LBYL when the check is cheap, atomic and
  the missing case is common.** Never both.
- **Catch at the level that can handle it** — retry, fall back, convert, report. A layer that can
  only log and re-raise should not catch at all. Log once, at the boundary that handles it.

```python
# WRONG — broad catch, swallowed cause, a try around everything, the error returned as None
def load_user(client: Client, user_id: UserId) -> User | None:
    try:
        response = client.get(f"/users/{user_id}")
        response.raise_for_status()
        return User.from_payload(response.json())
    except Exception:
        logger.error("failed")
        return None

# CORRECT — narrow try, translated with its cause, an error is never a return value
def load_user(client: Client, user_id: UserId) -> User:
    try:
        response = client.get(f"/users/{user_id}")
        response.raise_for_status()
    except HTTPStatusError as error:
        if error.response.status_code == HTTPStatus.NOT_FOUND:
            raise UserNotFoundError(user_id) from error
        raise UserServiceError(f"Fetching user {user_id} failed") from error
    return User.from_payload(response.json())
```

## Logging

- `logging.getLogger(__name__)`, once per module. `ERROR` means someone must look — never for an
  expected user mistake.
- **Never log secrets or PII** — tokens, passwords, card numbers, raw request payloads. Log
  identifiers, not objects, and structured fields (`extra={...}`) rather than text encoding them.
- Message style: lower-case start, no trailing punctuation, present tense, event first then
  context — `"payment captured"`, not `"Captured the payment successfully!"`.
- Configure logging **once** at the entry point, never in a library or on import. Timing and
  counters are metrics, not logs; never log in a hot loop.

## Resources

- **Anything acquired is released by a context manager** — files, locks, sessions, transactions,
  clients. Writing one, `ExitStack` for a dynamic number, and what cleanup may raise: the
  `python-wiring` skill, which also owns who closes what.

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

A legal header is exempt. A suppression keeps its reason on the suppressed line; when it will not
fit, the reason goes above and the code stays put, or the formatter's wrap silently voids it.

Forbidden: commented-out code, restating the code, section banners, author or date stamps, change
logs, and comments that describe a name instead of fixing it.

**A docstring's length follows publication, not complexity.** Where a generator renders it for
outside readers it is full — summary, parameters, return value, the errors this function's own
logic raises. Everywhere else it is one line and often absent: one reference library leaves nearly
half its public names undocumented. It states the contract and stops — `"""Return the shortest
route between two stops."""`, never `"""Run Dijkstra over the adjacency map."""`

### Comments and Docstrings Are Local

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

## Definition of Done

The formatter, the linters, the type checker in strict mode and the tests run first, in that
order, and each is clean with no new suppression. Then the eight checks no tool makes — the ones
skipped first under pressure:

- [ ] Every new identifier passes the Naming Self-Check, and survives the relocation test
- [ ] Every new module and class answers to one actor — name who would ask to change it
- [ ] Every helper has a reason to exist: reuse, a required callable, hidden complexity, a test
      seam, or a named predicate — and every class has one of the six triggers
- [ ] Constants sit at the top of the module, and **every top-level name not used outside is
      prefixed** — `find_unprefixed_names.py` reports nothing new
- [ ] No generically named unit contains concrete logic; no concrete rule lives in two places
- [ ] No `Any`, no magic literal, no `dict[str, Any]` crossing a layer; `@override` on every
      override, `Final` on every constant
- [ ] Every conversion preserves the cause; nothing returns `None`/`False`/`-1` to signal an error;
      errors are logged once, at the boundary, with no secrets or PII
- [ ] Every comment and docstring passes the relocation test; no credentials, URLs or
      environment-specific values are hardcoded

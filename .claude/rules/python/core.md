---
paths:
  - "**/*.py"
---

# Python — Core

What applies to every Python edit. `naming.md` loads with it; `testing.md` loads in test files.
Everything else is a skill, invoked when the work reaches it — by its own description, or by name:

| Skill | When |
|---|---|
| `python-types` | choosing between `Literal`/`Enum`/`NewType`/`TypedDict`, writing a generic, narrowing an unknown, reaching for `collections.abc` |
| `python-boundaries` | HTTP, queues, caches, serialization, timeouts, retries, time, money, identifiers |
| `python-wiring` | an entry point, where an object is built, a settings field, a layer argument |
| `python-async` | `async def`, threads, processes |
| `python-persistence` | an ORM, a transaction, a migration |
| `python-packaging` | a package other code imports: `__all__`, façade, `_internal`, optional extras, deprecation |
| `python-cli` | an entry point with an argument parser |
| `python-security` | input from outside: a body, a filename, a URL, a subprocess argument, a credential |
| `python-performance` | a path already measured and found slow |
| `python-examples` | an example that ships — docstring, README, `examples/` |
| `python-rules-authoring` | editing these rules or skills |
| `python-<library>` | the code imports that library — `pydantic`, `sqlalchemy`, `tenacity`, `niquests`, `orjson` |

Style, layout and mechanical complexity belong to the formatter, the linters and the type checker.
**Nothing here restates what a tool decides.** Which tools a project runs and how they are
configured is the project's business, not this document's. When a tool and this file disagree, the
tool wins and this file gets a PR.

Two things about living with those tools are not configuration and do belong here:

- **A suppression carries its rule code and its reason on the same line.** An unexplained one is a
  defect in its own right, and the count only ever ratchets down.
- **A limit is named, not raised.** One module with fifteen members must not buy every other module
  the right to fifteen: the limit stays and the file is named, with a reason that can be checked
  later and that stops applying when the file changes. When three files need the same escape, stop
  editing the configuration — the rule is describing something real about the architecture.

## When Rules Conflict

1. An explicit instruction from the person you are working with, for this task.
2. A `MUST` / `NEVER` rule in these files.
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
- **The next person is you, without the context.** One reason to change per unit; a new case is
  data or a new file, never a new branch in something that already works. Deleting must be as easy
  as adding.

## YAGNI, KISS, DRY

- **Build what today's requirement needs.** The cost of a speculative feature is not the hour spent
  writing it; it is that everything afterwards must keep it working. A generalisation built for one
  case is a guess about the second, and a wrong abstraction is harder to remove than the
  duplication it prevented, because callers have grown into it. A configuration option nobody sets
  and a parameter that is always the default are branches never known to work.
- **The simplest construction that fully solves the problem**, which is not the shortest one.
  Prefer the boring mechanism: a function over a class, a dict over a registry. Simplicity is
  measured at the point of *use*.
- **DRY is about knowledge, not text.** Two fragments that look identical but change for different
  reasons are not duplication — merging them couples two things that must be free to move apart,
  and the next change arrives as a parameter, then a flag, then a branch. Two fragments that must
  change together are duplication even when they look nothing alike: a limit enforced in a
  validator and repeated in a schema. **Wait for the third occurrence.** The cure is often a shared
  constant or a shared type, not a new unit that has to be named.

## Control Flow

- **Extract any condition with more than two operands into a named predicate.** The linter measures
  the complexity but cannot name the concept: `if _is_eligible_for_refund(order):` says what the
  three clauses meant.
- **State the positive case first**, and keep the shorter branch first. No double negatives — rename
  the flag instead.
- **`match` is structural pattern matching, not a `switch`.** Use it to destructure a closed union
  of variants or nested data; not to compare one scalar against constants, and not for two branches.
- **A bare lowercase name in a pattern binds, it does not compare.** Constants in patterns must be
  dotted — `case OrderStatus.PAID:`, never `case PAID:`. This is a silent logic bug, and it is the
  one thing about `match` worth memorising.
- **Every `match` over a union or `Enum` ends with exhaustiveness**: `case _: assert_never(value)`,
  or a named error. A silent fall-through is forbidden.
- **A factory dispatches through a mapping, not through `match`.** Kind in, builder out:
  `_FACTORY[source.kind](**options)`. Adding a kind is one entry, and the set is readable in one
  place instead of spread over branches.
- **A comprehension holds one transformation; anything more is a loop.** The judgement is about
  how much the reader can hold, not how much fits.
- **Write a generator function for any lazy sequence longer than a one-line expression**, and for
  anything reading from a stream, file, cursor or paginated API.

## Functions

- **One responsibility.** If describing it needs "and", split it.
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

**Never extract a function to have somewhere to put a docstring.** When the reasoning does not fit
in the code it goes inline as one "why" comment; a function created as a home for prose is a
comment with call overhead.

  ```python
  # WRONG — a stage name, one call site, and a docstring several times the size of the body
  def _log_outcome(stats: ImportStats | None, imported: int) -> None:
      """Record how the import ended and what the upstream feed answered.

      An empty result says nothing on its own: an expired API key, a rate-limit
      refusal and an honestly empty feed all look the same.
      """
      if stats is None:
          logger.info("import finished: imported=%s, no stats", imported)
          return
      logger.info("import finished: imported=%s requests=%s", imported, stats.requests)

  # CORRECT — inline, with the one fact the code cannot state itself
  def run_import(...) -> None:
      ...
      # Zero results is ambiguous without stats: an expired key, a rate limit and
      # a changed payload format all look identical in the log otherwise.
      if stats is None:
          logger.info("import finished: imported=%s, no stats", imported)
      else:
          logger.info("import finished: imported=%s requests=%s", imported, stats.requests)
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
  forces every caller to re-discover which it got. A union is fine when it is a **named type the
  caller handles uniformly** — `type Compared = frozenset[str] | str`, matched once and never
  asked about again; it is a defect when the caller has to reconstruct which branch ran. `None` is
  legitimate only for `find_…`-style lookups and procedures.
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
methods want to be grouped by feature** rather than by visibility has more than one responsibility
— split the class, do not reorder it.

Before reaching for a class, consider `functools.partial` or a closure, a frozen dataclass of
options as a parameter, or **splitting the module** — a long module of independent functions is
idiomatic Python and does not improve by growing a `self`.

  ```python
  # WRONG — the same client and settings threaded through every function
  def fetch_page(client: Client, settings: Settings, url: str) -> str: ...
  def fetch_listing(client: Client, settings: Settings, page: int) -> list[str]: ...
  def fetch_product(client: Client, settings: Settings, url: str) -> Product: ...

  # CORRECT — trigger 4: the repeated parameters were the constructor
  class ProductCatalogue:
      def __init__(self, client: Client, settings: Settings) -> None:
          self._client = client
          self._settings = settings

      def fetch_page(self, url: str) -> str: ...
      def fetch_listing(self, page: int) -> list[str]: ...
      def fetch_product(self, url: str) -> Product: ...
  ```

**SOLID, in the two forms that get broken**: one responsibility per class, and high-level modules
depend on abstractions — inject dependencies, never instantiate a collaborator inside a class. A
subclass is usable wherever its parent is; it never narrows a return type or widens a parameter.

### A Contract Is a Base Class with `@abstractmethod`; `Protocol` Is for Code You Do Not Control

A `Protocol` describes a *shape*; a base class the implementations inherit declares a *contract*.
Inside an application every implementation is yours to write, so the contract is nameable and the
inheritance is free — and it buys two things structural typing cannot:

- **The failure arrives at the class, not at the call site.** An implementation that forgot a
  method is an error where it is defined; a `Protocol` says nothing until someone passes it
  somewhere, and the error surfaces at that one call site, possibly far away.
- **The inheritance is the documentation.** `class SlackNotifier(Notifier)` states the intent in
  the line that defines the class; structural conformance is invisible until you diff the methods
  by hand.

**`@abstractmethod` alone gets the static guarantee; `ABC` adds a runtime one, and a metaclass.**
The type checker reports `Cannot instantiate abstract class "X" with abstract attribute "y"` from
the decorators alone — inheriting `abc.ABC` is not what makes that work. What `ABCMeta` adds is the
refusal at construction time, and what it costs is a metaclass: it conflicts with Django's model
metaclass, with mypyc compilation, and with any other library that wants that slot.

- **Default to `ABC`** in an application that compiles nothing and inherits no foreign metaclass.
  The runtime refusal is free there, and it catches the implementation built through a path the
  checker does not see.
- **Drop to a plain base class with `@abstractmethod`** when a metaclass is already spoken for, or
  the code is compiled. Neither guarantee the checker gives is lost.
- **Decide once per project and say which**, rather than mixing both shapes in one tree.

`@override` is orthogonal: it works on any base class, and it is mandatory either way — a renamed
method on the contract then becomes an error in every implementation.

Use `Protocol` when you cannot make the other side inherit: a third-party type, a duck-typed shape
someone else's code produces, a callback signature. **Never wrap a stdlib ABC in a `Protocol`** —
`Iterable`, `Mapping`, `Sized` already name those capabilities. **A class with no abstract methods
is not a contract**, whatever it is called.

### A Contract and Its Implementations Are One Directory

The contract is the reason the implementations exist, so they live together — and nothing else
does. One directory per capability, named for it; the contract in `base.py`; one module per
implementation, named for what makes it concrete; `__init__.py` exporting the contract and the
implementations and nothing more.

```
notifications/
    base.py         # Notifier(ABC) — the contract, and the errors it raises
    slack.py        # SlackNotifier(Notifier) — imports the Slack SDK, and is the only file that does
    email.py        # EmailNotifier(Notifier) — imports the SMTP client
    _templates.py   # private to the group: the bodies email.py renders
    __init__.py     # the contract and the implementations, nothing else
```

- **`base.py` is a position, not a `Base` class.** The module sits at the base of the group; the
  class inside it is still named for the capability — `Notifier`, never `BaseNotifier`. The two
  rules do not collide: one is about a file, the other about a class.
- **The contract's module imports nothing any implementation needs.** That is what makes the split
  worth having: a new implementation is a new file, and no existing file changes. An import of a
  driver in `base.py` silently makes every consumer of the contract depend on that driver.
- **A helper only one implementation uses is private and stays in the group** — `_templates.py`
  beside `email.py`, never in a shared `utils`.
- **No contract, no directory.** An implementation that will only ever be the only one is a single
  module named concretely, with no `base.py` above it. The group appears when the second
  implementation does, or when a test needs a fake — the same threshold that earns the contract.
- **A test fake is an implementation, and it lives with the tests.** The group is what ships.

### Dunders

Implement a dunder when the behaviour it represents is a natural fit, never to satisfy a style
preference. `__repr__` on every domain class that is not a dataclass: unambiguous, identifying
fields, no secrets. `__eq__` and `__hash__` come together or not at all — value objects get both
from `@dataclass(frozen=True)`; entities compare by identity and say so. Implementing a container
protocol means subclassing the matching `collections.abc` ABC, not hand-writing every dunder.

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

**The order is an intent, and Python enforces a dependency underneath it.** A name can only be
written after everything it is built from, so three positions yield: a validator a type alias is
built from comes before that alias and therefore before the logger; a constant derived from a class
cannot precede the class — and when that happens the module is holding two things, the shape and
what is computed from it, so **split it** and the constants land at the top again. Anything else
that will not fit the order is the same signal: look for the seam, do not renumber the list.

- **One reason to change per module.** A module mixing I/O, domain rules and presentation is split.
- **Size is a smell, not a limit.** The linters enforce a ceiling; the seam is your judgement.
- **No executable statements at import time** other than constants and the logger. No network
  calls, no file reads, no settings construction — these make imports slow, order-dependent and
  untestable. **`main()` is a function, never module-level code.**
- **A module name that reaches `sys.path` directly must not shadow a standard-library module** —
  `types`, `typing`, `json`, `logging`, `queue`, `io`, `abc` and their neighbours. This bites for a
  top-level module of a distribution, a loose script, or a scheduler DAG file. Nested inside a
  package the name is only ever visible as `mypackage.types`, so there is nothing to shadow, and
  the module is named after its contents — `internal/json.py`, `internal/io.py` are right. The
  linter does not draw that line (ruff `A005` fires on both), so a package that names modules after
  their contents turns `A005` off deliberately, once, with the reason written down.

### Every Top-Level Name Not Used Outside Takes an Underscore

Classes, functions, constants and type aliases alike. A settings section that only appears as a
field of the root, a row shape only its own repository builds, a policy only its own service
applies, a limit only its own function reads, an alias only its own signatures mention: each takes
the prefix — `_SectionSettings`, `_LOGGED_ANSWER`, `_Compared`. Without it the name reads as part
of the module's surface, and the first import from another module makes it one for good.

**Constants and aliases are the ones that get missed.** A class draws attention the moment it is
imported somewhere; a constant is quietly read from a second module, and by the time anyone looks
it has two homes and no owner.

The test is mechanical, and worth running over a package at once: for each top-level name, grep it
across the tree, drop the file that defines it, and prefix everything left with no hits. Run it
**after** the move that made a name internal — that is when a public name quietly stops being one.
A name a framework reaches through a decorator — a CLI command, a route handler, a fixture — has a
caller the grep cannot see, and is not covered.

### Imports

- **Import modules for modules, names for classes and functions.** Then call `invoices.issue(...)`
  or `issue_invoice(...)` — never a three-level attribute chain, which hides what is used.
- **A function-level import is flagged, and exactly three reasons buy the suppression**: breaking a
  genuine circular import, loading a heavy or optional implementation on demand, and a façade that
  exports implementations whose libraries are separate extras. Each carries the reason on the line.
  Generic "lazy loading" is not one of them — restructure instead.
- **Annotations that would create a cycle or pull a heavy dependency go under `TYPE_CHECKING`.**
- **Rename on import only for a community-standard alias or an actual clash** — never to shorten.
- **No side effects on import.** Importing a module must be free, idempotent, order-independent.
- **Never depend transitively on something you import**; every direct dependency is declared, with
  a lower bound. **Never feature-detect with `try: import x`** in application code.

## Types and Data — Defaults

The decisions behind these are in the `python-types` skill; these are the ones that apply everywhere.

- **mypy `--strict` clean**, which is what makes the annotations mandatory. `T | None`, never
  `Optional[T]`; PEP 695 generics (`class Repository[T: Entity]`), never `TypeVar` + `Generic`.
- **Parameters take `collections.abc` ABCs, returns are concrete.** `Mapping[str, int]` in,
  `dict[str, int]` out. This is also what handles variance.
- **`Any` is rarely the type you want, and never the one you reach for first.** It does not mean
  "unknown", it means "stop checking" — and a function *returning* `Any` spreads that silence to
  every caller. `object` is what "unknown" is spelled as: it forces narrowing. Reach for `Any` when
  a library fixes the signature and there is nothing to narrow to; keep it in that one position and
  out of the rest.
- **`@dataclass(frozen=True, slots=True, kw_only=True)` by default.** `frozen` is about mutability,
  `slots` about the attribute set, `kw_only` about the call site. The third is the one usually
  forgotten and the one that pays daily: a field added in the middle stops being a silent breaking
  change, and two adjacent fields of the same type can no longer be swapped by a caller.
  `_Rejected(order.id, reason, title)` reads fine and is wrong in three ways. Positional
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
- **Prefer pure functions**: input in, output out, no reads of global state. Push I/O to the edges.
- **A string that is user-facing or used twice is a constant** or an `Enum` member. The linter
  catches the magic *number*; a repeated literal string it will not.
- **`os` is correct where `pathlib` has no answer**, and only there: permission probing
  (`os.access`), process state (`os.getcwd`, `os.environ`), raw file descriptors. The case that
  costs an evening: a native library refuses to write its output file and reports only an exit
  code, because the previous build was left behind by a container running as root. There is no
  `Path.can_write()` to check first, and the linter that rewrites `os.path` calls into `Path` has
  nothing to say about this one.

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
- **Raise as early as possible** — validate at the boundary, fail on the first invalid value.
- **Never return `None`, `False`, `-1` or an empty collection to signal an error** in a function
  whose name promises a value. `None` is for `find_…`-style lookups where absent is normal.
- **Never use exceptions for ordinary control flow.**
- **Keep `try` blocks minimal**: only the statements that can raise; everything else before the
  `try` or in `else:`.
- **EAFP when the failure is rare and checking would race; LBYL when the check is cheap, atomic and
  the missing case is common.** Never both.
- **Catch at the level that can handle it** — retry, fall back, convert, report. A layer that can
  only log and re-raise should not catch at all. Log once, at the boundary that handles it.

  ```python
  # WRONG — broad catch, swallowed cause, huge try, error as None
  def load_user(user_id: int):
      try:
          response = client.get(f"/users/{user_id}")
          user = User(**response.json())
          cache.set(user_id, user)
          return user
      except Exception:
          logger.error("failed")
          return None

  # CORRECT — narrow try, translated with cause, never returns None for an error
  def load_user(client: Client, cache: UserCache, user_id: UserId) -> User:
      try:
          response = client.get(f"/users/{user_id}")
          response.raise_for_status()
      except HTTPStatusError as error:
          if error.response.status_code == HTTPStatus.NOT_FOUND:
              raise UserNotFoundError(user_id) from error
          raise UserServiceError(f"Fetching user {user_id} failed") from error

      user = User.from_payload(response.json())
      cache.set(user_id, user)
      return user
  ```

## Logging

- One logger per module, obtained by module name, defined at the top.
- Levels have fixed meaning: `DEBUG` diagnostic detail; `INFO` normal business events; `WARNING`
  recoverable anomaly; `ERROR` an operation failed and someone must look; `CRITICAL` the process
  cannot continue. Not `ERROR` for an expected user mistake.
- **Never log secrets or PII** — tokens, passwords, card numbers, raw request payloads. Log
  identifiers, not objects, and structured fields (`extra={...}`) rather than text encoding them.
- Message style: lower-case start, no trailing punctuation, present tense, event first then
  context — `"payment captured"`, not `"Captured the payment successfully!"`.
- Configure logging **once** at the entry point, never in a library or on import. Timing and
  counters are metrics, not logs; never log in a hot loop.

## Resources

- **Anything acquired is released by a context manager**: files, locks, sessions, transactions,
  clients, temporary state. `try/finally: close()` is only for *implementing* one.
- **Own resources get `@contextmanager`** (or the async form): yield exactly once, clean up in
  `finally`, and name it for the lifecycle — `managed_engine`. A class with `__enter__`/`__exit__`
  only when the object has other methods besides those two.
- **A dynamic number of resources → `ExitStack`**, which is also the composition root's shutdown
  mechanism. Transferring ownership out of a function is `stack.pop_all()`.
- **`__exit__` propagates by default.** Cleanup must not raise over the original error; if it can
  fail, catch and log its failure separately.
- **No hidden global mutation managers.** One that flips module or process state (`chdir`,
  environment variables, logging config) is test poison — fine in tests and entry points, never in
  library or service code.

## Documentation

**Which names need a docstring is the linter's decision**; what goes inside one is not.

- **A module docstring is published text, and that decides where it is required.** A module on the
  public surface gets one: it is what the documentation generator renders above the API, and its
  absence is a hole in the docs rather than a missing comment — `pydantic` writes one in 33 of its
  34 public modules and in half of its private ones. Inside a private area, write the line when the
  module's place is not obvious from its name: why it exists apart from its neighbour, or a
  constraint governing the whole file. A mandate everywhere produces `"""Throttling base
  classes."""` above `throttling/base.py` — the filename with a full stop.
- **A docstring states the contract and stops**: what the thing is, its parameters, its return
  value, the errors its own logic raises, its side effects. Not how it works, not what it used to
  do, not a number from a benchmark — that belongs in the commit message.
- **An inline comment is written only when one of the kinds below applies.** Code carries its own
  meaning through names; a comment that restates it is a name that should have been fixed.

**When a comment is unavoidable it explains *why*, never *what*.** Exactly these kinds are allowed:
a workaround or non-obvious constraint, with a reference a reader can verify or remove later;
`# TODO(username): description` with an owner; a suppression with its rule code and reason on the
suppressed line — and when the line cannot hold both, the reason goes immediately above and the
code stays put, because the formatter wraps an over-long line and a `noqa` carried onto a
continuation stops suppressing anything, silently; a warning about a non-obvious consequence of
this block; a legal header.

Forbidden: commented-out code, restating the code, section banners, author or date stamps, change
logs, and comments that describe a name instead of fixing it.

### Comments and Docstrings Are Local

A comment describes **only the code in its own block**; a docstring describes **only the contract
of the thing it is attached to**. Both must stay true when anything outside changes.

- **Scope equals placement.** A comment inside a loop body is about that iteration. A function
  docstring covers its parameters, return value, raised errors and side effects — never wider.
- **No callers, no collaborators, no ordering.** `# called by OrderService.place_order()`,
  `# must run before _flush()`, `# keep in sync with schemas/order.py`, `"""Called by the nightly
  batch job."""`, `"""Must be called after load_config()."""` — each rots the moment the other side
  changes, and nothing checks it. If two places must agree, encode the coupling in code: one shared
  constant, one shared type, one call.
- **Contract, not implementation.** `"""Return the shortest route between two stops."""`, not
  `"""Run Dijkstra over the adjacency map."""`
- **`Raises:` lists what this function's own logic raises**, never what an injected dependency
  might propagate.
- **No cross-docstring continuity** — never "as described above", "see the base class", "same as
  `save()` but async". Either the override adds nothing, and gets no docstring, or it has its own
  contract stated in full. No changelogs, authors, dates or TODOs.
- **The relocation test.** Cut the block and paste it into another module: if the comment becomes
  wrong, meaningless, or unverifiable, it was leaking. **If a comment can only be written by
  referring elsewhere, the design is wrong**, not the comment.

  ```python
  # WRONG — leaks into other code; every line rots silently
  class OrderValidator:
      # NOTE: OrderService calls this before _persist(); do not reorder
      # keep the limit in sync with schemas/order.py MAX_ITEMS
      def validate(self, order: Order) -> None:
          if len(order.items) > 100: ...   # matches the API schema limit

  # CORRECT — the coupling is code, and the only comment is a self-contained reason
  MAX_ORDER_ITEMS: Final = 100        # the schema imports this too: one source of truth

  class OrderValidator:
      def validate(self, order: Order) -> None:
          if len(order.items) > MAX_ORDER_ITEMS: ...
  ```

  The general recipe for a leaking docstring: "must run after taxes are calculated" stops being
  prose and becomes a type — `PricedOrder` instead of `Order`. What you want to explain in words
  usually belongs in the signature.

## Definition of Done

The formatter, the linters, the type checker in strict mode and the tests run first, in that
order, and each is clean with no new suppression. Then the seven checks no tool makes — the ones
skipped first under pressure:

- [ ] Every new identifier passes the Naming Self-Check, and survives the relocation test
- [ ] Every helper has a reason to exist: reuse, a required callable, hidden complexity, a test
      seam, or a named predicate — and every class has one of the six triggers
- [ ] Constants sit at the top of the module, and **every top-level name not used outside is
      prefixed** — grep each one across the tree, drop its own file, prefix what has no hits left
- [ ] No generically named unit contains concrete logic; no concrete rule lives in two places
- [ ] No `Any`, no magic literal, no `dict[str, Any]` crossing a layer; `@override` on every
      override, `Final` on every constant
- [ ] Every conversion preserves the cause; nothing returns `None`/`False`/`-1` to signal an error;
      errors are logged once, at the boundary, with no secrets or PII
- [ ] Every comment and docstring passes the relocation test; no credentials, URLs or
      environment-specific values are hardcoded

---
paths:
  - "**/*.py"
---

# Python Code Quality — Core

Principles, functions, classes, errors, logging, resources, concurrency, documentation and the
Definition of Done. The companion files cover typing, naming, architecture, testing and the standard
library; each is loaded automatically by the `paths:` in its own front matter.

Two more sets sit alongside. `tooling/` covers the environment, the linters and the hooks; those
load with the configuration file each tool owns. `libraries/` covers third-party libraries; open the
one for the library you are touching, since which of them applies depends on the imports rather than
on the path.

Style, layout and mechanical complexity are enforced by the project's linters, formatter and type
checker. **This document does not restate anything a tool can decide** — a rule a linter can check
is a linter's job, and a rule that needs judgement is this document's job. When the two disagree,
the tool wins and this document gets a PR. Never disable a rule to make code pass: a suppression
carries its code and a reason on the same line, and an unexplained one is a defect in its own right.

## When rules conflict

Resolve in this order:

1. An explicit instruction from the person you are working with, for this task.
2. A `MUST` / `NEVER` rule in these files.
3. What `pydantic` or `sqlalchemy` does in the same situation — they are large, long-lived, and
   have paid for their choices.
4. Consistency with the surrounding code of the same package.
5. The default (*prefer*) in these files.
6. Your own judgement — and say so, rather than letting it read as a rule.

If a rule is wrong for the situation, the fix is to change the rule, with the reasoning — not a
silent exception in code. A rule that is regularly worked around is a rule that needs changing.

## Core Principles

Every rule in this set serves these, in this order. When two rules conflict, the earlier principle
wins.

1. **Correct** — the code does what its name and signature promise, for every input the types
   allow, and fails loudly otherwise.
2. **Readable** — a teammate who has never seen the file understands it top-down without opening
   other files. Names carry the meaning; comments are the exception.
3. **Simple** — the least machinery that solves today's problem: no speculative abstractions, no
   helper without a reason, no class without state or a contract.
4. **Typed** — illegal states are unrepresentable; the checker, not the reviewer, catches the
   mistake.
5. **Fast enough, by measurement** — algorithmic sanity always; anything beyond that only with a
   profile in hand.

**Non-negotiables**: mypy strict and the linters pass with zero suppressions you cannot justify;
nothing is handed over that fails the Definition of Done.

## YAGNI, KISS, DRY

Three names for the same discipline, and all three are misquoted often enough to be worth stating
precisely.

### YAGNI — You Aren't Gonna Need It

**Build what today's requirement needs, and nothing beyond it.** The cost of a speculative feature
is not the hour spent writing it; it is that everything afterwards must keep it working — it gets
tested, typed, refactored around, and read by everyone who passes.

- A generalisation built for one case is a guess about the second. The guess is usually wrong, and a
  wrong abstraction is harder to remove than the duplication it was meant to prevent, because
  callers have grown into it by then.
- A configuration option nobody sets, a hook nobody registers, a parameter that is always the
  default: each is a branch that is never exercised and therefore never known to work.
- The honest answer to "we might need it later" is to make the change easy to *make* later — a clear
  seam, a small interface — not to make it now.

### KISS — Keep It Simple

**The simplest construction that fully solves the problem**, which is not the shortest one. A dense
one-liner that has to be decoded is complexity moved out of the code and into the reader.

- Prefer the boring mechanism: a function over a class, a dict over a registry, a loop over a
  comprehension that needs a comment.
- Cleverness that needs explaining has already failed. If the explanation cannot be deleted, the
  code should be.
- Simplicity is measured at the point of *use*. A construct that makes the implementation elegant
  and every call site awkward has moved cost onto more people than it saved it from.

### DRY — Don't Repeat Yourself

**DRY is about knowledge, not about text.** The rule is that every piece of knowledge has one
authoritative home — not that no two lines may look alike.

- **Two fragments that look identical but change for different reasons are not duplication.**
  Merging them couples two things that must be free to move apart, and the next change to one of
  them arrives as a parameter, then a flag, then a branch. Ask what would have to change together,
  not what looks the same.
- **Two fragments that must change together are duplication even when they look nothing alike** — a
  limit enforced in a validator and repeated in a schema, a status decoded in two adapters.
- **Wait for the third occurrence.** Two call sites are not yet evidence of a rule; they are a
  coincidence often enough that acting on them is how the wrong abstraction gets built.
- The cure is not always a shared function. A shared constant, a shared type, or one call in the
  right place removes the duplication of *knowledge* without inventing a unit that has to be named.

## Control Flow and Expressions

Only what a linter cannot decide; everything mechanical about expressions is already a tool's job.

- **Extract any condition with more than two operands into a named predicate.** The linter can
  measure the complexity but not name the concept: `if _is_eligible_for_refund(order):` says what
  the three clauses meant.
- **State the positive case first**, and keep the shorter branch first. No double negatives — rename
  the flag instead.
- **`match` is structural pattern matching, not a `switch`.** Use it to destructure a closed union
  of variants or nested data. Do not use it to compare one scalar against constants, and do not use
  it for two branches.
- **A factory dispatches through a mapping, not through `match`.** Kind in, builder out:
  `_FACTORY[source.kind](**options)`. The mapping is the dispatch table — adding a kind is one
  entry, and the set of kinds is readable in one place instead of spread over branches. Even a
  lazily-imported driver fits: the mapping holds local builders, and the builder does the import.
- **Every `match` over a union or `Enum` ends with exhaustiveness**: cover all variants and close
  with `case _: assert_never(value)`, or raise a named error in `case _:`. A silent fall-through is
  forbidden.
- **A bare lowercase name in a pattern binds, it does not compare.** Constants in patterns must be
  dotted (`case OrderStatus.PAID:`, never `case PAID:`) — this is a silent logic bug, not a style
  slip, and it is the one thing about `match` worth memorising.
- **Comprehension for one transformation plus at most one filter**; a loop otherwise. The judgement
  is about how much the reader can hold, not about how much fits.
- **Write a generator function for any lazy sequence longer than a one-line expression**, and for
  anything reading from a stream, file, cursor or paginated API.
- **Strings that are user-facing or reused in more than one place are constants** (or `Enum`
  values), not inline literals.

## Function Design

- **MUST** keep every function to a single responsibility.
- Extracted helpers **MUST** have names that make the parent readable as plain English — the reader
  understands the full flow without inspecting each helper.
- Group related parameters into a frozen dataclass rather than growing the signature.

### Extraction Must Pay for Itself

Extracting a helper is not free. The name, the signature, the docstring and the jump the reader has
to make are an **interface**, and the interface is paid for by everything around it. A helper is
justified only when it gives back more than it costs. Ousterhout's terms: deep functions hide a lot
behind a small interface; shallow ones expose an interface as complex as their body and hide
nothing.

**Extract when at least one is true:**

1. **Real reuse** — two or more call sites *today*. Not "we might need it later".
2. **Required as an object** — a callback, a `key=` function, a value in a dispatch table, a
   framework hook. There is no choice here, and size is irrelevant.
3. **It hides genuine complexity** — the body is non-obvious, and afterwards the **name is enough**:
   the caller never needs to open it.
4. **The parent would otherwise break its limits** — and the extraction restores one level of
   abstraction rather than just moving lines out of sight.
5. **It needs its own test seam** — the logic must be verifiable independently of the parent.
6. **It is a named predicate** — a condition that deserves a name. Short predicates are explicitly
   allowed; naming a condition *is* the abstraction.

**Do not extract when all of these hold:** one call site, a short and obvious body, and the parent
stays within its limits. Keep it inline, separated by a blank line as its own paragraph, with at
most one "why" comment.

**Shallow-helper tests — if any fires, inline it:**

- **Interface test.** Signature plus docstring is longer than the body.
- **Name test.** To know what happens, the reader opens the body anyway. The abstraction did not
  happen.
- **Entanglement test.** Reading the parent requires flipping into the helper and back.
- **Parameter test.** The helper needs three or more parameters only to rebuild the parent's
  context. The code belongs in the parent.
- **Wrapper test.** The body is a single library call, a single `logger.*`, or one arithmetic
  expression. That is a rename, not an abstraction.
- **Temporal-decomposition test.** The name describes a *stage* (`_step_two`, `_after_parse`,
  `_log_outcome`) rather than a standalone action. Splitting along the time axis instead of along
  knowledge produces helpers that can never be understood alone.

**Never extract a function to have somewhere to put a docstring.** When the reasoning does not fit
in the code, it goes inline as one "why" comment. A function created as a home for prose is a
comment with call overhead.

  ```python
  # WRONG — single call site, a name that describes a stage, and a docstring several
  # times the size of the body
  def _log_outcome(stats: ImportStats | None, imported: int) -> None:
      """Record how the import ended and what the upstream feed answered.

      An empty result says nothing on its own: an expired API key, a rate-limit
      refusal, a changed payload format and an honestly empty feed all look the
      same. Only the request statistics tell them apart.
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

  ```python
  # WRONG — wrapper test: each helper is one library call behind a new name
  def _now() -> datetime:
      return datetime.now(UTC)

  def _is_empty(items: Sequence[Item]) -> bool:
      return len(items) == 0

  # CORRECT — call the library; `if not items` needs no name
  timestamp = datetime.now(UTC)
  if not items:
      ...
  ```

  ```python
  # WRONG — parameter test: five parameters exist only to rebuild the caller's context
  def _build_headers(token: str, tenant: str, request_id: str, locale: str, version: str) -> dict[str, str]:
      ...

  # CORRECT — the context is one object, so the helper has one parameter and a real interface
  @dataclass(frozen=True, slots=True)
  class RequestContext:
      token: str
      tenant: str
      request_id: str
      locale: str
      version: str

      def to_headers(self) -> dict[str, str]: ...
  ```

  ```python
  # WRONG — temporal decomposition: helpers named after stages, none understandable alone
  def run(raw: bytes) -> None:
      data = _step_one(raw)
      data = _step_two(data)
      _step_three(data)

  # CORRECT — name the actions, or keep it inline when each is two lines
  def import_orders(raw: bytes, repository: BaseOrderRepository) -> None:
      payload = deserialize(raw)
      orders = [Order.from_payload(item) for item in payload["items"]]
      repository.save_all(orders)
  ```

  ```python
  # CORRECT — three lines, one call site, and still justified: rule 6, the condition gets
  # a name the `if` cannot express, and rule 5, it is worth testing alone
  def _is_stale(entry: CacheEntry, now: datetime, ttl: timedelta) -> bool:
      return now - entry.written_at > ttl

  # CORRECT — rule 3: the body is non-obvious, the name fully replaces reading it
  def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
      raw = base64.urlsafe_b64decode(cursor.encode() + b"==")
      written_at, entity_id = raw.decode().split("|", maxsplit=1)
      return datetime.fromisoformat(written_at), UUID(entity_id)
  ```

### Function Body Layout

A function body reads top-to-bottom in a fixed rhythm: **guards → work → result**.

1. **Guard clauses first.** Validate inputs and handle trivial cases with an immediate `return` or
   `raise`.
2. **The happy path at indentation level 1.** After the guards, the main logic must not be nested
   inside an `if`. If it is, invert the condition and return early.
3. **One blank line between logical steps**, none inside a step. More than three steps → extract.
4. **Single exit type.** A function returns one static type — never `str | list[str] | None`
   depending on the branch. `None` is legitimate only for `find_…`-style lookups and procedures.
5. **Result last.** Compute into a well-named local, then return it — except trivial one-expression
   functions.

Rules the linter cannot see:

- **No boolean flag parameters.** `export(orders, as_csv=True)` is two functions, or one taking a
  `Literal`/`Enum` format. A flag always means the function does two things; the linter flags the
  positional call, not the design.
- **Parameters are ordered: subject, then required inputs, then optional configuration.** Injected
  dependencies come first — they are the function's environment.
- **Do not reach outside.** A function uses only its parameters and module-level constants. No
  global mutable state, no `settings` import, no clock or randomness buried deep inside — take them
  as parameters so the function is testable.
- **Compute or do, not both** (command–query separation): a function that returns a value has no
  side effects; a function with side effects returns `None`, or a small object describing what
  happened.
- **One level of abstraction per function.** An orchestrator contains only calls at its own level;
  it does not also format a string or open a socket.
- **Locals are introduced where they are used.** A local used once on the next line is usually
  noise — inline it unless the name adds meaning.
- **No output parameters**: never pass a collection to be filled. Return a new one.

  ```python
  # WRONG — arrow-shaped, flag parameter, two return types, reaches outside
  def get_shipping_cost(order, express=False):
      if order is not None:
          if order.items:
              if order.country in EU_COUNTRIES:
                  return order.weight_kg * (settings.EU_EXPRESS_RATE if express else settings.EU_RATE)
              return "unsupported"
          return 0
      return None

  # CORRECT — guards, flat happy path, one return type, dependencies passed in
  def calculate_shipping_cost(order: Order, rates: ShippingRates, *, speed: ShippingSpeed) -> Money:
      if not order.items:
          return Money.zero()
      if order.country not in EU_COUNTRIES:
          raise UnsupportedDestinationError(order.country)

      return order.weight_kg * rates.for_speed(speed)
  ```

## Class Design and SOLID Principles

### Classes vs Functions

Functions are the default; a class is an upgrade that must be triggered. A Python module is already
a namespace with "methods", so a class has to offer something a module does not.

**Write a class when at least one is true:**

1. **State survives between calls** — a token bucket, a connection pool, an accumulator, an open
   session.
2. **Invariants tie values together** — data that must stay consistent (`Money`, `DateRange`). That
   is a frozen dataclass with methods, not a "service" class.
3. **The behaviour must be swappable** — two or more implementations behind one contract, or a test
   needs a fake.
4. **Several operations share the same dependencies** — when three or more functions in a module
   take the same two or more parameters, those repeated parameters *are* a constructor that has not
   been written yet.
5. **There is a lifecycle** — acquire/release, `__enter__`/`__exit__`, `close()`.
6. **A framework demands it** — `Enum`, `Exception`, a dataclass. No choice.

**Functions suffice when** the work is a pure input→output transformation, there is no state, there
will be one implementation, and dependencies are passed by the caller and differ per call.

**Anti-patterns — reliable signs of a class that should not exist:**

- **A class with `__init__` and one method.** That is a function with extra steps:
  `Calculator(x).calculate()` instead of `calculate(x)`.
- **A class of only `@staticmethod`s.** A module wearing a costume.
- **A class as a box for constants** — those are module constants or an `Enum`.
- **A stateless "service" with no dependencies** — a namespace with `self` attached.

**Consider these before reaching for a class:**

- `functools.partial` or a closure, to fix one or two arguments.
- A single frozen dataclass of options passed as a parameter, instead of a five-field constructor.
- **Splitting the module** — often the real answer. A long module of independent functions is
  idiomatic Python and does not improve by growing a `self`.

  ```python
  # WRONG — stateless class: the same functions, plus self and ceremony
  class ReceiptParser:
      def __init__(self) -> None: ...

      def parse_title(self, html: str) -> str: ...
      def parse_salary(self, html: str) -> Money | None: ...

  # CORRECT — module-level functions
  def parse_title(html: str) -> str: ...
  def parse_salary(html: str) -> Money | None: ...
  ```

  ```python
  # WRONG — the same client and settings threaded through every function
  def fetch_page(client: Client, settings: Settings, url: str) -> str: ...
  def fetch_listing(client: Client, settings: Settings, page: int) -> list[str]: ...
  def fetch_product(client: Client, settings: Settings, url: str) -> Product: ...

  # CORRECT — the repeated parameters were the constructor
  class ProductCatalogue:
      def __init__(self, client: Client, settings: Settings) -> None:
          self._client = client
          self._settings = settings

      def fetch_page(self, url: str) -> str: ...
      def fetch_listing(self, page: int) -> list[str]: ...
      def fetch_product(self, url: str) -> Product: ...
  ```

**MUST** apply all five SOLID principles in every class and module:

### S — Single Responsibility Principle
Each class does exactly one thing. If you can describe a class with "and", split it.

### O — Open/Closed Principle
Classes are open for extension, closed for modification. Add behaviour by subclassing or composing,
not by editing existing code.

### L — Liskov Substitution Principle
Subclasses must be usable wherever their parent is expected. Never narrow a return type or widen an
accepted parameter type in a subclass.

### I — Interface Segregation Principle
Prefer many small, focused interfaces over one large one. Use `Protocol` to define the minimal
surface each consumer actually needs.

### D — Dependency Inversion Principle
High-level modules depend on abstractions. Inject dependencies; never instantiate collaborators
inside a class. The same inversion applies to imports: the library behind an implementation is
imported only in that implementation's module.

### Abstract Base Classes and Protocols

- **Use `Protocol`** to define structural interfaces — prefer it over `ABC` when you need no shared
  implementation.
- **Use `ABC`** when the base provides shared behaviour that subclasses inherit, or when a strict
  hierarchy must be enforced.
- **NEVER** use a bare class as an interface. Every contract is a `Protocol` or an ABC.

  ```python
  # Protocol — structural, no shared implementation; every contract starts with Base
  class BaseNotifier(Protocol):
      def send(self, recipient: str, message: str) -> None: ...

  # ABC with shared behaviour — same Base prefix, mixed with real methods
  class BaseRepository[T](ABC):
      @abstractmethod
      def find(self, entity_id: int) -> T | None: ...

      @abstractmethod
      def save(self, entity: T) -> None: ...

      def get(self, entity_id: int) -> T:      # shared behaviour justifies ABC over Protocol
          entity = self.find(entity_id)
          if entity is None:
              raise EntityNotFoundError(entity_id)
          return entity
  ```

### Method Ordering Within a Class

A class is read top-down like an article: interface first, implementation details last. Two
principles decide the order — **visibility** (public → private) and **step-down** (a method appears
below the method that calls it, as close to it as possible).

1. Class docstring.
2. Class attributes and constants; dataclass field annotations.
3. `__slots__`, if present.
4. `__init__` / `__post_init__`.
5. Alternative constructors — `@classmethod` named `from_…`.
6. Remaining dunder methods — they define the object's contract, so they sit next to the
   constructors.
7. `@property` accessors, each setter immediately after its getter.
8. **Public methods**, ordered by importance: the primary operation first. In an ABC or `Protocol`,
   abstract methods come first — they *are* the contract.
9. **Private methods**, after all public ones, in call order.
10. `@staticmethod` — last, or directly below its single caller. A static method that does not use
    the class at all is a module-level function; move it.

- **Never interleave** public and private methods. A reader who stops at the first underscore must
  have seen the whole public interface.
- **Group by visibility, not by feature.** If a class is large enough that grouping by feature seems
  necessary, it violates SRP — split the class instead of reordering it.
- **Do not sort alphabetically.** Alphabetical order destroys the step-down flow and says nothing
  about importance.

## Dunder (Magic) Methods

- **MUST** implement a dunder whenever the behaviour it represents is a natural fit — do not add a
  boilerplate wrapper method when a protocol dunder achieves the same thing idiomatically.
- `__repr__` on every domain class that is not a dataclass: unambiguous, includes the identifying
  fields, never secrets. `__str__` only when there is a human-facing rendering distinct from the
  repr.
- `__eq__` and `__hash__` come together or not at all; value objects get both from
  `@dataclass(frozen=True)`; entities compare by identity and say so explicitly.
- Implementing a container protocol means subclassing the matching `collections.abc` ABC, not
  hand-writing every dunder.
- **DO NOT** implement a dunder to satisfy a style preference. Add them only when they make the
  class behave like a natural Python type.

## Error Handling

- **MUST** catch the most specific exception that the guarded lines can actually raise.
- Provide messages that include the identifying values: `f"Order {order_id} cannot be shipped:
  status is {status}"`, not `"Invalid order"`.

### Exception Hierarchy

- Every package defines one root exception, `<Package>Error(Exception)`, and all its own exceptions
  inherit from it. Callers can then catch "anything from this library" with one clause. `sqlalchemy`
  is the reference: everything descends from `SQLAlchemyError`, and the leaves name the failure
  precisely (`NoSuchColumnError`, `AmbiguousForeignKeysError`).
- Inherit from the closest stdlib type as well when the meaning matches:
  `UserNotFoundError(AppError, LookupError)`.
- Exceptions **carry data as attributes**, not only text: `UserNotFoundError(user_id)` stores
  `self.user_id`.
- Domain code raises domain exceptions; it **never** lets a driver's or a client's exception escape
  a public function. Translate at the boundary.

### Raising

- Raise as early as possible — validate at the boundary, fail on the first invalid value, never
  accumulate a bad state and fail later.
- **Never return `None`, `False`, `-1` or an empty collection to signal an error** in a function
  whose name promises a value. Raise. Return `None` only from `find_…`-style lookups where "absent"
  is a normal outcome.
- **Never use exceptions for ordinary control flow** — raising to break out of nested loops, or
  catching to end an iteration.

### Catching

- **Keep `try` blocks minimal**: wrap only the statements that can raise. Everything else goes
  before the `try` or into `else:`.
- **EAFP vs LBYL:** prefer EAFP when the failure is rare and checking would race; prefer LBYL when
  the check is cheap, atomic, and the "missing" case is common. Never do both.
- **Catch at the level that can handle the error** — retry, fall back, convert, report. A layer that
  can only log and re-raise should not catch at all.
- Every `except` that swallows must log and either return a documented fallback or re-raise.
  Logging and re-raising at every layer produces duplicate stack traces — log once.
- **Use `ExceptionGroup` / `except*`** for concurrent failures from a `TaskGroup`; do not flatten to
  the first exception.

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
  class UserNotFoundError(UserServiceError, LookupError):
      def __init__(self, user_id: UserId) -> None:
          super().__init__(f"User {user_id} not found")
          self.user_id = user_id

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

- One logger per module, obtained by module name and defined at the top.
- Levels have fixed meaning: `DEBUG` — diagnostic detail; `INFO` — normal business events;
  `WARNING` — recoverable anomaly, nothing lost; `ERROR` — an operation failed and someone must
  look; `CRITICAL` — the process cannot continue. Do not log `ERROR` for expected user mistakes.
- Log **once**, at the boundary that handles the error.
- **Never log secrets or PII**: tokens, passwords, card numbers, raw request payloads. Log
  identifiers, not objects.
- Use structured fields (`extra={...}`) rather than encoding them in the message.
- Message style: lower-case start, no trailing punctuation, present tense, event first then
  context: `"payment captured"`, not `"Captured the payment successfully!"`.
- Configure logging **once** at the entry point, never inside libraries or on import. Libraries
  obtain loggers; they never add handlers or set levels.
- Timing, counters and rates belong to metrics, not logs; never log inside a hot loop.

## Context Managers and Resource Management

- **Anything acquired is released by a context manager**: files, locks, sessions, transactions,
  clients, temporary state. `try/finally: close()` is only for *implementing* a context manager,
  never for using a resource that has one.
- **Own resources get `@contextmanager`** (or `@asynccontextmanager`): yield exactly once, clean up
  in `finally`, and name it for the resource lifecycle (`managed_engine`, `acquired_lock`). A full
  class with `__enter__`/`__exit__` only when the object has other methods besides enter and exit.
- **The part before `yield` is cheap and infallible where possible** — do heavy or failure-prone
  acquisition inside, so cleanup logic stays uniform; never return a half-initialized resource.
- **A dynamic number of resources → `ExitStack` / `AsyncExitStack`**, which is also the composition
  root's shutdown mechanism. Transferring ownership out of a function is `stack.pop_all()` — the
  only sanctioned way to return an open resource.
- **`__exit__` decides about exceptions deliberately**: propagate by default. Swallowing is subject
  to the same rules as `except`. Cleanup must not raise over the original error; if it can fail,
  catch and log its failure separately.
- **Most managers are single-use** — entering twice is a bug. If reuse is supported, a test proves
  it.
- **No hidden global mutation managers.** A context manager that flips module or process state
  (`chdir`, environment variables, logging config) is test poison — acceptable in tests and entry
  points, never in library or service code.

## Asyncio and Concurrency

### Asyncio

- **Never block the event loop**: no sync drivers, no `time.sleep`, no heavy CPU work inside
  `async def`.
- **Blocking calls are offloaded, not tolerated**: `await asyncio.to_thread(...)` for I/O-bound sync
  code. CPU-bound work goes to a **shared** process pool created once in the composition root and
  passed in — never an executor constructed per call, which pays pool startup every time and breaks
  concurrency limits.
- **Every `await` on external I/O runs under a deadline** — the client's configured timeout or an
  explicit `asyncio.timeout(...)` scope. An unbounded `await` is the async equivalent of an infinite
  loop.
- **Structured concurrency by default**: `asyncio.TaskGroup` — tasks cannot leak, the first failure
  cancels siblings and raises an `ExceptionGroup`. **Fire-and-forget `create_task` without keeping a
  reference is forbidden**: the task can be garbage-collected mid-flight and its exception silently
  lost.
- **Cancellation is not an error to swallow.** On cancellation, clean up in `finally` and re-raise.
  Shielding is reserved for genuinely-must-finish commits, always combined with a timeout.
- **Concurrency is bounded**: fan-outs go through a `Semaphore` with a named constant limit; queues
  between producers and consumers are bounded — an unbounded queue is a memory leak with extra
  steps.
- **Request-scoped context travels via `contextvars`** — never module globals, never thread-locals
  in async code. Do not smuggle business parameters through it.
- **Graceful shutdown is designed, not hoped for**: handle `SIGTERM`/`SIGINT`, stop accepting work,
  drain or cancel with a deadline, then close resources in reverse order. Consumers acknowledge only
  after processing.
- **Async generators are closed deterministically** — consume with `aclosing(...)` when the loop may
  break early, or cleanup runs at GC time on a dead loop.
- **Locks protect state, not I/O.** Never hold a lock across an external `await` you do not control.
- **Sync and async versions of an API are separate, explicit functions** — no boolean, no
  auto-detection. Write the async core and delegate the sync wrapper at the edge, never the reverse.

### Threads, Processes, and the GIL

Pick the model by the workload, and measure before assuming parallelism helps:

| Workload | Model |
|---|---|
| Many concurrent network / DB waits | async |
| A blocking library with no async API | threads |
| CPU-bound Python | processes |
| CPU-bound inside a C extension that releases the GIL | threads |

- **Executors are shared and injected**, sized by a named constant, and closed on shutdown.
- **Process pools receive picklable, small arguments** and return small results; pass ids and paths,
  not loaded objects. A function submitted to a process pool is a module-level function.
- **Shared mutable state between threads is protected by a lock**, held for the shortest time, never
  across I/O. Prefer no shared state at all.
- **Thread-safety is a documented property of a class**, not an assumption.
- **`threading.local` only for genuinely per-thread resources**; in async code it is wrong — use
  `contextvars`.
- **Daemon threads are forbidden** for anything that does work; every thread is joined on shutdown
  with a timeout.
- **The `multiprocessing` start method is `spawn`**, set explicitly; forking a process that already
  has threads or an event loop is undefined behaviour in practice.
- **Signals are handled in the main thread only**; workers get a stop event, not a signal.

## Documentation

- **The module docstring is mandatory — one line, in every module.** The name says what the module
  is called; the line says what is inside and why it exists apart from its neighbour.
- **NEVER** add any other docstring, or an inline comment, unless explicitly asked to.
- **Exception — shared-library public API**: in a package other teams install and import, every name
  in `__all__` gets a docstring. Internal service code carries the module line and nothing more.
- Code must be self-documenting through clear naming — if a comment feels necessary, refactor
  instead.
- Comments inside the code examples in these files are **for illustration only**. Do **NOT** copy
  them into real code.

### Comments — the Only Permitted Kinds

When a comment is unavoidable, it explains **why**, never **what** or **how**. Exactly these kinds
are allowed:

- **Workaround or non-obvious constraint**, with a reference a reader can verify or remove later.
- **`# TODO(username): description`** — always with an owner and, where possible, a ticket.
- **A suppression** — always with its rule code and the reason on the same line.
- **Warnings about non-obvious consequences of this block**: `# Order matters here: the reversed
  list is what the caller iterates`.
- **Legal or licence headers** where the project requires them.

Forbidden: commented-out code, restating the code, section banners, author or date stamps, change
logs, and comments that describe a name instead of fixing it.

### Comments Are Local — No Leaking Context

A comment describes **only the code in its own block**. It must stay true when anything outside that
block changes, and be understandable without opening another file.

- **Scope equals placement.** A comment inside a function talks about that function; inside a loop
  body, about that iteration. Never explain a caller, a subclass, or "the bigger picture" from
  inside a unit.
- **No comments about other code.** `# called by OrderService.place_order()`, `# must run before
  _flush()`, `# keep in sync with schemas/order.py` are all forbidden: each rots the moment the
  other side changes and nothing checks it. If two places must agree, encode the coupling in code —
  one shared constant, one shared type, one call — not in prose.
- **No cross-block control-flow narration.** `# this is the second stage` cannot be verified by a
  reader of that block.
- **The relocation test.** Cut the block and paste it into another module: if the comment becomes
  wrong, meaningless, or unverifiable, it was leaking.
- **Reasons, not references.** External references point outward to tickets, RFCs and specs — which
  are stable — never inward to other source locations, which are not.
- **If a comment can only be written by referring elsewhere, the design is wrong**, not the comment.

  ```python
  # WRONG — leaks into other code; every line rots silently
  class OrderValidator:
      # NOTE: OrderService calls this before _persist(); do not reorder
      # keep the limit in sync with schemas/order.py MAX_ITEMS
      def validate(self, order: Order) -> None:
          if len(order.items) > 100:   # matches the API schema limit
              raise TooManyItemsError(order.id)

  # CORRECT — the coupling is code, and the only comment is a self-contained reason
  MAX_ORDER_ITEMS: Final = 100        # the schema imports this too: one source of truth

  class OrderValidator:
      def validate(self, order: Order) -> None:
          if len(order.items) > MAX_ORDER_ITEMS:
              raise TooManyItemsError(order.id)
  ```

### Docstrings Are Local — No Leaking Context

When a docstring is written at all, it describes **the contract of the thing it is attached to**,
and nothing else.

- **Scope equals attachment.** A function docstring covers its parameters, return value, raised
  errors, and side effects; a class docstring, what the class represents and its invariants. Never
  wider.
- **No callers, no consumers.** `"""Called by OrderService during checkout."""` is forbidden —
  callers are added and removed, and the docstring silently becomes a lie.
- **No collaborators or ordering.** `"""Must be called after load_config()."""` — if the dependency
  is real, express it in the signature, where the checker enforces it.
- **No architecture lectures.** A method docstring does not explain the layer scheme or the request
  lifecycle. That lives in the project's documentation.
- **Contract, not implementation.** `"""Return the shortest route between two stops."""`, not
  `"""Run Dijkstra over the adjacency map."""`
- **`Raises:` lists what this function's own logic raises**, never what an injected dependency might
  propagate.
- **No cross-docstring continuity.** Never "as described above", "see the base class", "same as
  `save()` but async". Either the override adds nothing — write no docstring, the base contract
  stands — or it has its own contract, stated in full.
- **No changelogs, authors, dates, or TODOs.**
- **Examples are self-contained.** A doctest that depends on objects built elsewhere is a leak that
  also breaks the moment those objects change.

  ```python
  # WRONG — documents callers, siblings, ordering, implementation and history
  class InvoiceRenderer:
      """Renders invoices.

      Called by the v1 API handler and by the nightly batch job.
      Must run after TaxCalculator has populated order.tax (see billing/tax.py).
      Added in 2.1; will move to the reporting service.
      """

  # CORRECT — a contract that survives being moved anywhere
  class InvoiceRenderer:
      """Produces the customer-facing HTML representation of a priced order."""

      def render(self, order: PricedOrder) -> str:
          """Return the invoice HTML for a priced order.

          Args:
              order: An order with taxes and totals already applied.

          Returns:
              A complete, self-contained HTML document.

          Raises:
              MissingTemplateError: If the configured template is not available.
          """
  ```

  The key move: "must run after taxes are calculated" stopped being prose and became a type —
  `PricedOrder` instead of `Order`. That is the general recipe for a leaking docstring; what you
  want to explain in words usually belongs in the signature.

### Examples — How to Write Them

Applies to every example that ships with code: docstring examples, `README` snippets, and files
under `examples/`. An example is executable documentation, held to the same standard as the code it
demonstrates, plus one extra requirement — it must run.

- **Show the smallest complete thing.** One capability, with every import and object constructed
  inside it. An example that starts mid-story is unusable and unverifiable.
- **Examples are executed, not proofread.** An example nobody runs is wrong within a release or two.
- **Start from the caller's goal, not the API surface.** Order examples by frequency of use.
- **Realistic data, no filler.** Never `foo`, `bar`, `test123`. Use reserved example values
  (`example.com`, RFC 5737 addresses) so an example can never hit a real host. Never a real key,
  token, hostname or customer name, not even redacted.
- **Deterministic output.** Anything time-, id- or order-dependent is pinned: inject a fixed clock,
  use a literal UUID, sort before printing.
- **Show the outcome, not the plumbing.** Print or assert the one value that proves the point.
- **Examples follow every rule in these files.** Copy-paste is how examples are consumed: an example
  with a bare `except` teaches a bare `except` to every reader.
- **Never demonstrate an anti-pattern without marking it** `# WRONG` next to a `# CORRECT`.
- **The happy path is the example; failures get their own** — one per error scenario a caller must
  handle.
- **Keep examples versioned with the API.** A deprecated path disappears from examples in the same
  release it is deprecated in.

## Definition of Done

Run in this order; every step must pass before the next one starts. Do not hand over code with any
unchecked box.

**Automated gates**

- [ ] The formatter leaves nothing to change
- [ ] The linters report nothing, and no new suppression was added
- [ ] The type checker is clean in strict mode, with no new ignore
- [ ] The tests are green, and new behaviour has tests at the right level
- [ ] The layer contracts hold

**Naming** (see Naming Self-Check)

- [ ] Every new identifier passes the Naming Self-Check
- [ ] Every `Protocol` / contract-ABC starts with `Base`; no concrete class does
- [ ] No generically named unit contains concrete logic; no concrete rule lives in two places

**Structure**

- [ ] Class follows Method Ordering; function follows Function Body Layout
- [ ] Every helper has a reason to exist: reuse, a required callable, hidden complexity, a test
      seam, or a named predicate
- [ ] Every class earns its existence: state, invariants, swappability, shared dependencies, or a
      lifecycle
- [ ] No boolean flag parameters; non-obvious parameters are keyword-only
- [ ] No logic at import time
- [ ] Public surface is exactly `__all__`; nothing imports a private name across a package boundary
- [ ] Implementation-specific libraries are imported only in the implementation module

**Types and data**

- [ ] Parameters use `collections.abc` ABCs; returns are concrete
- [ ] No `Any`, no `object` used as "anything"
- [ ] Every closed value set is `Literal` or `Enum`; no `dict[str, Any]` crosses a layer boundary
- [ ] Every override carries `@override`; functions that always raise are `-> Never`
- [ ] Constants are `Final`; dataclasses are `frozen=True` unless justified
- [ ] No magic literals

**Errors and logging**

- [ ] Every conversion preserves the cause
- [ ] No function returns `None`/`False`/`-1` to signal an error
- [ ] Errors logged once, at the boundary; no secrets or PII

**Persistence**

- [ ] Queries load relations explicitly; repositories return domain objects and never commit
- [ ] Each migration is one change, reversible, and backward compatible with the deployed code

**Async and resources**

- [ ] No blocking calls inside async functions; every external call has a timeout; no unreferenced
      `create_task`
- [ ] Every resource is opened in a context manager; lifetime lives in the composition root
- [ ] Datetimes are aware UTC; money is `Decimal`; time is injected where tested
- [ ] External calls have a deliberate retry and idempotency decision

**Hygiene**

- [ ] Every comment and docstring passes the relocation test
- [ ] Every shipped example is self-contained, deterministic, and actually runs
- [ ] No hardcoded credentials, URLs, or environment-specific values

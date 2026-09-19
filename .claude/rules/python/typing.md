---
paths:
  - "**/*.py"
---

# Typing and Data Modelling

Supplement to `core.md`. Governs any signature, dataclass, model, or serialized shape.

## Type Hints and Generics

- **MUST** use type hints for all function signatures (parameters and return values)
- **NEVER** use `Any` (the exact rule: Narrowing and `Any`)
- **MUST** run mypy in **`--strict` mode** and resolve all errors. Configure it in the project's tool configuration, not via CLI flags.
- Use `T | None` for nullable types (Python >= 3.10+); avoid the older `Optional[T]` form.

### Built-in Generic Syntax (Python >= 3.12)

Use the **built-in generic bracket syntax** for all standard collection types — do **NOT** import `List`, `Dict`, `Tuple`, etc. from `typing`.

  ```python
  # Python >= 3.12 — CORRECT
  from collections.abc import Mapping, Sequence

  def rank_tags(tags: Sequence[str], weight_by_tag: Mapping[str, int]) -> tuple[str, ...]:
      ...

  # WRONG (legacy, only acceptable for Python < 3.12)
  from typing import List, Dict, Tuple
  def rank_tags(tags: List[str], weight_by_tag: Dict[str, int]) -> Tuple[str, ...]:
      ...
  ```

### Generic Classes (Python >= 3.12)

Use the new **`class Foo[T]`** syntax (PEP 695) instead of `Generic[T]` from `typing`. Bound type parameters with `:`.

  ```python
  # CORRECT: PEP 695 syntax; the bound carries the meaning, the letter stays T
  class Repository[T: Entity](ABC):
      @abstractmethod
      def find(self, entity_id: EntityId) -> T | None: ...
      @abstractmethod
      def save(self, entity: T) -> None: ...

  # WRONG (legacy)
  from typing import Generic, TypeVar
  T = TypeVar("T", bound=Entity)
  class Repository(Generic[T]): ...

  # CORRECT: a generic dataclass under the same syntax
  @dataclass(frozen=True, slots=True)
  class Page[T]:
      items: tuple[T, ...]
      total: int
  ```

### `Self`, Overloads, Dispatch, and Narrowing

- **`typing.Self` (Python >= 3.11) for methods returning their own instance**: `def with_row(self, row: Row) -> Self`, `@classmethod def from_env(cls) -> Self`, `def __enter__(self) -> Self`. Never a quoted class name (`-> "Cart"`) and never the class name unquoted — both break for subclasses.
- **`@typing.overload` when one function genuinely has several signatures** (different return type depending on argument types): declare the overloads, implement once. Do not use overloads to paper over a function that should be two functions (see: no boolean flag parameters).
- **`functools.singledispatch` / `singledispatchmethod` instead of `isinstance` ladders** when behaviour varies by the type of one argument and the set of types is open (plugins can register). For a closed set of variants prefer `match` on a tagged union of dataclasses.
- **`TypeIs` (3.13+, or `TypeGuard`) for custom narrowing predicates**: `def is_shipped(order: Order) -> TypeIs[ShippedOrder]`. The predicate name follows boolean naming rules.
- **`assert_never(value)` in the `case _:` of every `match` over a union or `Enum`** — exhaustiveness becomes a type error instead of a silent fall-through when a new variant is added.
- **`@final`** on classes not designed for subclassing and on methods that subclasses must not override; **`ClassVar`** on class-level attributes that are not instance fields.

  ```python
  # WRONG — isinstance ladder, quoted self-type
  def render(shape) -> str:
      if isinstance(shape, Circle): ...
      elif isinstance(shape, Square): ...

  class Cart:
      def add(self, item: Item) -> "Cart": ...

  # CORRECT
  @singledispatch
  def render(shape: Shape) -> str:
      raise NotImplementedError(type(shape).__name__)

  @render.register
  def _(shape: Circle) -> str: ...

  @render.register
  def _(shape: Square) -> str: ...

  class Cart:
      def add(self, item: Item) -> Self: ...

  type Event = OrderPlaced | OrderPaid | OrderShipped

  def apply(event: Event) -> None:
      match event:
          case OrderPlaced():  ...
          case OrderPaid():    ...
          case OrderShipped(): ...
          case _:
              assert_never(event)
  ```

### Standard-Library ABCs (`collections.abc`) — in Annotations and at Runtime

The standard library already defines the vocabulary of "things you can iterate / index / call / hash / close". **MUST** use these abstract base classes instead of concrete types in annotations, instead of ad-hoc `hasattr` / duck checks at runtime, and instead of hand-rolled protocols for behaviour the stdlib already names.

**In annotations — accept the most abstract type that works, return the most concrete type you actually build:**

| You only need to… | Annotate the parameter as | Never as |
|---|---|---|
| iterate once | `Iterable[T]` | `list[T]` |
| iterate, know the length, index | `Sequence[T]` | `list[T]`, `tuple[T, ...]` |
| mutate in place (append, set item) | `MutableSequence[T]` | `list[T]` |
| look up by key, iterate keys | `Mapping[K, V]` | `dict[K, V]` |
| add / remove keys | `MutableMapping[K, V]` | `dict[K, V]` |
| test membership, iterate, no duplicates | `Set[T]` (from `collections.abc`, alias `AbstractSet`) | `set[T]`, `frozenset[T]` |
| call it | `Callable[[A, B], R]` | `types.FunctionType`, `object` |
| pass to `len()` | `Sized` | — |
| use as a dict key | `Hashable` | — |
| `for … in` once, possibly lazy | `Iterator[T]` / `Generator[Y, S, R]` | `list[T]` |
| `async for` | `AsyncIterable[T]` / `AsyncIterator[T]` | — |
| `await` | `Awaitable[T]` / `Coroutine[…]` | — |
| read/write bytes or text | `typing.IO[bytes]`, `typing.TextIO`, `io.IOBase` subclasses | `object` |
| numbers of any kind | `numbers.Real` / `numbers.Integral` (or `int | float`) | `float` when `int` is also fine |

- Import from `collections.abc`, never from `typing` (`typing.Sequence`, `typing.Mapping`, `typing.Callable` etc. are deprecated aliases).
- Return types are concrete: `-> list[User]`, `-> dict[str, int]`, `-> tuple[int, int]` — the caller may rely on `.append`, `.items()`, unpacking. Return an ABC only when you deliberately hide the container (`-> Iterator[Row]` for a generator, `-> Mapping[str, str]` for a read-only view).
- `Sequence[str]` is also the correct way to say "a list of strings but **not** a bare `str`" — mypy treats `str` as `Sequence[str]`, so add an explicit `isinstance(value, str)` guard in the body when a bare string would be a bug.
- Attributes and dataclass fields follow the same rule: `items: Sequence[Item]` for read-only, `items: list[Item]` only when the class itself mutates it.

**At runtime — `isinstance` against the ABC, never `hasattr` or `type()`:**

- `isinstance(value, Mapping)` — **NEVER** `isinstance(value, dict)` (breaks `MappingProxyType`, `ChainMap`, custom mappings) and **NEVER** `hasattr(value, "keys")`.
- `isinstance(value, Iterable)`, `isinstance(value, Callable)`, `isinstance(value, Hashable)`, `isinstance(value, Sized)` — the ABCs implement `__subclasshook__`, so any object with the right dunder methods passes, registered or not.
- `isinstance(value, str)` / `isinstance(value, bytes)` guards come **before** `Iterable` / `Sequence` checks — both are sequences.
- `isinstance(value, numbers.Real)` — **NEVER** `isinstance(value, (int, float))`, which rejects `Decimal`, `Fraction` and NumPy scalars (`bool` is an `Integral`; guard it explicitly if that matters).
- `os.PathLike` for "a path-like thing", then normalise with `Path(value)`; never `isinstance(value, (str, Path))`.

**When implementing a container — subclass the ABC and implement only the abstract methods; the mixin methods come for free:**

- `MutableMapping` — implement `__getitem__`, `__setitem__`, `__delitem__`, `__iter__`, `__len__`; get `get`, `pop`, `setdefault`, `update`, `keys`, `items`, `values`, `__contains__`, `__eq__` for free.
- `Sequence` — implement `__getitem__`, `__len__`; get `__iter__`, `__contains__`, `__reversed__`, `index`, `count`.
- `Iterator` — implement `__next__`; get `__iter__`.
- `Set` — implement `__contains__`, `__iter__`, `__len__`; get all set algebra (`&`, `|`, `-`, `<=`, `isdisjoint`).
- **NEVER** subclass `dict`, `list`, `set` directly to customise behaviour — their C-level methods bypass your overrides (`dict.update` does not call `__setitem__`). Subclass `collections.UserDict` / `UserList` / `UserString` or the ABC.
- `NotImplementedError` in an ABC method is a bug: use `@abstractmethod` so instantiation fails early.

  ```python
  # WRONG — concrete types in params, duck check by attribute, dict subclass with silent hole
  def merge_settings(base: dict[str, str], override: dict[str, str]) -> dict[str, str]: ...

  def total_length(values):
      if hasattr(values, "__len__"):
          return len(values)
      return sum(1 for _ in values)

  class CaseInsensitiveDict(dict):                # dict.update() bypasses __setitem__
      def __setitem__(self, key, value):
          super().__setitem__(key.lower(), value)

  # CORRECT
  from collections.abc import Iterable, Iterator, Mapping, MutableMapping, Sized

  def merge_settings(base: Mapping[str, str], override: Mapping[str, str]) -> dict[str, str]:
      return {**base, **override}

  def total_length(values: Iterable[object]) -> int:
      if isinstance(values, Sized):
          return len(values)
      return sum(1 for _ in values)

  class CaseInsensitiveDict(MutableMapping[str, str]):
      def __init__(self) -> None:
          self._store: dict[str, str] = {}

      def __getitem__(self, key: str) -> str:
          return self._store[key.lower()]

      def __setitem__(self, key: str, value: str) -> None:
          self._store[key.lower()] = value

      def __delitem__(self, key: str) -> None:
          del self._store[key.lower()]

      def __iter__(self) -> Iterator[str]:
          return iter(self._store)

      def __len__(self) -> int:
          return len(self._store)
  ```

- Beyond `collections.abc`, use the other stdlib ABCs where they fit: `numbers` (`Number`, `Real`, `Integral`), `io` (`IOBase`, `RawIOBase`, `TextIOBase`), `os.PathLike`, `contextlib.AbstractContextManager` / `AbstractAsyncContextManager`, `abc.ABC` for your own hierarchies. Write a custom contract **only** when no stdlib ABC names the capability — and then an `ABC`, unless the other side is someone else's to subclass.

## Make Illegal States Unrepresentable

Every value has a narrowest honest type. Reach for it — a wider type is a runtime check you owe later, in a place nobody will remember to write it.

### Type Precision Ladder

| Instead of | Use | When |
|---|---|---|
| `str` for a closed set | `Literal["csv", "json"]` | 2–4 values, one or two signatures |
| `str` / `Literal` reused across signatures | `Enum` / `StrEnum` | the set has a name, behaviour, or 3+ users |
| `str`, `int` that must not be mixed | `NewType` | identity only, no rules (see Value Objects) |
| a primitive with rules | frozen dataclass value object | validation, invariants, operations |
| `dict[str, Any]` you don't own | `TypedDict` | fixed keys, external JSON shape |
- **A dataclass carries three flags together: `frozen=True, slots=True, kw_only=True`.** `frozen`
  is about mutability, `slots` about the attribute set, `kw_only` about the call site. The third
  is the one usually forgotten and the one that pays daily: a field added in the middle stops being
  a silent breaking change, and two adjacent fields of the same type can no longer be swapped by a
  caller. `_Rejected(order.id, reason, title)` reads fine and is wrong in three different ways;
  `_Rejected(advertisement_id=..., reason=..., title=...)` cannot be.
- **Positional construction survives only where the order is the concept itself** — `Point(x, y)`,
  `Range(low, high)` — and even there the type checker is the only thing that will catch a swap.

| `dict[str, Any]` crossing a boundary | a validating boundary model | untrusted input needing validation |
| `dict` with homogeneous dynamic keys | `Mapping[UserId, Order]` | keys are data, not fields |
| `tuple[Any, ...]` | frozen dataclass | any record — never `NamedTuple` |
| `Any` | `object` + narrowing, or a `Protocol` | the value is genuinely unknown |
| several `bool` fields | one `Enum` state | the flags encode a state machine |

  ```python
  # WRONG — four fields, none constrained: 32 combinations of which 4 are valid
  @dataclass
  class Job:
      id: str
      status: str                    # "pending"? "PENDING"? "in-progress"?
      payload: dict[str, Any]
      is_retryable: bool
      finished_at: datetime | None   # set when status == "done"? unknowable

  # CORRECT — every field narrowed; invalid states cannot be constructed
  JobId = NewType("JobId", UUID)

  class JobStatus(StrEnum):
      PENDING = "pending"
      RUNNING = "running"
      DONE = "done"
      FAILED = "failed"

  @dataclass(frozen=True, slots=True, kw_only=True)
  class Job:
      id: JobId
      status: JobStatus
      payload: JobPayload
      finished_at: datetime | None
  ```

  ```python
  # WRONG — three booleans give 8 states, 3 of which are valid
  @dataclass
  class Subscription:
      is_active: bool
      is_cancelled: bool
      is_expired: bool

  # CORRECT — one field, exactly three states
  class SubscriptionState(StrEnum):
      ACTIVE = "active"
      CANCELLED = "cancelled"
      EXPIRED = "expired"
  ```

### `TypedDict`

- **`TypedDict` is for dict-shaped data that must stay a dict** — a JSON payload you don't own, a `**kwargs` bundle, a driver row. It has no validation, no methods, no invariants and no runtime identity (`isinstance` does not work on it); anything needing those is a dataclass or a model.
- **`total=False` is not "optional-ish"** — mark individual keys `NotRequired[…]` / `Required[…]` so each key states its own contract.
- **`ReadOnly[…]`** (PEP 705) for keys consumers must not mutate.
- **Never as an internal domain type.** A `TypedDict` passed between layers is a dict pretending to be a model: convert it at the boundary and pass the domain object inward (see Boundary Validation).
- **`Unpack[SomeKwargs]` for typed `**kwargs`** when a signature forwards a fixed set of options.
- Extra keys are a type error, never a runtime one — never rely on a `TypedDict` to reject unknown fields; that is `extra="forbid"` on a model.

  ```python
  # WRONG — dict[str, Any] at the boundary and inside; the keys exist only in the author's head
  def parse_product(raw: dict[str, Any]) -> dict[str, Any]:
      return {"title": raw["name"], "salary": raw.get("salary")}

  # CORRECT — TypedDict describes the foreign JSON; a domain object travels inward
  class ProductPayload(TypedDict):
      name: str
      salary: NotRequired[int | None]
      published_at: ReadOnly[str]

  def parse_product(raw: ProductPayload) -> Product:
      return Product(
          title=raw["name"],
          salary=Money.from_minor(raw["salary"]) if raw.get("salary") else None,
          published_at=datetime.fromisoformat(raw["published_at"]),
      )
  ```

  ```python
  # Typed **kwargs
  class RetryOptions(TypedDict):
      attempts: NotRequired[int]
      backoff_seconds: NotRequired[float]

  def fetch(url: str, **options: Unpack[RetryOptions]) -> Response: ...
  ```

### `Literal`

- **`Literal` for a closed set inside one or two signatures**: `def export(fmt: Literal["csv", "json"]) -> bytes`. Callers are checked; there is no runtime cost.
- **Promote to `Enum`** at the threshold set by the Type Precision Ladder — three or more users — or earlier when the set needs iteration, carries behaviour or metadata, or crosses a boundary where the wire value and the code value may diverge (`StrEnum` keeps them equal).
- **`Literal` + `Final` for constants whose exact value matters to the checker**: `DEFAULT_FORMAT: Final[Literal["json"]] = "json"`.
- **Tagged unions**: give each variant a `Literal` discriminator so `match` narrows exhaustively; close with `assert_never` (see `match` Statements).
- **Never `Literal[True]` / `Literal[False]` to fake two functions** — that is a boolean flag with extra syntax (see Function Design).

  ```python
  # WRONG — an unconstrained string; the mistake surfaces at runtime, in the caller's process
  def export(orders: Sequence[Order], fmt: str) -> bytes:
      if fmt == "csv": ...
      elif fmt == "json": ...
      raise ValueError(fmt)

  # CORRECT — the set is closed at type-check time
  def export(orders: Sequence[Order], fmt: Literal["csv", "json"]) -> bytes: ...

  export(orders, "xml")   # error: Argument 2 has incompatible type
  ```

  ```python
  # Tagged union with an exhaustive match
  @dataclass(frozen=True, slots=True)
  class Circle:
      radius: Decimal
      kind: Literal["circle"] = "circle"

  @dataclass(frozen=True, slots=True)
  class Rectangle:
      width: Decimal
      height: Decimal
      kind: Literal["rectangle"] = "rectangle"

  type Shape = Circle | Rectangle

  def area(shape: Shape) -> Decimal:
      match shape:
          case Circle(radius=radius):
              return PI * radius * radius
          case Rectangle(width=width, height=height):
              return width * height
          case _:
              assert_never(shape)
  ```

### `Annotated`

- **`Annotated[T, …]` carries constraints the type system cannot express**: `Annotated[int, Field(ge=1, le=100)]`, DI markers, unit tags. The static type stays `T`; the metadata is read at runtime by whatever validates the boundary.
- **Name the constrained type once** and reuse it, instead of repeating constraints in every signature.
- **Constraints belong at the boundary**; domain code receives values that are already valid (see Value Objects).

  ```python
  # WRONG — the same limits repeated in every signature, enforced in the body
  def list_orders(page_size: int) -> list[Order]:
      if not 1 <= page_size <= 200:
          raise ValueError("bad page size")

  # CORRECT — the constrained type is named once
  type PageSize = Annotated[int, Field(ge=1, le=200)]
  type Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]+$")]

  class OrderQuery(BoundaryModel):
      page_size: PageSize = 50
      source: Slug
  ```

### Narrowing and `Any`

- **`Any` is forbidden** except at an untyped third-party edge — and there it is narrowed on the first line and never propagates. A function returning `Any` poisons every caller silently.
- **`object` instead of `Any` for "unknown"**: `object` forces narrowing, `Any` disables checking.
- **`cast()` is a claim, not a fix**: allowed only when you can state why the checker cannot see what you can, on one line — never to silence an error you do not understand. Prefer a checked `isinstance` or a reusable `TypeIs` predicate.
- **Never widen a return type to avoid a branch**: `-> Order | None` on a function that always returns an `Order` forces a pointless check on every caller.

  ```python
  # WRONG — Any escapes the function and infects everything downstream
  def load_settings(path: Path) -> Any:
      return tomllib.loads(path.read_text())

  # CORRECT — narrowed on the first line, never leaves
  def load_settings(path: Path) -> Settings:
      raw: object = tomllib.loads(path.read_text())
      if not isinstance(raw, Mapping):
          raise ConfigurationError(f"{path} must contain a table")
      return Settings.parse(raw)
  ```

  ```python
  # WRONG — cast as a way to silence the checker
  user = cast(User, cache.get(key))

  # CORRECT — checked narrowing through a reusable predicate
  def is_user(value: object) -> TypeIs[User]:
      return isinstance(value, User)

  cached = cache.get(key)
  if not is_user(cached):
      raise CacheCorruptedError(key)
  ```

### Generics and Variance

- **PEP 695 syntax** (`def first[T](...)`, `class Repository[T]`); parameter letters follow the convention in Type, Protocol, and Alias Naming (`T`, `K`/`V`, `P`/`R`).
- **Bound the parameter when it has requirements**: `[T: Entity]`, `[K: Hashable]`. An unbounded parameter whose body calls methods on it is a lie.
- **Parameters take `Sequence`/`Mapping`, returns are concrete** (see Standard-Library ABCs) — that handles variance without ever writing `covariant=`.
- **`ParamSpec` + `Concatenate` for decorators**: a decorator returning `Callable[..., Any]` erases type safety for every decorated function.

  ```python
  # WRONG — unbounded T that is really a model; concrete list in the parameter
  T = TypeVar("T")
  def save_all(repository: Any, items: list[T]) -> None: ...

  # CORRECT — bounded parameter; abstract input
  class Repository[T: Entity](ABC):
      @abstractmethod
      def save_all(self, entities: Sequence[T]) -> None: ...
  ```

  ```python
  # A decorator that preserves the wrapped signature
  def logged[**P, R](func: Callable[P, R]) -> Callable[P, R]:
      @wraps(func)
      def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
          logger.debug("calling %s", func.__qualname__)
          return func(*args, **kwargs)
      return wrapper
  ```

### Further Type Constructs

- **`@override` (PEP 698, 3.12) on every method that overrides a base method** — mandatory. It catches a typo in the method name, and it turns a rename in a contract into a type error at every subclass instead of a silently orphaned method that never runs again.
- **`Never` / `NoReturn` for functions that never return normally**: a helper that always raises is `-> Never`, and the checker then knows the code after the call is unreachable. `Never` is also the type of the impossible branch — `assert_never(value)` works because the narrowed value has type `Never`.
- **`LiteralString` (PEP 675) for parameters that must not receive interpolated input**: a query builder, a shell helper, a template loader. The checker accepts literals and concatenations of literals, and rejects any string that passed through user input — a compile-time complement to the SQL and `subprocess` rules in Security.
- **A recursive alias instead of `Any` for free-form JSON**: `type Json = str | int | float | bool | None | list[Json] | dict[str, Json]`. Use it only where the shape is genuinely unknown; a known shape is a `TypedDict` or a model.
- **`Protocol` with `__call__` instead of a multi-parameter `Callable`.** `Callable[[str, int, bool], None]` names nothing: the reader cannot tell which argument is which, and keyword arguments cannot be expressed at all. One parameter and an obvious return → `Callable`; two or more, or any keyword argument → a named calling protocol.
- **Phantom types for units**: `Seconds = NewType("Seconds", float)`, `Meters = NewType("Meters", float)`. The unit already appears in variable names (see Variable Naming); in a signature it belongs in the type, so that adding a timeout to a distance is an error rather than a bug.
- **`Iterator` vs `Iterable` in return types** — return `Iterator[T]` only when the caller is expected to consume it once (a generator, a streaming read); return a concrete `list`/`tuple` when the caller may need length, indexing, or a second pass. Returning an `Iterator` that callers keep re-iterating produces silent empty results on the second loop.
- **A sentinel, not `None`, when `None` is a legal value.** For PATCH-style updates and "argument not supplied" defaults, `None` cannot distinguish "not provided" from "explicitly null". Define a sentinel with a singleton type and keep it out of the public value space.
- **No `Result` / `Either` types.** Python signals failure with exceptions (see Error Handling); a `Result` wrapper duplicates that mechanism, defeats `raise … from`, and forces every caller into manual unwrapping. The one acceptable use is a batch operation whose *normal output* is a mix of successes and failures (validating 10 000 rows) — and then it is an explicit frozen dataclass with a `Literal` tag, not a general-purpose monad.
- **`Buffer` (PEP 688, 3.12) instead of `bytes | bytearray | memoryview`**; `SupportsIndex` / `SupportsFloat` when you only need the conversion protocol rather than a concrete numeric type.
- **`assert_type()` in tests for public library APIs** — pins the inferred type so a refactor cannot silently widen it. `reveal_type()` is a debugging tool and never gets committed.

  ```python
  # WRONG — silent orphan after a rename, anonymous Callable, None hiding two meanings
  class SlackNotifier(Notifier):
      def notify(self, recipient: Recipient, message: str) -> None: ...   # base renamed it to send()

  def register(handler: Callable[[str, int, bool], None]) -> None: ...

  def update_user(user_id: UserId, nickname: str | None = None) -> None:
      ...   # is None "leave unchanged" or "clear the nickname"?

  # CORRECT
  class SlackNotifier(Notifier):
      @override
      def send(self, recipient: Recipient, message: str) -> None: ...

  class EventHandler(Protocol):
      def __call__(self, event: str, attempt: int, *, is_retry: bool) -> None: ...

  def register(handler: EventHandler) -> None: ...

  @final
  class _Unset:
      def __repr__(self) -> str:
          return "UNSET"

  UNSET: Final = _Unset()

  def update_user(user_id: UserId, nickname: str | None | _Unset = UNSET) -> None:
      if nickname is UNSET:
          ...        # leave unchanged
      elif nickname is None:
          ...        # clear it
  ```

  ```python
  # Never, LiteralString, units, and iterator semantics
  def fail_missing(entity: str, entity_id: object) -> Never:
      raise EntityNotFoundError(f"{entity} {entity_id} not found")

  def execute_ddl(statement: LiteralString) -> None: ...

  execute_ddl(f"DROP TABLE {name}")        # error: expected LiteralString

  Seconds = NewType("Seconds", float)
  Meters = NewType("Meters", float)

  def wait(duration: Seconds) -> None: ...
  wait(Meters(5.0))                        # error: incompatible type

  def stream_rows(path: Path) -> Iterator[Row]:      # consumed once, lazily
      with path.open() as handle:
          for line in handle:
              yield Row.parse(line)

  def load_rows(path: Path) -> list[Row]:            # caller needs length and re-iteration
      with contextlib.closing(stream_rows(path)) as rows:
          return list(rows)
  ```

### Enforcement

- mypy strict, plus `disallow_any_generics`, `warn_return_any`, `warn_unreachable`, `strict_equality`, `no_implicit_reexport`.
- `# type: ignore[code]` always with a code and a reason (see Comments); their count only ratchets down.
- A `dict[str, Any]` or an untyped `**kwargs` crossing a layer boundary is a review blocker, not a style nit.

## Immutability and Data

Mutable state is the default source of bugs; make immutability the default and mutation the explicit exception.

- **`@dataclass(frozen=True, slots=True)` by default.** Drop `frozen` only when the object is a genuine aggregate root that must change over time, and say so in its name/design (`Cart`, `Session`), not for convenience. Use `dataclasses.replace()` to derive modified copies.
- **`tuple` over `list` for fixed sequences**, `frozenset` over `set` for fixed sets, `MappingProxyType` when exposing a dict read-only. A collection that is never mutated after construction is a tuple.
- **`Final` for every module- and class-level constant**: `MAX_RETRIES: Final = 3`. mypy then rejects reassignment.
- **NEVER** mutable default arguments (`def f(items: list[str] = [])`). Use `None` + assignment, or `field(default_factory=list)` in dataclasses, or a tuple `()`.
- **NEVER mutate arguments.** A function that receives a list and appends to it must be named for it (`append_audit_entry(entries, …)`) and annotated `MutableSequence`; everything else copies and returns.
- **NEVER return internal mutable state from a getter/property.** Return a copy, a tuple, or a `MappingProxyType`.
- Choosing between `Literal`, `Enum`, `NewType` and a value object is one decision with one home: the Type Precision Ladder. `NamedTuple` is never the answer (a frozen dataclass is).
- Prefer **pure functions**: input in, output out, no reads of global state, no writes. Push I/O to the edges of the call graph.
- **Dataclass field rules**: validation and derived fields in `__post_init__` (with `object.__setattr__` for frozen); `field(kw_only=True)` — or a `_: KW_ONLY` sentinel — for every field that is not obviously positional, mirroring the keyword-only rule for functions; `field(repr=False)` for secrets and blobs; `field(compare=False)` for ids/timestamps that must not affect equality.

### Value Objects

A primitive that carries rules is not a primitive. Choose the representation by how much behaviour the concept has:

- **Plain `str` / `int` / `Decimal`** — only for values with no rules at all (a free-text comment).
- **`NewType`** — the value has *identity* rules only: it must not be confused with other same-typed values, but has no validation or behaviour. `UserId = NewType("UserId", int)`, `Sku = NewType("Sku", str)`. Zero runtime cost; mypy-only protection.
- **Frozen dataclass value object** — the value has validation, invariants, or operations: `Money` (currency arithmetic, no negative amounts), `Email` (format validation, `domain` property), `Percentage`, `DateRange` (start <= end, `overlaps()`), `PhoneNumber`. Validate in `__post_init__` and raise the package's own error; from then on an instance is **valid by construction** — functions receiving a `Money` never re-validate it.
- **Promotion is one-way**: when a `NewType` grows its first rule, it becomes a value object everywhere; never keep both representations alive.
- Value objects are compared by value (dataclass `eq`), are `Hashable`, and live in `models/` (or `domain/`) with zero I/O.

  ```python
  # WRONG — primitives with implicit rules scattered at call sites
  def apply_discount(price: float, rate: float) -> float:
      if rate < 0 or rate > 1:
          raise ValueError("bad rate")
      return round(price * (1 - rate), 2)

  # CORRECT — rules live in the type; call sites cannot construct an invalid value
  @dataclass(frozen=True, slots=True)
  class DiscountRate:
      value: Decimal

      def __post_init__(self) -> None:
          if not Decimal(0) <= self.value <= Decimal(1):
              raise InvalidDiscountRateError(self.value)

  def apply_discount(price: Money, rate: DiscountRate) -> Money:
      return price * (1 - rate.value)
  ```

  ```python
  # WRONG — mutable defaults, mutates its argument, leaks internal list
  @dataclass
  class Report:
      rows: list[Row] = []

      def add(self, row: Row) -> None:
          self.rows.append(row)

      @property
      def all_rows(self) -> list[Row]:
          return self.rows

  def normalize(rows: list[Row]) -> list[Row]:
      for row in rows:
          row.name = row.name.strip()
      return rows

  # CORRECT
  @dataclass(frozen=True, slots=True)
  class Report:
      rows: tuple[Row, ...] = ()

      def with_row(self, row: Row) -> Self:
          return replace(self, rows=(*self.rows, row))

  def normalize(rows: Sequence[Row]) -> list[Row]:
      return [replace(row, name=row.name.strip()) for row in rows]
  ```

## Enumerations

- *When* a set of values becomes an `Enum` is decided by the Type Precision Ladder; this section is about *how* to write one.
- Use **`enum.StrEnum`** (Python >= 3.11) when the enum values are strings that appear in serialized output (JSON keys, DB columns, API fields). This avoids `.value` access and makes serialization transparent.
- Use **`enum.IntEnum`** for integer codes that must compare equal to plain `int` values (e.g. HTTP status codes, bitmasks).
- Use **`enum.Flag`** / **`enum.IntFlag`** for combinable bit flags.
- **NEVER** compare enum members with raw literals; always compare member-to-member.

  ```python
  from enum import Enum, StrEnum, IntEnum, Flag, auto

  # StrEnum — serializes as its string value directly
  class OrderStatus(StrEnum):
      PENDING = "pending"
      CONFIRMED = "confirmed"
      SHIPPED = "shipped"
      CANCELLED = "cancelled"

  # Enum — domain concept with no serialization requirement
  class PaymentMethod(Enum):
      CREDIT_CARD = auto()
      BANK_TRANSFER = auto()
      CRYPTO = auto()

  # IntEnum — integer codes (e.g. HTTP, error codes)
  class ErrorCode(IntEnum):
      NOT_FOUND = 404
      UNPROCESSABLE = 422
      INTERNAL = 500

  # Flag — combinable permissions
  class Permission(Flag):
      READ = auto()
      WRITE = auto()
      DELETE = auto()
      ADMIN = READ | WRITE | DELETE

  # WRONG — bare string literals scattered everywhere
  if order.status == "pending": ...

  # CORRECT — enum member comparison
  if order.status == OrderStatus.PENDING: ...
  ```

## Boundary Validation and Domain Models

Two model families, two jobs. Do not mix them.

- **Validating models live at process boundaries only**: request and response shapes, message
  payloads, settings, rows from untrusted sources. Their job is parsing and validating external
  data, and they are the only place that job happens.
- **Frozen dataclasses and value objects live inside**: domain entities and everything between
  layers. Domain code never imports the validation library.
- **Validate once, at the edge.** The boundary parses, converts to a domain object, and passes that
  inward. Services and storage never re-validate; re-validation deeper in the stack means the
  boundary leaked.
- **Boundary models are strict**: no silent coercion of `"1"` to `1`, no unknown fields quietly
  dropped. Whatever the library calls it, turn it on.
- **Explicit mapping between the families**: a `to_domain()` / `from_domain()` pair, or a mapper
  module. Never construct one family by splatting the other's fields — a field rename then breaks it
  silently, and nothing fails until production.
- **Validating a bare collection reuses one adapter instance**; constructing the validator is the
  expensive part.
- **Output shapes are explicit too**: the boundary returns a response model built from the domain
  object, never a domain or ORM object serialized by accident. Over-exposure of fields is a security
  bug, not a formatting one.

## Time, Money, and Identifiers

- **Datetimes are always timezone-aware UTC**: `datetime.now(UTC)` — **NEVER** `datetime.now()` / `datetime.utcnow()` (naive, and `utcnow` is deprecated). Convert to local time only at the presentation edge, with `zoneinfo.ZoneInfo`, never a hand-written offset.
- Naive datetimes are rejected at the boundary: a schema that accepts a datetime requires an offset.
- **Store and serialize as ISO-8601** (`.isoformat()` / `datetime.fromisoformat`); epoch numbers only for machine-to-machine metrics.
- **Never compare or mix naive and aware**; never do date arithmetic across DST with plain `timedelta` on local times — do it in UTC.
- **`date` for calendar concepts, `datetime` for instants** — a birthday is a `date`; storing it as midnight `datetime` invents a timezone bug.
- **Time is a dependency.** Any code that needs "now" takes a clock (`now: Callable[[], datetime]` or a tiny `Clock` protocol) injected from the composition root; `datetime.now(UTC)` appears only in the default wiring and tests use a fixed clock.
- **Money is `Decimal`, never `float`.** Construct from `str` or `int` (`Decimal("19.99")` — `Decimal(19.99)` inherits float error); quantize explicitly at boundaries (`amount.quantize(Decimal("0.01"), ROUND_HALF_EVEN)`); wrap in a `Money` value object with currency, so amounts in different currencies cannot be added.
- **Durations and sizes are `timedelta` and integers of an explicit unit** (see variable naming: `timeout_seconds`); never floats of ambiguous unit.
- **Identifiers**: `uuid.uuid4()` for opaque ids; UUIDv7 (or ULID) when ids must sort by creation time (index locality); **never** auto-increment integers exposed publicly (enumeration attacks) and never `random`-derived ids (see Security). Wrap ids in `NewType`.

## Serialization

- **Serialization is explicit and lives at the boundary**: a boundary model, or a dedicated
  `to_dict` / `from_dict` on a value object. Never `obj.__dict__`, never `vars(obj)`, never
  serializing a domain or ORM object directly.
- **Round-trip is a contract**: `from_dict(to_dict(x)) == x`, covered by a test for every serialized
  type.
- **NEVER unpickle untrusted data** — it executes code on load. Do not use pickle for persistence or
  cross-service messages at all, being version-fragile; it is acceptable only inside a single
  process tree.
- **Safe loaders only** for untrusted text formats; configuration is read once at startup, not used
  as a database.
- **Versioned payloads**: any shape that crosses a queue or is stored carries an explicit version
  field, and consumers tolerate unknown *added* fields. Tolerance is for stored and queued data
  evolution, achieved by explicit migration on read — requests still reject extras.
- **Binary formats follow the same rules**: explicit schema, explicit version, adapters at the edge,
  never in domain code.

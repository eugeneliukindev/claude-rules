---
name: python-types
description: >-
  Python type design decisions: the precision ladder from a bare primitive to Literal, Enum,
  NewType, TypedDict, frozen value objects and validating models; PEP 695 generics, dispatch and
  variance; narrowing Any and object; Annotated constraints; enumerations; and the mypy error
  codes that enforce them. Use when choosing a representation for a Python value, designing a
  generic class or function, narrowing an unknown value, replacing a dict[str, Any], or deciding
  what to put in an annotation.
---

# Types — Reference

`core.md` carries the defaults; this file carries the decisions behind them.

**Choosing a `collections.abc` ABC** — which one to accept in a parameter, which to return, how to
check one at runtime, how to implement a container: see [collections-abc.md](collections-abc.md).

## Type Precision Ladder

Every value has a narrowest honest type. A wider type is a runtime check you owe later, in a place
nobody will remember to write it.

| Instead of | Use | When |
|---|---|---|
| `str` for a closed set | `Literal["csv", "json"]` | 2–4 values, one or two signatures |
| `str` / `Literal` reused across signatures | `Enum` / `StrEnum` | the set has a name, behaviour, or 3+ users |
| `str`, `int` that must not be mixed | `NewType` | identity only, no rules |
| a primitive with rules | frozen dataclass value object | validation, invariants, operations |
| `dict[str, Any]` you don't own | `TypedDict` | fixed keys, external JSON shape |
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

## Value Objects

A primitive that carries rules is not a primitive. Choose by how much behaviour the concept has:

- **Plain `str` / `int` / `Decimal`** — only for values with no rules at all (a free-text comment).
- **`NewType`** — *identity* rules only: it must not be confused with other same-typed values, but
  has no validation or behaviour. `UserId = NewType("UserId", int)`. Zero runtime cost.
- **Frozen dataclass value object** — the value has validation, invariants, or operations: `Money`,
  `Email`, `DateRange`. Validate in `__post_init__` and raise the package's own error; from then on
  an instance is **valid by construction**, and functions receiving it never re-validate.
- **Promotion is one-way**: when a `NewType` grows its first rule it becomes a value object
  everywhere; never keep both representations alive.
- Value objects are compared by value, are `Hashable`, and carry no I/O.

**Dataclass field rules**: validation and derived fields go in `__post_init__`, with
`object.__setattr__` when frozen; `field(default_factory=…)` for anything mutable or computed;
`field(repr=False)` for secrets and blobs; `field(compare=False)` for ids and timestamps that must
not affect equality. Derive a modified copy with `dataclasses.replace()`, never by mutation.

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

## `TypedDict`

- **For dict-shaped data that must stay a dict** — a JSON payload you don't own, a `**kwargs`
  bundle, a driver row, a file you read back with `json.load`. No validation, no methods, no
  invariants, no runtime identity (`isinstance` does not work); anything needing those is a
  dataclass or a model.
- **A file read back is the clearest case.** The rows come out of the library as dicts and stay
  dicts — the loader built them, not you — and converting every one costs more than it returns when
  most of the file is only counted, filtered or written back. The `TypedDict` names the keys so
  `row["labels"]` stops being `Any`; the part that carries meaning is still parsed by a model where
  it is used.
- **`total=False` is not "optional-ish"** — mark individual keys `NotRequired[…]` / `Required[…]`.
  **`ReadOnly[…]`** (PEP 705) for keys consumers must not mutate.
- **Never as an internal domain type.** Convert at the boundary and pass the domain object inward.
- **`Unpack[SomeKwargs]` for typed `**kwargs`** when a signature forwards a fixed set of options.
- Extra keys are a type error, never a runtime one — rejecting unknown fields is `extra="forbid"`
  on a model.

  ```python
  # WRONG — dict[str, Any] at the boundary and inside; the keys exist only in the author's head
  def parse_product(raw: dict[str, Any]) -> dict[str, Any]:
      return {"title": raw["name"], "price": raw.get("price")}

  # CORRECT — TypedDict describes the foreign JSON; a domain object travels inward
  class ProductPayload(TypedDict):
      name: str
      price: NotRequired[int | None]
      published_at: ReadOnly[str]

  def parse_product(raw: ProductPayload) -> Product:
      return Product(
          title=raw["name"],
          price=Money.from_minor(raw["price"]) if raw.get("price") else None,
          published_at=datetime.fromisoformat(raw["published_at"]),
      )
  ```

## `Literal` — Closing a Set

- **For a closed set inside one or two signatures**: `def export(fmt: Literal["csv", "json"]) ->
  bytes`. Callers are checked at type-check time; no runtime cost.
- **Promote to `Enum`** at the ladder's threshold — three or more users — or earlier when the set
  needs iteration, carries behaviour, or crosses a boundary where the wire value and the code value
  may diverge (`StrEnum` keeps them equal).
- **`Literal` + `Final` for constants whose exact value matters**: `DEFAULT: Final[Literal["json"]]`.
- **Tagged unions**: a `Literal` discriminator per variant so `match` narrows exhaustively.
- **Never `Literal[True]` / `Literal[False]` to fake two functions** — that is a boolean flag with
  extra syntax.

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

## `Annotated` — Constraints the Type System Cannot Express

`Literal` narrows *which values*; `Annotated` attaches *rules about* a value that the static type
keeps no room for. The static type stays `T`; the metadata is read at runtime by whatever validates
the boundary.

- **Constraints, DI markers, unit tags**: `Annotated[int, Field(ge=1, le=100)]`.
- **Name the constrained type once and reuse it.** Repeating the same bounds in five signatures is
  five places to get it wrong, and the constraint travels with the name when it is aliased.
- **Constraints belong at the boundary.** Domain code receives values that are already valid, so a
  bound restated in a service body means the boundary leaked.

  ```python
  # WRONG — the same limits repeated in every signature, enforced by hand in the body
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

## Enumerations

- **`StrEnum`** (3.11+) when the values are strings that appear in serialized output — no `.value`
  access, transparent serialization. **`IntEnum`** for integer codes that must compare equal to
  plain ints. **`Flag`** / **`IntFlag`** for combinable bit flags. Plain **`Enum`** for a domain
  concept with no serialization requirement, members from `auto()`.
- **Compare member to member**, never against a raw literal: `order.status == OrderStatus.PENDING`.
- Enums are singular nouns; members are states or kinds.

## Narrowing and `Any`

- **`Any` is legal and rarely what you want.** It does not say "unknown", it says "stop checking",
  and a function *returning* `Any` spreads that silence to everything downstream. Two positions
  earn it: an untyped third-party edge, where it is narrowed on the first line and never
  propagates; and a signature a library fixes — a wrap-validator, a hook, a callback whose shape is
  not yours to choose. There, `Any` stays in exactly the position the library defines, and the
  arguments you *do* control are typed.
- **`object` is how "unknown" is spelled**: it forces narrowing. A parameter you merely inspect —
  `isinstance` checks, `repr`, passing it on — is `object`, not `Any`, even when the value beside
  it has to stay `Any`.
- **`cast()` is a claim, not a fix**: allowed only when you can state on one line why the checker
  cannot see what you can. Prefer a checked `isinstance` or a reusable `TypeIs` predicate.
- **Never widen a return type to avoid a branch**: `-> Order | None` on a function that always
  returns an `Order` forces a pointless check on every caller.

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

## Generics, Dispatch, and Variance

- **PEP 695 syntax from Python 3.12**: `def first[T](...)`, `class Repository[T: Entity]`. The
  parameter belongs to the signature, so nothing module-level is declared and nothing can be reused
  by accident.
- **Below 3.12 it is `TypeVar` + `Generic`, and that is not a lapse** — the syntax does not exist
  yet. The same applies to the `typing` names that arrived with it: `typing_extensions.override`
  until 3.12, `typing_extensions.TypeIs` until 3.13. A project states its floor once, in
  `requires-python`, and every one of these choices follows from it rather than being argued per
  file. Naming for the `TypeVar` form is in `naming.md`: private and suffixed, `_T` / `_KT` /
  `_BackendT`.
- **Bound the parameter when it has requirements.** An unbounded parameter whose body calls methods
  on it is a lie.
- **Parameters take `Sequence`/`Mapping`, returns are concrete** — that handles variance without
  ever writing `covariant=`.
- **`ParamSpec` + `Concatenate` for decorators**: a decorator returning `Callable[..., Any]` erases
  type safety for every function it wraps.
- **`typing.Self` for methods returning their own instance** — `def with_row(self) -> Self`,
  `@classmethod def from_env(cls) -> Self`, `__enter__`. Never a quoted class name, which breaks
  for subclasses.
- **`@typing.overload` when one function genuinely has several signatures** — not to paper over a
  function that should be two.
- **`functools.singledispatch` instead of an `isinstance` ladder** when behaviour varies by the
  type of one argument and the set is open. For a closed set, `match` on a tagged union.
- **`TypeIs` (3.13+, or `TypeGuard`) for custom narrowing predicates**; the name follows the
  boolean rules.

  ```python
  # WRONG — unbounded T that is really a model, concrete list in the parameter, isinstance ladder
  T = TypeVar("T")
  def save_all(repository: Any, items: list[T]) -> None: ...

  def render(shape) -> str:
      if isinstance(shape, Circle): ...
      elif isinstance(shape, Square): ...

  # CORRECT
  class Repository[T: Entity](ABC):
      @abstractmethod
      def save_all(self, entities: Sequence[T]) -> None: ...

  @singledispatch
  def render(shape: Shape) -> str:
      raise NotImplementedError(type(shape).__name__)

  @render.register
  def _(shape: Circle) -> str: ...

  def logged[**P, R](func: Callable[P, R]) -> Callable[P, R]:
      @wraps(func)
      def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
          logger.debug("calling %s", func.__qualname__)
          return func(*args, **kwargs)
      return wrapper
  ```

## Further Constructs

- **`Never` / `NoReturn` for functions that never return normally** — the checker then knows the
  code after the call is unreachable. `Never` is also the type of the impossible branch, which is
  why `assert_never(value)` works.
- **`LiteralString` (PEP 675) for parameters that must not receive interpolated input**: a query
  builder, a shell helper, a template loader. The checker accepts literals and concatenations of
  literals and rejects anything that passed through user input.
- **A recursive alias instead of `Any` for free-form JSON**: `type Json = str | int | float | bool
  | None | list[Json] | dict[str, Json]`. Only where the shape is genuinely unknown.
- **`Protocol` with `__call__` instead of a multi-parameter `Callable`.** `Callable[[str, int,
  bool], None]` names nothing — the reader cannot tell which argument is which, and keyword
  arguments cannot be expressed at all. One parameter and an obvious return → `Callable`; two or
  more, or any keyword argument → a named calling protocol.
- **Phantom types for units**: `Seconds = NewType("Seconds", float)`. In a signature the unit
  belongs in the type, so that adding a timeout to a distance is an error rather than a bug.
- **`Iterator` vs `Iterable` in return types** — `Iterator[T]` only when the caller consumes it
  once. Returning an `Iterator` that callers re-iterate produces silent empty results the second
  time.
- **A sentinel, not `None`, when `None` is a legal value.** For PATCH-style updates, `None` cannot
  distinguish "not provided" from "explicitly null".
- **No `Result` / `Either` types.** Python signals failure with exceptions; a wrapper duplicates
  that, defeats `raise … from`, and forces every caller into manual unwrapping. The one acceptable
  use is a batch operation whose *normal output* is a mix of successes and failures — and then it
  is an explicit frozen dataclass with a `Literal` tag, not a general-purpose monad.
- **`Buffer` (PEP 688) instead of `bytes | bytearray | memoryview`**; `SupportsIndex` /
  `SupportsFloat` when only the conversion protocol is needed.
- **`assert_type()` in tests for public library APIs** — pins the inferred type so a refactor
  cannot silently widen it. `reveal_type()` is a debugging tool and never gets committed.

  ```python
  # WRONG — anonymous Callable, and None hiding two different meanings
  def register(handler: Callable[[str, int, bool], None]) -> None: ...

  def update_user(user_id: UserId, nickname: str | None = None) -> None:
      ...   # is None "leave unchanged" or "clear the nickname"?

  # CORRECT
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
  def fail_missing(entity: str, entity_id: object) -> Never:
      raise EntityNotFoundError(f"{entity} {entity_id} not found")

  def execute_ddl(statement: LiteralString) -> None: ...

  execute_ddl(f"DROP TABLE {name}")        # error: expected LiteralString

  Seconds = NewType("Seconds", float)
  Meters = NewType("Meters", float)

  def wait(duration: Seconds) -> None: ...
  wait(Meters(5.0))                        # error: incompatible type
  ```

## Enforcement

`strict = true` already turns on `disallow_any_generics`, `warn_return_any`, `strict_equality`,
`no_implicit_reexport` and the rest of that family — listing them again is noise. What it does
**not** turn on is the set below, and three of those enforce rules this file otherwise only asks
for:

```toml
[tool.mypy]
strict = true
warn_unreachable = true
extra_checks = true
strict_equality_for_none = true
enable_error_code = [
  "explicit-override",     # @override on every override — otherwise a rename orphans a method
  "exhaustive-match",      # every match over a union or Enum is closed
  "ignore-without-code",   # a bare `# type: ignore` stops being possible
  "deprecated",            # using a @deprecated name is an error, not a runtime warning
  "possibly-undefined",    # a name bound in only one branch
  "redundant-expr",        # a condition that cannot change the outcome
  "redundant-self",
  "truthy-bool",           # `if some_object:` where the object is always truthy
  "truthy-iterable",
  "unused-awaitable",      # a coroutine created and never awaited
  "unimported-reveal",     # a committed reveal_type()
]
```

- **A rule the checker can hold is a rule you stop having to remember.** `@override` on every
  override, an exhaustive `match`, a coded ignore: all three are stated elsewhere in these files
  and all three become errors here. Adding the code is the cheapest thing in this document.
- `# type: ignore[code]` always with a code and a reason; their count only ratchets down.
- A `dict[str, Any]` or an untyped `**kwargs` crossing a layer boundary is a review blocker.

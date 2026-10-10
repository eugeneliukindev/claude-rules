---
name: python-types
description: >-
  Python type design decisions: the precision ladder from a bare primitive to Literal, Enum,
  NewType, TypedDict, frozen value objects and validating models; PEP 695 generics, dispatch and
  variance; narrowing Any and object; Annotated constraints; enumerations; collections.abc
  parameter types; and the mypy error codes that enforce them. Use when choosing a representation
  for a Python value, designing a generic class or function, narrowing an unknown value, replacing
  a dict[str, Any], picking a collections.abc type, or deciding what to put in an annotation.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Types — Reference

The `types.md` rule carries the defaults; this file carries the decisions behind them.

**Choosing a `collections.abc` ABC** — which one to accept in a parameter, which to return, how to
check one at runtime, how to implement a container: see [collections-abc.md](collections-abc.md).

## Type Precision Ladder

Every value has a narrowest honest type. A wider type is a runtime check you owe later, in a place
nobody will remember to write it.

| Instead of | Use | When |
|---|---|---|
| `str` for a closed set | `Literal["csv", "json"]` | 2–4 values, one or two signatures |
| `Literal` reused across signatures | `Enum` / `StrEnum` | a name, behaviour, or 3+ users |
| `str`, `int` that must not be mixed | `NewType` | identity only, no rules |
| a primitive with rules | frozen dataclass value object | validation, invariants, operations |
| `dict[str, Any]` you don't own | `TypedDict` | fixed keys, external JSON shape |
| `dict[str, Any]` crossing a boundary | a validating boundary model | untrusted input |
| `dict` with homogeneous dynamic keys | `Mapping[UserId, Order]` | keys are data, not fields |
| `tuple[Any, ...]` | frozen dataclass | any record — never `NamedTuple` |
| `Any` | `object` + narrowing, or a `Protocol` | the value is genuinely unknown |
| several `bool` fields | one `Enum` state | the flags encode a state machine |

```python
# WRONG — every field a primitive: any string is a status, any dict a payload, any str an id
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Job:
    id: str
    status: str                    # "pending"? "PENDING"? "in-progress"?
    payload: dict[str, Any]

# CORRECT — every field at its narrowest honest type
JobId = NewType("JobId", UUID)

class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"

@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Job:
    id: JobId
    status: JobStatus
    payload: JobPayload
```

Narrow fields still combine freely: a `finished_at: datetime | None` beside `status` lets a done job
exist with no finish time. When a field belongs to one state, give each state its own variant — a
tagged union, below under `Literal` — and the combination cannot be constructed at all.

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

# CORRECT — the rule lives in the type; no instance can hold an invalid rate
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class DiscountRate:
    value: Decimal

    def __post_init__(self) -> None:
        if not Decimal(0) <= self.value <= Decimal(1):
            raise InvalidDiscountRateError(self.value)

def apply_discount(price: Money, rate: DiscountRate) -> Money:
    return price * (1 - rate.value)
```

**Dunders where the behaviour is a natural fit**, never to satisfy a style preference. `__repr__` on
every domain class that is not a dataclass: unambiguous, identifying fields, no secrets. `__eq__`
and `__hash__` come together or not at all — value objects get both from `@dataclass(frozen=True)`;
entities compare by identity and say so. A container protocol is implemented by subclassing the
matching `collections.abc` ABC, not by hand-writing every dunder. The class-creation hooks —
`__init_subclass__`, `__set_name__`, `__class_getitem__`, a metaclass — and typing them with
`ClassVar` and `dataclass_transform` are in `python-metaclasses`.

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
    published_at: str

def parse_product(raw: ProductPayload) -> Product:
    price = raw.get("price")
    return Product(
        title=raw["name"],
        price=Money.from_minor(price) if price is not None else None,
        published_at=datetime.fromisoformat(raw["published_at"]),
    )
```

Test the bound value with `is not None`, not `if raw.get("price")`: truthiness turns a price of
`0` into "no price", and a re-read `raw.get(...)` is not narrowed by the first one.

## `Literal` — Closing a Set

- **For a closed set inside one or two signatures**: `def export(fmt: Literal["csv", "json"]) ->
  bytes`. Callers are checked at type-check time; no runtime cost.
- **Promote to `Enum`** at the ladder's threshold — three or more users — or earlier when the set
  needs iteration, carries behaviour, or crosses a boundary where the wire value and the code value
  may diverge (`StrEnum` keeps them equal).
- **`Final` keeps a constant's exact value**: `DEFAULT_EXPORT_FORMAT: Final = "json"` is inferred as
  `Literal["json"]` and passes wherever the `Literal` is expected; `Final[Literal[...]]` adds
  nothing.
- **Tagged unions**: a `Literal` discriminator field (`kind: Literal["circle"]`) is what narrows a
  union of `TypedDict`s and what a validator dispatches serialized data on. Dataclass variants
  need none — a class pattern in `match` narrows them, and `assert_never` closes the match.
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
# Tagged union of dataclasses with an exhaustive match
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Circle:
    radius: Decimal

@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Rectangle:
    width: Decimal
    height: Decimal

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
    return json.loads(path.read_bytes())

# CORRECT — narrowed on the first line, never leaves
def load_settings(path: Path) -> Settings:
    raw: object = json.loads(path.read_bytes())
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{path} must contain an object")
    return Settings.parse(raw)
```

## Generics, Dispatch, and Variance

- **PEP 695 syntax from Python 3.12**: `def first[T](...)`, `class Repository[T: Entity]`. The
  parameter belongs to the signature, so nothing module-level is declared and nothing can be reused
  by accident.
- **Below 3.12 it is `TypeVar` + `Generic`, and that is not a lapse** — the `types.md` rule asks for
  PEP 695 on a 3.12+ floor, and below it the syntax does not exist yet. The same applies to the
  `typing` names that arrived with it: `typing_extensions.override` until 3.12,
  `typing_extensions.TypeIs` until 3.13. A project states its floor once, in `requires-python`, and
  every one of these choices follows from it rather than being argued per file.
- **PEP 695 type parameters are single capital letters** — `T`, `K`/`V`, `P`/`R` for
  `ParamSpec`/return. The bound carries the meaning (`[T: BaseModel]`); the letter does not need
  to, and only a generic with three or more parameters spells them out.
- **A `TypeVar` is a module-level name, so it is private and suffixed** — `_T`, `_KT`, `_VT`, `_P`,
  `_R`. Where one module declares several and the letters stop telling them apart, the role goes in
  front of the suffix, never instead of it: `_BackendT`, `_ModelT`. Variance is the PEP 484 suffix
  after it — `_ModelT_co`, `_ModelT_contra` — which is what ruff's `PLC0105` checks, and the twins
  sort together.
- **Bound the parameter when it has requirements.** An unbounded parameter whose body calls methods
  on it is a lie.
- **Parameters take `Sequence`/`Mapping`, returns are concrete** — that handles variance without
  ever writing `covariant=`.
- **`ParamSpec` + `Concatenate` for decorators**: `def logged[**P, R](func: Callable[P, R]) ->
  Callable[P, R]`. A decorator returning `Callable[..., Any]` erases type safety for every
  function it wraps.
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
# WRONG — T promises nothing although the body needs an id, and list[T] refuses a tuple
def index_by_id[T](entities: list[T]) -> dict[EntityId, T]:
    return {entity.id: entity for entity in entities}   # error: "T" has no attribute "id"

# CORRECT — the bound states the requirement; Sequence takes any read-only sequence
def index_by_id[T: Entity](entities: Sequence[T]) -> dict[EntityId, T]:
    return {entity.id: entity for entity in entities}
```

```python
# WRONG — an isinstance ladder over an open hierarchy: every new kind edits this function
def render(notification: Notification) -> str:
    if isinstance(notification, EmailNotification): ...
    elif isinstance(notification, SmsNotification): ...
    raise NotImplementedError(type(notification).__name__)

# CORRECT — each kind gets its own renderer, registered beside the generic function
@singledispatch
def render(notification: Notification) -> str:
    raise NotImplementedError(type(notification).__name__)

@render.register
def _(notification: EmailNotification) -> str: ...

@render.register
def _(notification: SmsNotification) -> str: ...
```

## Further Constructs

- **`Never` / `NoReturn` for functions that never return normally** — the checker then knows the
  code after the call is unreachable. `Never` is also the type of the impossible branch, which is
  why `assert_never(value)` works.
- **`LiteralString` (PEP 675) for parameters that must not receive interpolated input**: a query
  builder, a shell helper, a template loader. pyright accepts literals and concatenations of
  literals and rejects anything that passed through user input; mypy treats `LiteralString` as
  plain `str` and accepts every string, so under mypy the annotation documents intent and checks
  nothing.
- **A recursive alias instead of `Any` for free-form JSON**: `type Json = str | int | float | bool
  | None | list[Json] | dict[str, Json]`. Only where the shape is genuinely unknown.
- **`Protocol` with `__call__` instead of a multi-parameter `Callable`.** `Callable[[str, int,
  datetime], None]` names nothing — the reader cannot tell which argument is which, and keyword
  arguments cannot be expressed at all. One parameter and an obvious return → `Callable`; two or
  more, or any keyword argument → a named calling protocol.
- **Phantom types for units**: `Seconds = NewType("Seconds", float)`. In a signature the unit
  belongs in the type, so that passing a distance where a duration is expected is an error rather
  than a bug. Arithmetic on a `NewType` returns the base type, so the check holds at signatures,
  not inside expressions. A phantom unit type does not drop the unit from the name:
  `duration_seconds: Seconds` — the reader of a call site still has only the name. A spacecraft was
  lost to exactly this: one program reported thruster impulse in pound-force seconds, the program
  consuming it read newton-seconds, and both sides were plain floats.
- **`Iterator` vs `Iterable` in return types** — `Iterator[T]` only when the caller consumes it
  once. Returning an `Iterator` that callers re-iterate produces silent empty results the second
  time.
- **A sentinel, not `None`, when `None` is a legal value.** For PATCH-style updates, `None` cannot
  distinguish "not provided" from "explicitly null". JSON Merge Patch (RFC 7396) made that choice
  for a whole format: `null` there means "remove the key", so a merge patch can never set a value
  to null. Make the sentinel a one-member `Enum`: mypy narrows `is UNSET` on an enum member in
  every branch, but on a plain-class instance only in the `if` branch, leaving the `else` wide.
- **No `Result` / `Either` types.** Python signals failure with exceptions; a wrapper duplicates
  that, defeats `raise … from`, and forces every caller into manual unwrapping. The one acceptable
  use is a batch operation whose *normal output* is a mix of successes and failures — and then it
  is an explicit frozen dataclass with a `Literal` tag, not a general-purpose monad.
- **`Buffer` (PEP 688) instead of `bytes | bytearray | memoryview`**; `SupportsIndex` /
  `SupportsFloat` when only the conversion protocol is needed.
- **`assert_type()` in tests for public library APIs** — pins the inferred type so a refactor
  cannot silently widen it. `reveal_type()` is a debugging tool and never gets committed.

```python
# WRONG — an anonymous Callable: which argument is which, and none can be passed by keyword
def register(handler: Callable[[str, int, datetime], None]) -> None: ...

# CORRECT — a named calling protocol
class EventHandler(Protocol):
    def __call__(self, event: str, attempt: int, *, received_at: datetime) -> None: ...

def register(handler: EventHandler) -> None: ...
```

```python
# WRONG — None means both "leave unchanged" and "clear the nickname"
def update_user(user_id: UserId, nickname: str | None = None) -> None: ...

# CORRECT — absence has its own value, and None keeps its one meaning
class _Unset(Enum):
    UNSET = auto()

UNSET: Final = _Unset.UNSET

def update_user(user_id: UserId, nickname: str | None | _Unset = UNSET) -> None:
    if nickname is UNSET:
        ...        # leave unchanged
    elif nickname is None:
        ...        # clear it
    else:
        ...        # nickname is str here
```

```python
def fail_missing(entity: str, entity_id: object) -> Never:
    raise EntityNotFoundError(f"{entity} {entity_id} not found")

def execute_ddl(statement: LiteralString) -> None: ...

execute_ddl(f"DROP TABLE {name}")        # pyright: error; mypy: accepted

Seconds = NewType("Seconds", float)
Meters = NewType("Meters", float)

def wait(duration_seconds: Seconds) -> None: ...

wait(Meters(5.0))                        # error: incompatible type "Meters"
```

## Enforcement

`strict = true` already turns on `disallow_any_generics`, `warn_return_any`, `strict_equality`,
`extra_checks`, `no_implicit_reexport` and the rest of that family. What it does **not** turn on —
`warn_unreachable`, `strict_equality_for_none` and a list of error codes — is in the `[tool.mypy]`
block of `python-project`, and three of those codes enforce rules this file otherwise only asks
for: `explicit-override`, `exhaustive-match` and `ignore-without-code`.

- **A rule the checker can hold is a rule you stop having to remember.** `@override` on every
  override, an exhaustive `match`, a coded ignore: all three are stated elsewhere in these files
  and all three become errors once the codes are enabled. Adding a code is the cheapest thing in
  this document.
- `# type: ignore[code]` always with a code and a reason; their count only ratchets down.
- A `dict[str, Any]` or an untyped `**kwargs` crossing a layer boundary is a review blocker.

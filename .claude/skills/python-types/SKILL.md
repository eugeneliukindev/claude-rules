---
name: python-types
description: >-
  Chooses how a Python value is typed: the ladder from a primitive to Literal, Enum, NewType,
  TypedDict and value objects, narrowing, generics, collections.abc. Use when choosing a
  representation for a value, replacing a dict[str, Any], writing a generic or a typed decorator,
  narrowing an unknown value, or deciding an annotation.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Types — Reference

The `types.md` rule carries the defaults; this file carries the decisions behind them.

## Choosing a Representation

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

### Every value takes its narrowest honest type

**Why:** a wider type is a runtime check you owe later, in a place nobody will remember to write it
— any string is a status, any dict a request, any `str` an id. Narrow fields still combine freely:
a `finished_at: datetime | None` beside `status` lets a done job exist with no finish time, and a
field that belongs to one state is a tagged union (Closed Sets, below).

**Example:**
```python
# WRONG — every field a primitive: "pending", "PENDING" and "in-progress" are all statuses
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ExportJob:
    job_id: str
    status: str
    request: dict[str, Any]


# CORRECT — every field at its narrowest honest type
ExportJobId = NewType("ExportJobId", UUID)


class ExportJobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ExportJob:
    job_id: ExportJobId
    status: ExportJobStatus
    request: ExportRequest
```

## Value Objects

### A primitive with rules is a frozen value object, valid by construction

**Why:** a rule checked at the call sites is checked at some of them. Choose by behaviour: a plain
`str`, `int` or `Decimal` for a value with no rules; `NewType` for identity only, at no runtime
cost; a frozen dataclass for validation, invariants or operations — `Money`, `Email`, `DateRange`
— validated in `__post_init__` with the package's own error, after which no function re-validates
it. Promotion is one-way: a `NewType` that grows its first rule becomes a value object everywhere.
Value objects compare by value, are hashable and carry no I/O.

**Example:**
```python
# WRONG — the range rule lives in the function, and every other caller of the floats skips it
def distance_km(
    from_latitude: float, from_longitude: float, to_latitude: float, to_longitude: float
) -> float:
    if not (-90 <= from_latitude <= 90 and -90 <= to_latitude <= 90):
        raise ValueError("latitude out of range")
    return haversine_km(from_latitude, from_longitude, to_latitude, to_longitude)


# CORRECT — no Coordinates instance can hold an impossible point
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Coordinates:
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if not (-90 <= self.latitude <= 90 and -180 <= self.longitude <= 180):
            raise InvalidCoordinatesError(self.latitude, self.longitude)


def distance_km(origin: Coordinates, destination: Coordinates) -> float:
    return haversine_km(
        origin.latitude, origin.longitude, destination.latitude, destination.longitude
    )
```

### A field says what it holds: secrets out of `repr`, ids and timestamps out of equality

**Why:** the generated `repr` prints a secret into the first log line that formats the object, and
an `issued_at` in `__eq__` makes two copies of one credential unequal. A mutable or computed default
is `field(default_factory=...)`; validation and derived fields go in `__post_init__`, through
`object.__setattr__` when frozen; a modified copy comes from `dataclasses.replace()`.

**Example:**
```python
# WRONG — repr shows the secret, and a re-issued copy compares unequal
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ApiCredential:
    client_id: str
    secret: str
    issued_at: datetime


# CORRECT — each field states where it may appear
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ApiCredential:
    client_id: str
    secret: str = field(repr=False)
    issued_at: datetime = field(compare=False)
```

### A dunder is written where the behaviour fits, and `__eq__` comes with `__hash__`

**Why:** a class that defines `__eq__` alone gets `__hash__ = None`, and its first use as a set
member or a dict key raises `TypeError: unhashable type`. Value objects get both from
`@dataclass(frozen=True)`; an entity compares by identity and says so in both. A domain class that
is not a dataclass has a `__repr__` naming its identity and no secret; a container subclasses its
`collections.abc` ABC. Class-creation hooks — `__init_subclass__`, `__set_name__`, a metaclass —
are in `python-metaclasses`.

**Example:**
```python
# WRONG — equality without a hash: {account} raises TypeError
@final
class Account:
    def __init__(self, *, account_id: AccountId, owner: str) -> None:
        self.account_id = account_id
        self.owner = owner

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Account) and other.account_id == self.account_id


# CORRECT — the entity's identity decides both equality and the hash
@final
class Account:
    def __init__(self, *, account_id: AccountId, owner: str) -> None:
        self.account_id = account_id
        self.owner = owner

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Account) and other.account_id == self.account_id

    @override
    def __hash__(self) -> int:
        return hash(self.account_id)
```

## `TypedDict`

### Dict-shaped data that stays a dict is a `TypedDict`, turned into a domain object where it enters

**Why:** a JSON payload you don't own, a `**kwargs` bundle, a driver row, a file read back — the
`TypedDict` names the keys so `row["labels"]` stops being `Any`, at no runtime cost. A file read
back stays dicts: converting every row costs more than it returns when most of the file is only
counted or filtered. It has no validation, methods or `isinstance`, so it is never a domain type.
Keys are marked `NotRequired[...]` or `Required[...]`, not `total=False`; `ReadOnly[...]` for keys
consumers must not change; `Unpack[Options]` types a forwarded `**kwargs`.

**Example:**
```python
# WRONG — the keys exist only in the author's head, and the dict travels inward
def parse_product(raw: dict[str, Any]) -> dict[str, Any]:
    return {"title": raw["name"], "price_cents": raw.get("price_cents")}


# CORRECT — the TypedDict describes the foreign JSON; a domain object travels inward
class ProductPayload(TypedDict):
    name: str
    price_cents: NotRequired[int | None]
    published_at: str


def parse_product(raw: ProductPayload) -> Product:
    price_cents = raw.get("price_cents")
    return Product(
        title=raw["name"],
        # is not None, not truthiness: a price of zero is a price
        price=Money.from_cents(price_cents) if price_cents is not None else None,
        published_at=datetime.fromisoformat(raw["published_at"]),
    )
```

## `Annotated`

### A constraint the type cannot express is an `Annotated` alias, named once

**Why:** `Literal` narrows which values; `Annotated` attaches rules the static type has no room for
— bounds, a pattern, a dependency marker — read at runtime by whatever validates the boundary;
`annotated_types` spells the bounds every validator reads. The
same bounds in five models are five places to get one wrong. A bound restated in a service body
means the boundary leaked: domain code receives values that are already valid.

**Example:**
```python
# WRONG — one limit, written into every query model
@dataclass(frozen=True, slots=True, kw_only=True)
class ArticleQuery:
    page_size: Annotated[int, Interval(ge=1, le=200)] = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class CommentQuery:
    page_size: Annotated[int, Interval(ge=1, le=200)] = 50


# CORRECT — the constrained type is named once and travels with its name
type PageSize = Annotated[int, Interval(ge=1, le=200)]


@dataclass(frozen=True, slots=True, kw_only=True)
class ArticleQuery:
    page_size: PageSize = 50


@dataclass(frozen=True, slots=True, kw_only=True)
class CommentQuery:
    page_size: PageSize = 50
```

## Closed Sets

### A closed set in one or two signatures is a `Literal`; reused, it is an `Enum`

**Why:** the checker rejects `"jpeg"` at the call site, where a `str` lets the function raise in
the caller's process. Promote to `Enum` at three users, or earlier when the set needs iteration,
behaviour, or crosses a boundary where wire and code values may diverge. `Final` keeps a constant's
exact value — `DEFAULT_IMAGE_FORMAT: Final = "png"` passes where the `Literal` is expected; a
`Literal[True]` parameter is a boolean flag with extra syntax.

**Example:**
```python
# WRONG — any string is accepted, and the mistake surfaces as a ValueError at runtime
def render_chart(chart: Chart, image_format: str) -> bytes:
    if image_format == "png":
        return chart.to_png()
    if image_format == "svg":
        return chart.to_svg()
    raise ValueError(f"unsupported image format {image_format!r}")


# CORRECT — render_chart(chart, "jpeg") is a type error
def render_chart(chart: Chart, image_format: Literal["png", "svg"]) -> bytes:
    if image_format == "png":
        return chart.to_png()
    return chart.to_svg()
```

### An enumeration's kind follows its use, and a member is compared to a member

**Why:** `StrEnum` serializes as its value with no `.value`; `IntEnum` equals the integer codes it
replaces; `Flag` combines bits; a plain `Enum` with `auto()` has no wire form to leak. A comparison
with a raw literal survives a renamed value and turns false without an error. An enum is a
singular noun, its members states or kinds.

### A field that belongs to one state makes each state its own variant

**Why:** a status beside optional fields lets a delivered shipment have no delivery time. Variants
make that combination unconstructable, a class pattern in `match` narrows each one, and
`assert_never` turns a new variant into a type error at every `match` that misses it. A union of
`TypedDict`s narrows on a `Literal` field — `kind: Literal["in_transit"]` — the same field a
validator dispatches serialized data on.

**Example:**
```python
# WRONG — any combination of status and optional fields can be built
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Shipment:
    status: ShipmentStatus
    tracking_number: str | None = None
    delivered_at: datetime | None = None


# CORRECT — each state carries exactly its own fields, and the match is exhaustive
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class AwaitingPickup:
    warehouse: str


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class InTransit:
    tracking_number: str


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Delivered:
    tracking_number: str
    delivered_at: datetime


type Shipment = AwaitingPickup | InTransit | Delivered


def describe(shipment: Shipment) -> str:
    match shipment:
        case AwaitingPickup(warehouse=warehouse):
            return f"waiting at {warehouse}"
        case InTransit(tracking_number=tracking_number):
            return f"in transit, tracking {tracking_number}"
        case Delivered(delivered_at=delivered_at):
            return f"delivered {delivered_at:%Y-%m-%d %H:%M}"
        case _:
            assert_never(shipment)
```

## Narrowing

### An unknown value is `object`, narrowed at once; `Any` stays only where a library put it

**Why:** `Any` turns checking off, and a function returning it spreads that silence to every
caller. Two positions earn it: an untyped third-party edge, narrowed on the next line; and a
signature a library fixes — a validator, a hook — where `Any` stays in exactly the library's
position and the arguments you control are typed. A return type is never widened to skip a branch:
`-> Playlist | None` on a function that always returns one makes every caller check for nothing.

### `cast()` is a claim; `isinstance` or a `TypeIs` predicate is a check

**Why:** `cast` changes the type and checks nothing, so a wrong claim fails far from where it was
made; it stays only with a one-line reason the checker cannot see. A narrowing needed twice is a
`TypeIs` predicate — 3.13, or `typing_extensions` below — named like any boolean.

**Example:**
```python
# WRONG — the claim is believed, and a list of ints fails three calls later
def tag_names(payload: Mapping[str, object]) -> list[str]:
    return cast(list[str], payload["tags"])


# CORRECT — the predicate checks what the annotation then promises
def is_string_list(value: object) -> TypeIs[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def tag_names(payload: Mapping[str, object]) -> list[str]:
    tags = payload["tags"]
    if not is_string_list(tags):
        raise MalformedPayloadError("tags must be a list of strings")
    return tags
```

## Generics

**Before writing a generic class or function, a type parameter, a decorator, an `@overload` or a
dispatch on an argument's type, read [generics.md](generics.md)** — PEP 695 on the floor that has
it, parameter names and bounds, variance, `ParamSpec`, `@overload`, `singledispatch`.

## `collections.abc`

**Before choosing a parameter's collection type, checking a value against a container type at
runtime, or implementing a container, read [collections-abc.md](collections-abc.md)** — the
annotation table, a bare `str` as a `Sequence[str]`, `numbers`, subclassing the ABC instead of
`dict`.

## Further Constructs

**Before writing a function that always raises, a parameter that must stay a literal string, a
free-form JSON value, a callback with several parameters, a unit of measure in a signature, a
returned generator, a runtime protocol check, a type pinned in a test, an "unset" default beside
`None`, a batch that collects failures, or bytes-like input, read [constructs.md](constructs.md)**
— `Never`, `LiteralString`, a recursive JSON alias, calling protocols, unit types, `Iterator`
returns, `assert_type`, sentinels, batch results, `Buffer`.

## Enforcement

`strict = true` turns on `disallow_any_generics`, `warn_return_any`, `strict_equality`,
`extra_checks`, `no_implicit_reexport` and the rest of that family. What it does **not** turn on —
`warn_unreachable`, `strict_equality_for_none` and a list of error codes — is in the `[tool.mypy]`
block of `python-project`; three of those codes turn rules into errors: `explicit-override`,
`exhaustive-match` and `ignore-without-code`. A rule the checker holds is a rule nobody has to
remember, and adding a code is the cheapest change in this file. A `dict[str, Any]` or an untyped
`**kwargs` crossing a layer boundary is a review blocker.

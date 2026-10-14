---
name: python-types
description: >-
  Chooses how a Python value is typed: the ladder from a primitive to Literal, Enum, NewType,
  TypedDict and value objects, narrowing, generics, collections.abc. Use when choosing a
  representation for a value, replacing a dict[str, Any], writing a generic or a typed decorator,
  narrowing an unknown value, or deciding an annotation. Not for a metaclass or a descriptor
  (python-metaclasses).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Types — Reference

`types.md` carries the defaults and `naming.md` how an alias or a `NewType` is named; this skill
carries the decisions behind them. Class-creation hooks — `__init_subclass__`, `__set_name__`, a
metaclass — are in `python-metaclasses`.

## Choosing a Representation

| Instead of | Use | When |
|---|---|---|
| `str` for a closed set | `Literal["fits", "csv"]` | 2–4 values, one or two signatures |
| `Literal` reused across signatures | `Enum` / `StrEnum` | a name, behaviour, or 3+ users |
| `str`, `int` that must not be mixed | `NewType` | identity only, no rules |
| a primitive with rules | frozen dataclass value object | validation, invariants, operations |
| `dict[str, Any]` you don't own | `TypedDict` | fixed keys, external JSON shape |
| `dict[str, Any]` crossing a boundary | a validating boundary model | untrusted input |
| `dict` with homogeneous dynamic keys | `Mapping[TargetId, Exposure]` | keys are data, not fields |
| `tuple[Any, ...]` | frozen dataclass | any record — never `NamedTuple` |
| several `bool` fields | one `Enum` state | the flags encode a state machine |

### Every value takes its narrowest honest type

**Why:** a wider type is a runtime check you owe later, in a place nobody will remember to write it
— any string is a status, any dict a target, any `str` an id. Narrow fields still combine freely:
a `reduced_at: datetime | None` beside `status` lets a reduced observation exist with no reduction
time, and a field that belongs to one state is a tagged union (Closed Sets, below).

**Example:**
```python
# WRONG — every field a primitive: "queued", "QUEUED" and "in-queue" are all statuses
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Observation:
    observation_id: str
    status: str
    target: dict[str, Any]


# CORRECT — every field at its narrowest honest type
ObservationId = NewType("ObservationId", UUID)


class ObservationStatus(StrEnum):
    QUEUED = "queued"
    EXPOSING = "exposing"
    REDUCED = "reduced"
    FAILED = "failed"


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Observation:
    observation_id: ObservationId
    status: ObservationStatus
    target: Target
```

## Value Objects

### A primitive with rules is a frozen value object, valid by construction

**Why:** a rule checked at the call sites is checked at some of them. Choose by behaviour: a plain
`str`, `int` or `Decimal` for a value with no rules; `NewType` for identity only; a frozen
dataclass for validation, invariants or operations, validated in `__post_init__` with the
package's own error, after which no function re-validates it. Promotion is one-way: a `NewType`
that grows its first rule becomes a value object everywhere. Value objects compare by value, are
hashable and carry no I/O.

**Example:**
```python
# WRONG — the range rule lives in the function, and every other caller of the floats skips it
def angular_separation_degrees(
    first_ra_degrees: float,
    first_dec_degrees: float,
    second_ra_degrees: float,
    second_dec_degrees: float,
) -> float:
    if not (-90 <= first_dec_degrees <= 90 and -90 <= second_dec_degrees <= 90):
        raise ValueError("declination out of range")
    return great_circle_degrees(
        first_ra_degrees, first_dec_degrees, second_ra_degrees, second_dec_degrees
    )


# CORRECT — no SkyPosition instance can hold an impossible point
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class SkyPosition:
    right_ascension_degrees: float
    declination_degrees: float

    def __post_init__(self) -> None:
        if not (0 <= self.right_ascension_degrees < 360 and -90 <= self.declination_degrees <= 90):
            raise InvalidSkyPositionError(self.right_ascension_degrees, self.declination_degrees)


def angular_separation_degrees(first: SkyPosition, second: SkyPosition) -> float:
    return great_circle_degrees(
        first.right_ascension_degrees,
        first.declination_degrees,
        second.right_ascension_degrees,
        second.declination_degrees,
    )
```

## Fields and Dunders

**Before giving a dataclass field a `field()` option, a computed value or a `__post_init__`, or
writing `__eq__`, `__hash__` or `__repr__` by hand, read
[fields-and-dunders.md](fields-and-dunders.md)** — secrets out of `repr`, timestamps out of
equality, `__eq__` with `__hash__`.

- A field says what it holds: secrets out of `repr`, ids and timestamps out of equality
- A dunder is written where the behaviour fits, and `__eq__` comes with `__hash__`

## Dict Shapes and Constraints

**Before typing data that stays a dict — a foreign JSON payload, a `**kwargs` bundle, a driver
row — or attaching a bound or a pattern the static type cannot express, read
[dict-shapes.md](dict-shapes.md)** — `TypedDict` turned into a domain object where it enters,
`NotRequired` and `ReadOnly`, `Unpack`, one `Annotated` alias per constraint.

- Dict-shaped data that stays a dict is a `TypedDict`, turned into a domain object where it enters
- A constraint the type cannot express is an `Annotated` alias, named once

## Closed Sets

### A closed set in one or two signatures is a `Literal`; reused, it is an `Enum`

**Why:** the checker rejects `"votable"` at the call site, where a `str` lets the function raise
in the caller's process. Promote to `Enum` at three users, or earlier when the set needs
iteration, behaviour, or crosses a boundary where wire and code values may diverge. `Final` keeps a
constant's exact value — `DEFAULT_CURVE_FORMAT: Final = "fits"` passes where the `Literal` is
expected; a `Literal[True]` parameter is a boolean flag with extra syntax.

**Example:**
```python
# WRONG — any string is accepted, and the mistake surfaces as a ValueError at runtime
def export_light_curve(curve: LightCurve, file_format: str) -> bytes:
    if file_format == "fits":
        return curve.to_fits()
    if file_format == "csv":
        return curve.to_csv()
    raise ValueError(f"unsupported file format {file_format!r}")


# CORRECT — export_light_curve(curve, "votable") is a type error
def export_light_curve(curve: LightCurve, file_format: Literal["fits", "csv"]) -> bytes:
    if file_format == "fits":
        return curve.to_fits()
    return curve.to_csv()
```

### An enumeration's kind follows its use, and a member is compared to a member

**Why:** `StrEnum` serializes as its value with no `.value`; `IntEnum` equals the integer codes it
replaces; `Flag` combines bits; a plain `Enum` with `auto()` has no wire form to leak. A comparison
with a raw literal survives a renamed value and turns false without an error.

### A field that belongs to one state makes each state its own variant

**Why:** a status beside optional fields lets an observed visit have no observation time. Variants
make that combination unconstructable, a class pattern in `match` narrows each one, and
`assert_never` turns a new variant into a type error at every `match` that misses it. A union of
`TypedDict`s narrows on a `Literal` field — `kind: Literal["observed"]` — the same field a
validator dispatches serialized data on.

**Example:**
```python
# WRONG — any combination of status and optional fields can be built
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class TargetVisit:
    status: VisitStatus
    observed_at: datetime | None = None
    frame_count: int | None = None


# CORRECT — each state carries exactly its own fields, and the match is exhaustive
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Scheduled:
    window_opens_at: datetime


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Observed:
    observed_at: datetime
    frame_count: int


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class LostToWeather:
    reason: str


type TargetVisit = Scheduled | Observed | LostToWeather


def summarize_visit(visit: TargetVisit) -> str:
    match visit:
        case Scheduled(window_opens_at=window_opens_at):
            return f"window opens {window_opens_at:%Y-%m-%d %H:%M}"
        case Observed(frame_count=frame_count):
            return f"observed, {frame_count} frames"
        case LostToWeather(reason=reason):
            return f"lost to weather: {reason}"
        case _:
            assert_never(visit)
```

## Narrowing

### `cast()` is a claim; `isinstance` or a `TypeIs` predicate is a check

**Why:** `cast` changes the type and checks nothing, so a wrong claim fails far from where it was
made; it stays only with a one-line reason the checker cannot see. A narrowing needed twice is a
`TypeIs` predicate — 3.13, or `typing_extensions` below — named like any boolean. An unknown value
is narrowed on the line it arrives (`types.md`).

**Example:**
```python
# WRONG — the claim is believed, and a list of ints fails three calls later
def filter_bands(header: Mapping[str, object]) -> list[str]:
    return cast(list[str], header["filters"])


# CORRECT — the predicate checks what the annotation then promises
def is_string_list(value: object) -> TypeIs[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def filter_bands(header: Mapping[str, object]) -> list[str]:
    filters = header["filters"]
    if not is_string_list(filters):
        raise MalformedFitsHeaderError("filters must be a list of strings")
    return filters
```

## Generics

**Before writing a generic class or function, a type parameter, a decorator, an `@overload` or a
dispatch on an argument's type, read [generics.md](generics.md)** — PEP 695 on the floor that has
it, parameter names and bounds, variance, `ParamSpec`, `@overload`, `singledispatch`.

- PEP 695 syntax on a 3.12 floor; `TypeVar` and `Generic` below it, and neither is a lapse
- A PEP 695 parameter is one capital letter; a `TypeVar` is private and suffixed
- A type parameter the body relies on is bounded, and a parameter takes a read-only collection
- A decorator keeps the signature it wraps, through `ParamSpec`
- `@overload` is for one function with several signatures, never for two functions
- Behaviour that varies by an argument's type over an open set is `singledispatch`

## `collections.abc`

**Before choosing a parameter's collection type, checking a value against a container type at
runtime, or implementing a container, read [collections-abc.md](collections-abc.md)** — the
annotation table, a bare `str` as a `Sequence[str]`, `numbers`, subclassing the ABC instead of
`dict`.

- `Sequence[str]` also accepts a bare `str`, so a function that means "several" guards it
- `numbers.Real` and `numbers.Integral` stay out of annotations
- A runtime check asks the ABC, never `hasattr` or a concrete type
- A number from elsewhere is checked against `numbers.Real`; one you parsed, `int` and `float`
- A container subclasses its ABC and implements only the abstract methods — never `dict` or `list`

## Further Constructs

**Before writing a function that always raises, a parameter that must stay a literal string, a
free-form JSON value, a callback with several parameters, a unit of measure in a signature, a
returned generator, a runtime protocol check, a type pinned in a test, an "unset" default beside
`None`, a batch that collects failures, or bytes-like input, read [constructs.md](constructs.md)**
— `Never`, `LiteralString`, a recursive JSON alias, calling protocols, unit types, `Iterator`
returns, `assert_type`, sentinels, batch results, `Buffer`.

- A function that never returns normally returns `Never`
- A parameter that must not receive interpolated input is `LiteralString`
- Free-form JSON is a recursive alias, not `Any`
- A callable with two or more parameters, or any keyword, is a calling protocol
- A quantity crossing a signature carries its unit in the type as well as the name
- A returned `Iterator` is consumed once; anything read twice returns a collection
- `isinstance` against a runtime-checkable `Protocol` checks names, not signatures
- A public library API pins its inferred types with `assert_type` in its tests
- When `None` is a legal value, absence is a one-member `Enum` sentinel
- Failure is an exception; a batch whose normal output mixes outcomes returns tagged variants
- Bytes-like input is `Buffer`; an integer-like index is `SupportsIndex`

## Enforcement

`strict = true` leaves off `warn_unreachable`, `strict_equality_for_none` and the error codes
`explicit-override`, `exhaustive-match` and `ignore-without-code`; enabling them in `[tool.mypy]`
turns three rules into errors, and a rule the checker holds is one nobody has to remember.

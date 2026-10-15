---
name: python-types
description: >-
  Chooses how a Python value is typed: the ladder from a primitive to Literal, Enum, NewType,
  TypedDict and value objects, narrowing, generics, collections.abc. ALWAYS invoke this skill when a
  task gives dicts or strings a real type, replaces a dict[str, Any], fixes KeyErrors or key typos,
  adds a value object, a generic or a typed decorator. Do not choose a representation directly.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Types — Reference

`types.md` carries the defaults and `naming.md` how an alias or a `NewType` is named; this skill
carries the decisions behind them.

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
| `Any` for genuinely unknown JSON | `type Json = str \| int \| float \| bool \| None \| list[Json] \| dict[str, Json]` | the shape is truly free-form |
| `tuple[Any, ...]` | frozen dataclass | any record — never `NamedTuple` |
| several `bool` fields | one `Enum` state | the flags encode a state machine |

### Every value takes its narrowest honest type

**Why:** a wider type is a runtime check you owe later, in a place nobody will remember to write it
— any string is a status, any dict a target, any `str` an id; `Any` stops checking at the first
subscript, where the recursive `Json` alias keeps every level a union to narrow. Narrow fields
still combine freely: a `reduced_at: datetime | None` beside `status` lets a reduced observation
exist with no reduction time, and a field that belongs to one state is a tagged union (Closed
Sets, below).

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
`str`, `int` or `Decimal` for a value with no rules; `NewType` for identity only — a type alias
(`type Designation = str`) is a name for the reader and the checker accepts any `str` for it; a
frozen dataclass for validation, invariants or operations, validated in `__post_init__` with the
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

### A quantity crossing a signature carries its unit in the type as well as the name

**Why:** with plain floats an angle in degrees passes where radians are expected. A Mars orbiter
was lost to exactly this: one program reported thruster impulse in pound-force seconds, the one
consuming it read newton-seconds, and both sides were plain floats. Arithmetic on a `NewType`
returns the base type, so the check holds at signatures, not inside expressions — which is why the
name keeps its unit too (`naming.md`).

### A field says what it holds: secrets out of `repr`, ids and timestamps out of equality

**Why:** the generated `repr` prints a secret into the first log line that formats the object —
`field(repr=False)` — and an `issued_at` in `__eq__` makes two copies of one credential unequal —
`field(compare=False)`. A class that defines `__eq__` by hand defines `__hash__` beside it, or its
first use as a set member raises `TypeError`.

## Dict Shapes and Constraints

### Dict-shaped data that stays a dict is a `TypedDict`, turned into a domain object where it enters

**Why:** a JSON payload you don't own, a `**kwargs` bundle, a driver row, a file read back — the
`TypedDict` names the keys so `entry["designation"]` stops being `Any`, at no runtime cost. A file
read back stays dicts: converting every row costs more than it returns when most of the file is
only counted or filtered. It has no validation, methods or `isinstance`, so it is never a domain
type. Keys are marked `NotRequired[...]` or `Required[...]`, not `total=False`; `ReadOnly[...]` for
keys consumers must not change; `Unpack[Options]` types a forwarded `**kwargs`.

**Example:**
```python
# WRONG — the keys exist only in the author's head, and the dict travels inward
def parse_catalogue_entry(raw: dict[str, Any]) -> dict[str, Any]:
    return {"designation": raw["name"], "magnitude": raw.get("v_magnitude")}

# CORRECT — the TypedDict describes the foreign JSON; a domain object travels inward
class CatalogueEntryPayload(TypedDict):
    name: str
    v_magnitude: NotRequired[float | None]
    discovered_at: str

def parse_catalogue_entry(raw: CatalogueEntryPayload) -> CatalogueStar:
    v_magnitude = raw.get("v_magnitude")
    return CatalogueStar(
        designation=raw["name"],
        # is not None, not truthiness: Vega's magnitude is zero
        apparent_magnitude=Magnitude(v_magnitude) if v_magnitude is not None else None,
        discovered_at=datetime.fromisoformat(raw["discovered_at"]),
    )
```

### A constraint the type cannot express is an `Annotated` alias, named once

**Why:** `Annotated` attaches rules the static type has no room for — bounds, a pattern — read at
runtime by whatever validates the boundary: `type ExposureSeconds = Annotated[float, Interval(gt=0,
le=3600)]`. The same bounds in five models are five places to get one wrong, and a bound restated
in a service body means the boundary leaked.

## Closed Sets

### A closed set in one or two signatures is a `Literal`; reused, an `Enum` of the kind its use calls for, and a member is compared to a member

**Why:** the checker rejects `"votable"` at the call site, where a `str` lets the function raise in
the caller's process. Promote to `Enum` at three users, or earlier when the set needs iteration,
behaviour, or crosses a boundary where wire and code values may diverge. `Final` keeps a constant's
exact value — `DEFAULT_CURVE_FORMAT: Final = "fits"` passes where the `Literal` is expected.
`StrEnum` serializes as its value with no `.value`; `IntEnum` equals the integer codes it replaces;
a plain `Enum` with `auto()` has no wire form to leak. A comparison with a raw literal survives a
renamed value and turns false without an error.

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

### A field that belongs to one state makes each state its own variant

**Why:** a status beside optional fields lets an observed visit have no observation time. Variants
make that combination unconstructable, a class pattern in `match` narrows each one, and
`assert_never` turns a new variant into a type error at every `match` that misses it. A union of
`TypedDict`s narrows on a `Literal` field — `kind: Literal["observed"]` — the same field a
validator dispatches serialized data on. A batch whose normal output mixes successes and failures
is such a union too — `ParsedLine | RejectedLine` — never a generic `Result` wrapper; any other
failure is an exception.

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

### When `None` is a legal value, absence is a one-member `Enum` sentinel

**Why:** in a PATCH-style update `None` cannot tell "not provided" from "explicitly cleared". A
public `class NotGiven(Enum): NOT_GIVEN = auto()` with `NOT_GIVEN: Final = NotGiven.NOT_GIVEN`
gives absence its own value — `common_name: str | None | NotGiven = NOT_GIVEN` — and `is NOT_GIVEN`
narrows an enum member in every branch, a plain-class instance only in the `if`.

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

### A runtime check asks the ABC, never `hasattr`, a concrete type or a runtime-checkable `Protocol`

**Why:** `isinstance(value, dict)` refuses a `MappingProxyType` or a `ChainMap`, and
`hasattr(value, "keys")` accepts anything with that one attribute; `isinstance` against a
`@runtime_checkable` `Protocol` checks names, not signatures, so a `park()` missing a parameter
passes and fails at the call. A `str` or `bytes` guard comes before an `Iterable` or `Sequence`
check, since both are sequences.

## Generics and Callables

### PEP 695 syntax on a 3.12 floor, a parameter one capital letter; `TypeVar` and `Generic` below it, a `TypeVar` private and suffixed, and neither is a lapse

**Why:** a PEP 695 parameter belongs to its signature, so nothing module-level is declared and
nothing is reused by accident; below 3.12 the syntax does not exist. The same floor decides the
names that came with it — `typing_extensions.override` until 3.12, `typing_extensions.TypeIs` until
3.13 — and a parameter default (PEP 696, `class Catalogue[T = Star]`), which is a syntax error on
3.12. A project states its floor once, in
`requires-python`, and every one of these choices follows from it rather than being argued per file.
The bound carries the meaning (`[T: Frame]`), so the letter need not — `T`, `K` and `V`, `P` and `R`
for `ParamSpec` and return; only a generic with three or more parameters spells them out. A
`TypeVar` is a module-level name, so it is private and takes the PEP 484 suffix — `_T`, `_KT`,
`_VT`, `_P`, `_R`; where several share a module, the role goes in front of the suffix — `_FrameT`,
`_TargetT` — and variance after it, `_FrameT_co`.

### A type parameter is declared in the signature that uses it, and bounded when the body relies on it

**Why:** on a 3.12 floor, `def load_frames[T: Frame](frame_type: type[T]) -> list[T]` scopes the
parameter to its one function, where a module-level `TypeVar` is shared by accident; below 3.12 the
syntax does not exist, and the floor in `requires-python` decides it once. An unbounded parameter
whose body reads an attribute promises callers more than it can keep. The bound carries the
meaning, so the letter need not — `T`, `K` and `V`, `P` and `R`; a module-level `TypeVar` is
private, `_T`, `_FrameT_co`.

### A decorator keeps the signature it wraps, through `ParamSpec`

**Why:** a decorator returning `Callable[..., Any]` erases the parameters and the return type of
every function it touches, and no call through it is checked again. `Concatenate[Telescope, P]`
types one that supplies the first argument itself.

**Example:**
```python
# WRONG — every decorated function now accepts anything and returns Any
def reduction_step(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        logger.debug("reduction step starts", extra={"step": func.__qualname__})
        return func(*args, **kwargs)

    return wrapper

# CORRECT — the wrapper has exactly the parameters and the return of what it wraps
def reduction_step[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.debug("reduction step starts", extra={"step": func.__qualname__})
        return func(*args, **kwargs)

    return wrapper
```

### A callable with two or more parameters, or any keyword, is a calling protocol

**Why:** `Callable[[str, float, datetime], None]` names nothing — the reader cannot tell which
argument is which, and a keyword argument cannot be expressed at all. One parameter and an obvious
return stay a `Callable`.

**Example:**
```python
# WRONG — which argument is which, and none can be passed by keyword
def follow_transients(
    handler: Callable[[str, float, datetime], None], *, alerts: AlertStream
) -> None:
    alerts.add_handler(handler)

# CORRECT — a named calling protocol
class TransientHandler(Protocol):
    def __call__(self, designation: str, magnitude: float, *, detected_at: datetime) -> None: ...

def follow_transients(handler: TransientHandler, *, alerts: AlertStream) -> None:
    alerts.add_handler(handler)
```

## `collections.abc`

| You only need to… | Annotate the parameter as | Never as |
|---|---|---|
| iterate once | `Iterable[T]` | `list[T]` |
| iterate, know the length, index | `Sequence[T]` | `list[T]`, `tuple[T, ...]` |
| mutate in place | `MutableSequence[T]` | `list[T]` |
| look up by key, iterate keys | `Mapping[K, V]` | `dict[K, V]` |
| add / remove keys | `MutableMapping[K, V]` | `dict[K, V]` |
| test membership, no duplicates | `Set[T]` (alias `AbstractSet`) | `set[T]`, `frozenset[T]` |
| call it with one argument | `Callable[[A], R]` — two or more: a calling `Protocol` | `object` |
| read/write bytes or text | `typing.IO[bytes]`, `typing.TextIO` | `object` |
| a real number, `int` included | `float` (accepts `int`, PEP 484) | `numbers.Real` |

A return is concrete — `-> list[Exposure]` — unless it deliberately hides the container:
`-> Mapping[...]` for a read-only view, `-> Iterator[Frame]` for a generator, which says "read
once" where an `Iterable` return invites a second loop that silently sees nothing. Attributes and
dataclass fields follow the same rule: `exposures: Sequence[Exposure]` when read-only. A contract
of your own is written only when no standard ABC names the capability.


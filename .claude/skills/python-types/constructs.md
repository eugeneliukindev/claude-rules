# Further Constructs

## Contents

- Control flow the checker follows: `Never`, `LiteralString`
- Shapes: a recursive JSON alias, a calling protocol, a unit type, an `Iterator` return
- Checks and markers: a runtime protocol check, `assert_type`
- Absence and failure: a sentinel beside `None`, a batch result instead of `Result`
- Narrow standard protocols: `Buffer`, `SupportsIndex`

## Control Flow the Checker Follows

### A function that never returns normally returns `Never`

**Why:** with `-> None` the checker assumes the call can return, and the code after it keeps the
type it had before; with `Never` it knows that line is unreachable and narrows. `NoReturn` is the
older spelling of the same type, which is also why `assert_never` works.

### A parameter that must not receive interpolated input is `LiteralString`

**Why:** a query builder, a shell helper or a template loader is safe only with text written in
the source. pyright accepts literals and concatenations of literals and rejects anything that
passed through input; mypy treats `LiteralString` as `str` and accepts every string, so under mypy
the annotation documents intent and checks nothing.

**Example:**
```python
# WRONG — any string, including one built from a request
def query_catalogue(statement: str, *, catalogue: CatalogueDatabase) -> list[CatalogueStar]:
    return catalogue.execute(statement)


# CORRECT — pyright rejects query_catalogue(f"... WHERE name = '{name}'", ...); mypy accepts it
def query_catalogue(
    statement: LiteralString, *, catalogue: CatalogueDatabase
) -> list[CatalogueStar]:
    return catalogue.execute(statement)
```

## Shapes

### Free-form JSON is a recursive alias, not `Any`

**Why:** `Any` stops checking at the first subscript; a recursive alias keeps every level a union
the code has to narrow. It is only for a shape that is genuinely unknown — a known one is a model
or a `TypedDict`. A `type` statement is evaluated lazily, so the recursion needs no quotes.

**Example:**
```python
# WRONG — metadata["anything"]["at"]["all"] type-checks
def count_metadata_values(metadata: Any) -> int:
    if isinstance(metadata, dict):
        return sum(count_metadata_values(value) for value in metadata.values())
    if isinstance(metadata, list):
        return sum(count_metadata_values(item) for item in metadata)
    return 1


# CORRECT — each level is a union the function narrows
type Json = str | int | float | bool | None | list[Json] | dict[str, Json]


def count_metadata_values(metadata: Json) -> int:
    if isinstance(metadata, dict):
        return sum(count_metadata_values(value) for value in metadata.values())
    if isinstance(metadata, list):
        return sum(count_metadata_values(item) for item in metadata)
    return 1
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

### A quantity crossing a signature carries its unit in the type as well as the name

**Why:** with plain floats an angle in degrees passes where radians are expected. A Mars orbiter
was lost to exactly this: one program reported thruster impulse in pound-force seconds, the one
consuming it read newton-seconds, and both sides were plain floats. Arithmetic on a `NewType`
returns the base type, so the check holds at signatures, not inside expressions — which is why the
name keeps its unit too (`naming.md`).

### A returned `Iterator` is consumed once; anything read twice returns a collection

**Why:** a generator annotated `Iterable` invites a second loop, and the second loop sees nothing —
no error, just an empty result. `Iterator[T]` says "once"; a caller that needs the values twice
gets a `list`.

**Example:**
```python
# WRONG — typed as re-iterable, but the second pass over the result is silently empty
def detections_above(
    detections: Iterable[Detection], *, min_signal_to_noise: float
) -> Iterable[Detection]:
    return (
        detection for detection in detections if detection.signal_to_noise > min_signal_to_noise
    )


# CORRECT — the type says it can be read once
def detections_above(
    detections: Iterable[Detection], *, min_signal_to_noise: float
) -> Iterator[Detection]:
    return (
        detection for detection in detections if detection.signal_to_noise > min_signal_to_noise
    )
```

## Checks and Markers

### `isinstance` against a runtime-checkable `Protocol` checks names, not signatures

**Why:** a `park()` missing the protocol's parameter passes the check, and the call fails later.
Where the check must mean it, narrow on the ABC the implementation inherits.

**Example:**
```python
# WRONG — any object with a park attribute passes, whatever its signature
@runtime_checkable
class Parkable(Protocol):
    def park(self, *, timeout_seconds: float) -> None: ...


def park_instruments(instruments: Iterable[object], *, timeout_seconds: float) -> None:
    for instrument in instruments:
        if isinstance(instrument, Parkable):
            instrument.park(timeout_seconds=timeout_seconds)


# CORRECT — only an implementation of the contract passes
def park_instruments(instruments: Iterable[object], *, timeout_seconds: float) -> None:
    for instrument in instruments:
        if isinstance(instrument, TelescopeMount):
            instrument.park(timeout_seconds=timeout_seconds)
```

### A public library API pins its inferred types with `assert_type` in its tests

**Why:** a value test passes whatever type the function now returns, so a refactor that widens
`float` to `float | None` ships to every user unnoticed. `reveal_type()` is for debugging and is
never committed.

## Absence and Failure

### When `None` is a legal value, absence is a one-member `Enum` sentinel

**Why:** in a PATCH-style update `None` cannot tell "not provided" from "explicitly cleared". JSON
Merge Patch (RFC 7396) made that choice for a whole format: `null` there means "remove the key", so
a merge patch can never set a value to null. mypy narrows `is NOT_GIVEN` on an enum member in every
branch, a plain-class instance only in the `if`. The sentinel's type is public, because a caller
that forwards the parameter has to name it.

**Example:**
```python
# WRONG — None means both "leave the common name" and "clear it"
def update_target(
    target_id: TargetId, *, common_name: str | None = None, targets: TargetCatalogue
) -> None:
    if common_name is not None:
        targets.set_common_name(target_id, common_name)


# CORRECT — absence has its own value, and None keeps its one meaning
class NotGiven(Enum):
    NOT_GIVEN = auto()


NOT_GIVEN: Final = NotGiven.NOT_GIVEN


def update_target(
    target_id: TargetId,
    *,
    common_name: str | None | NotGiven = NOT_GIVEN,
    targets: TargetCatalogue,
) -> None:
    if common_name is NOT_GIVEN:
        return
    if common_name is None:
        targets.clear_common_name(target_id)
    else:
        targets.set_common_name(target_id, common_name)
```

### Failure is an exception; a batch whose normal output mixes outcomes returns tagged variants

**Why:** a `Result` or `Either` wrapper duplicates exceptions, defeats `raise ... from` and makes
every caller unwrap by hand. The one shape that needs a value per failure is a batch whose normal
output is a mix of successes and failures — and that is an explicit union of frozen dataclasses,
not a general-purpose monad.

**Example:**
```python
# WRONG — a generic wrapper every caller has to unwrap
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Outcome[T]:
    value: T | None = None
    error: str | None = None


def import_observing_log(lines: Iterable[LogLine]) -> list[Outcome[LogEntry]]:
    outcomes: list[Outcome[LogEntry]] = []
    for line in lines:
        try:
            outcomes.append(Outcome(value=parse_log_entry(line)))
        except InvalidLogEntryError as error:
            outcomes.append(Outcome(error=str(error)))
    return outcomes


# CORRECT — the batch says what each line became
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class ParsedLogLine:
    line_number: int
    entry: LogEntry


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class RejectedLogLine:
    line_number: int
    reason: str


type LogLineOutcome = ParsedLogLine | RejectedLogLine


def import_observing_log(lines: Iterable[LogLine]) -> list[LogLineOutcome]:
    outcomes: list[LogLineOutcome] = []
    for line in lines:
        try:
            outcomes.append(ParsedLogLine(line_number=line.number, entry=parse_log_entry(line)))
        except InvalidLogEntryError as error:
            outcomes.append(RejectedLogLine(line_number=line.number, reason=str(error)))
    return outcomes
```

## Narrow Standard Protocols

### Bytes-like input is `Buffer`; an integer-like index is `SupportsIndex`

**Why:** `bytes | bytearray | memoryview` misses `array.array`, `mmap` and every other buffer;
`Buffer` (PEP 688, `collections.abc` from 3.12) names the protocol itself. `SupportsIndex` and
`SupportsFloat` say that only the conversion is needed.

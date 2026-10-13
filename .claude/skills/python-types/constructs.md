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
def execute_ddl(statement: str, *, connection: Connection) -> None:
    connection.execute(statement)


# CORRECT — pyright rejects execute_ddl(f"DROP TABLE {name}", ...); mypy lets it through
def execute_ddl(statement: LiteralString, *, connection: Connection) -> None:
    connection.execute(statement)
```

## Shapes

### Free-form JSON is a recursive alias, not `Any`

**Why:** `Any` stops checking at the first subscript; a recursive alias keeps every level a union
the code has to narrow. It is only for a shape that is genuinely unknown — a known one is a model
or a `TypedDict`. A `type` statement is evaluated lazily, so the recursion needs no quotes.

**Example:**
```python
# WRONG — document["anything"]["at"]["all"] type-checks
def count_leaves(document: Any) -> int:
    if isinstance(document, dict):
        return sum(count_leaves(value) for value in document.values())
    if isinstance(document, list):
        return sum(count_leaves(item) for item in document)
    return 1


# CORRECT — each level is a union the function narrows
type Json = str | int | float | bool | None | list[Json] | dict[str, Json]


def count_leaves(document: Json) -> int:
    if isinstance(document, dict):
        return sum(count_leaves(value) for value in document.values())
    if isinstance(document, list):
        return sum(count_leaves(item) for item in document)
    return 1
```

### A callable with two or more parameters, or any keyword, is a calling protocol

**Why:** `Callable[[str, int, datetime], None]` names nothing — the reader cannot tell which
argument is which, and a keyword argument cannot be expressed at all. One parameter and an obvious
return stay a `Callable`.

**Example:**
```python
# WRONG — which argument is which, and none can be passed by keyword
def subscribe(handler: Callable[[str, int, datetime], None], *, bus: EventBus) -> None:
    bus.add_handler(handler)


# CORRECT — a named calling protocol
class DeliveryHandler(Protocol):
    def __call__(self, event_name: str, attempt: int, *, received_at: datetime) -> None: ...


def subscribe(handler: DeliveryHandler, *, bus: EventBus) -> None:
    bus.add_handler(handler)
```

### A quantity crossing a signature carries its unit in the type and in the name

**Why:** with plain floats a distance passes where a duration is expected. A Mars orbiter was lost
to exactly this: one program reported thruster impulse in pound-force seconds, the one consuming it
read newton-seconds, and both sides were plain floats. Arithmetic on a `NewType` returns the base
type, so the check holds at signatures, not inside expressions — and the reader of a call site still
has only the name, so the unit stays in it.

### A returned `Iterator` is consumed once; anything read twice returns a collection

**Why:** a generator annotated `Iterable` invites a second loop, and the second loop sees nothing —
no error, just an empty result. `Iterator[T]` says "once"; a caller that needs the values twice
gets a `list`.

**Example:**
```python
# WRONG — typed as re-iterable, but the second pass over the result is silently empty
def readings_above(readings: Iterable[Reading], *, threshold: float) -> Iterable[Reading]:
    return (reading for reading in readings if reading.value > threshold)


# CORRECT — the type says it can be read once
def readings_above(readings: Iterable[Reading], *, threshold: float) -> Iterator[Reading]:
    return (reading for reading in readings if reading.value > threshold)
```

## Checks and Markers

### `isinstance` against a runtime-checkable `Protocol` checks names, not signatures

**Why:** a `close()` missing the protocol's parameter passes the check, and the call fails later.
Where the check must mean it, narrow on the ABC the implementation inherits (`python-contracts`).

**Example:**
```python
# WRONG — any object with a flush attribute passes, whatever its signature
@runtime_checkable
class Flushable(Protocol):
    def flush(self, *, timeout_seconds: float) -> None: ...


def flush_all(sinks: Iterable[object], *, timeout_seconds: float) -> None:
    for sink in sinks:
        if isinstance(sink, Flushable):
            sink.flush(timeout_seconds=timeout_seconds)


# CORRECT — only an implementation of the contract passes
def flush_all(sinks: Iterable[object], *, timeout_seconds: float) -> None:
    for sink in sinks:
        if isinstance(sink, MetricSink):
            sink.flush(timeout_seconds=timeout_seconds)
```

### A public library API pins its inferred types with `assert_type` in its tests

**Why:** a value test passes whatever type the function now returns, so a refactor that widens
`Decimal` to `Decimal | None` ships to every user unnoticed. `reveal_type()` is for debugging and is
never committed.

## Absence and Failure

### When `None` is a legal value, absence is a one-member `Enum` sentinel

**Why:** in a PATCH-style update `None` cannot tell "not provided" from "explicitly cleared". JSON
Merge Patch (RFC 7396) made that choice for a whole format: `null` there means "remove the key", so
a merge patch can never set a value to null. mypy narrows `is UNSET` on an enum member in every
branch, a plain-class instance only in the `if`. The sentinel's type is public, because a caller
that forwards the parameter has to name it.

**Example:**
```python
# WRONG — None means both "leave the nickname" and "clear it"
def update_profile(user_id: UserId, *, nickname: str | None = None, profiles: Profiles) -> None:
    if nickname is not None:
        profiles.set_nickname(user_id, nickname)


# CORRECT — absence has its own value, and None keeps its one meaning
class Unset(Enum):
    UNSET = auto()


UNSET: Final = Unset.UNSET


def update_profile(
    user_id: UserId, *, nickname: str | None | Unset = UNSET, profiles: Profiles
) -> None:
    if nickname is UNSET:
        return
    if nickname is None:
        profiles.clear_nickname(user_id)
    else:
        profiles.set_nickname(user_id, nickname)
```

### Failure is an exception; a batch whose normal output mixes outcomes returns tagged variants

**Why:** a `Result` or `Either` wrapper duplicates exceptions, defeats `raise ... from` and makes
every caller unwrap by hand. The one shape that needs a value per failure is a batch whose normal
output is a mix of successes and failures — and that is an explicit union of frozen dataclasses,
not a general-purpose monad.

**Example:**
```python
# WRONG — a generic wrapper every caller has to unwrap
@dataclass(frozen=True, slots=True, kw_only=True)
class Result[T]:
    value: T | None = None
    error: str | None = None


def import_rows(rows: Iterable[CsvRow]) -> list[Result[Contact]]:
    results: list[Result[Contact]] = []
    for row in rows:
        try:
            results.append(Result(value=parse_contact(row)))
        except InvalidContactError as error:
            results.append(Result(error=str(error)))
    return results


# CORRECT — the batch says what each row became
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Imported:
    line_number: int
    contact: Contact


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Rejected:
    line_number: int
    reason: str


type ImportOutcome = Imported | Rejected


def import_rows(rows: Iterable[CsvRow]) -> list[ImportOutcome]:
    outcomes: list[ImportOutcome] = []
    for row in rows:
        try:
            outcomes.append(Imported(line_number=row.line_number, contact=parse_contact(row)))
        except InvalidContactError as error:
            outcomes.append(Rejected(line_number=row.line_number, reason=str(error)))
    return outcomes
```

## Narrow Standard Protocols

### Bytes-like input is `Buffer`; an integer-like index is `SupportsIndex`

**Why:** `bytes | bytearray | memoryview` misses `array.array`, `mmap` and every other buffer;
`Buffer` (PEP 688, `collections.abc` from 3.12) names the protocol itself. `SupportsIndex` and
`SupportsFloat` say that only the conversion is needed.

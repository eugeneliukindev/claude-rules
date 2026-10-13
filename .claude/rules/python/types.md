---
paths:
  - "**/*.py"
---

# Python — Types and Data

The decisions behind these are in the `python-types` skill; these apply everywhere.

## Annotations

### Code is `mypy --strict` clean, in the modern spelling

**Why:** strict mode is what makes every annotation mandatory and checked; `T | None` and PEP 695
generics on a 3.12+ floor say in one place what `Optional` and `TypeVar` + `Generic` spread over
three.

### Parameters take `collections.abc` types; returns are concrete

**Why:** `Mapping[str, int]` in accepts every mapping and handles variance without `covariant=`;
`dict[str, int]` out tells the caller what it can do with the result.

### "Unknown" is spelled `object`; `Any` means "stop checking"

**Why:** `object` forces narrowing before use; `Any` lets every typo through, and a function
*returning* it spreads that silence to every caller.
**Except:** the one position where a library fixes the signature and there is nothing to narrow to.

**Example:**
```python
# WRONG — value.anything type-checks, typos included
def describe(value: Any) -> str:
    return value.lattitude


# CORRECT — the checker demands isinstance before use
def describe(value: object) -> str:
    if isinstance(value, Coordinate):
        return f"{value.latitude}, {value.longitude}"
    return type(value).__name__
```

## Data Classes

### `@dataclass(frozen=True, slots=True, kw_only=True)` by default

**Why:** `frozen` is about mutability, `slots` about the attribute set, `kw_only` about the call
site — the one usually forgotten: positional, two ids of one type are swapped, it type-checks, and
the money moves backwards. A mutable connection URL let callers leak changes into each other's
connections; making it immutable broke every one of them.
**Except:** positional construction where the order is the concept — `Point(x, y)`; mutability for
a genuine aggregate root, said in its name — `Cart`, `Session` — with copies through `replace()`.

**Example:**
```python
# WRONG — positional and mutable: the call swaps the ids, and nothing objects
@dataclass
class Transfer:
    sender_id: AccountId
    recipient_id: AccountId
    amount: Money


transfer = Transfer(recipient_id, sender_id, amount)


# CORRECT — every call site names its fields, and the value cannot change after
@dataclass(frozen=True, slots=True, kw_only=True)
class Transfer:
    sender_id: AccountId
    recipient_id: AccountId
    amount: Money


transfer = Transfer(sender_id=sender_id, recipient_id=recipient_id, amount=amount)
```

### `@override` on every override, `@final` where subclassing is not meant, `Final` on constants

**Why:** `@override` turns a renamed parent method into an error instead of an orphan; `@final` on
an implementation of a contract or an exported class keeps subclasses out (optional elsewhere);
`-> Never` marks a function that always raises; `Final` makes the checker reject reassignment and
infer the literal type.

**Example:**
```python
# WRONG — an orphan waiting to happen, a reassignable limit, a raise the checker cannot follow
MAX_LINES = 500


class CsvExporter(Exporter):
    def __init__(self, *, max_lines: int = MAX_LINES) -> None:
        self._max_lines = max_lines

    def export(self, invoices: Sequence[Invoice]) -> bytes:
        return render_csv(invoices[: self._max_lines])


def reject(invoice: Invoice) -> None:
    raise InvoiceRejectedError(invoice.number)


# CORRECT
MAX_LINES: Final = 500


@final
class CsvExporter(Exporter):
    def __init__(self, *, max_lines: int = MAX_LINES) -> None:
        self._max_lines = max_lines

    @override
    def export(self, invoices: Sequence[Invoice]) -> bytes:
        return render_csv(invoices[: self._max_lines])


def reject(invoice: Invoice) -> Never:
    raise InvoiceRejectedError(invoice.number)
```

## Mutability

### Fixed sequences are `tuple`, fixed sets `frozenset`, a dict exposed read-only `MappingProxyType`

**Why:** an immutable container cannot be changed by the caller who received it, and says so in its
type.

### Arguments are never mutated, and internal state is never handed out

**Why:** a response that appended to the header list it was given grew one shared list on every
request; field descriptors handed out by a getter were mutated by callers, and the library had to
keep supporting it.
**Except:** a function whose job is the mutation is named for it and takes a `MutableSequence`.

**Example:**
```python
# WRONG — appends to the caller's list, and hands out its own
@final
class Playlist:
    def __init__(self, *, tracks: list[Track]) -> None:
        self._tracks = tracks

    def with_track(self, track: Track) -> list[Track]:
        self._tracks.append(track)
        return self._tracks


# CORRECT — copies in, a tuple out; the caller's list and the playlist's tracks stay apart
@final
class Playlist:
    def __init__(self, *, tracks: Iterable[Track]) -> None:
        self._tracks = tuple(tracks)

    def with_track(self, track: Track) -> tuple[Track, ...]:
        return (*self._tracks, track)
```

### A string that is user-facing or used twice is a constant or an `Enum` member

**Why:** the linter catches a magic *number*; a repeated literal string it does not, and the two
spellings drift.

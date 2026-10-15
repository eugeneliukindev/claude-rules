---
paths:
  - "**/*.py"
---

# Python — Types and Data

The decisions behind these are in the `python-types` skill; these apply everywhere.

### Parameters take `collections.abc` types; returns are concrete

**Why:** `Mapping[str, int]` in accepts every mapping and handles variance; `dict[str, int]` out
tells the caller what it can do with the result.

### `@dataclass(frozen=True, slots=True, kw_only=True)` by default

**Why:** `frozen` is about mutability, `slots` about the attribute set, `kw_only` about the call
site — the one usually forgotten: positional, two ids of one type are swapped, it type-checks, and
the money moves backwards.
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
an implementation of a contract or an exported class keeps subclasses out; `-> Never` marks a
function that always raises; `Final` makes the checker reject reassignment and infer the literal
type.

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

### Arguments are never mutated, and internal state is never handed out

**Why:** a response that appended to the header list it was given grew one shared list on every
request; a result is returned, never written into a parameter. What is fixed is a `tuple`, a
`frozenset` or a `MappingProxyType`, copied in and handed out as such.
**Except:** a function whose job is the mutation is named for it and takes a `MutableSequence`.

### A string that is user-facing or used twice is a constant or an `Enum` member

**Why:** a literal string repeated at two call sites drifts into two spellings.

---
paths:
  - "**/*.py"
---

# Python — Control Flow

## Conditions

### A condition becomes a named predicate when its operands together name a concept

**Why:** the reader would otherwise reconstruct the concept from the operands every time; the
linter counts operands and cannot name them, so the count is not the test.
**Except:** a condition that already reads as what it means stays inline, whatever its length —
`if user is None or user.is_blocked`.

**Example:**
```python
# WRONG — three operands the reader must assemble into "renewable"
def renew_loan(loan: Loan, *, today: date) -> Loan:
    if not loan.is_reserved and loan.renewals < _MAX_RENEWALS and loan.due_on >= today:
        return loan.extended_by(_LOAN_PERIOD)
    raise RenewalRefusedError(loan.loan_id)


# CORRECT — the name says what the operands meant
def renew_loan(loan: Loan, *, today: date) -> Loan:
    if _is_renewable(loan, today=today):
        return loan.extended_by(_LOAN_PERIOD)
    raise RenewalRefusedError(loan.loan_id)


def _is_renewable(loan: Loan, *, today: date) -> bool:
    return not loan.is_reserved and loan.renewals < _MAX_RENEWALS and loan.due_on >= today
```

## Pattern Matching

### `match` destructures a closed union or nested data; it is not a `switch`

**Why:** comparing one scalar against constants, or choosing between two branches, reads better as
`if`; `match` earns its syntax when the patterns take values apart.

**Example:**
```python
# WRONG — a switch on one value, with no structure taken apart
def fee_percent(plan: str) -> int:
    match plan:
        case "basic":
            return 3
        case "pro":
            return 2
        case _:
            raise UnknownPlanError(plan)


# CORRECT — the patterns destructure the variants of a closed union
def describe(event: ShipmentEvent) -> str:
    match event:
        case ParcelDispatched(tracking_number=number, carrier=carrier):
            return f"{number}: handed to {carrier}"
        case ParcelReturned(tracking_number=number, reason=reason):
            return f"{number}: returned ({reason})"
        case _:
            assert_never(event)
```

### A bare name in a pattern binds, it does not compare — constants are dotted

**Why:** whatever its case, `case Parcel(status=DELIVERED)` matches every parcel and binds the name
`DELIVERED`; it is the one thing about `match` worth memorising.

**Example:**
```python
# WRONG — matches every parcel, and DELIVERED is now a fresh variable
def is_delivered(parcel: Parcel) -> bool:
    match parcel:
        case Parcel(status=DELIVERED):
            return True
        case _:
            return False


# CORRECT — a dotted name compares
def is_delivered(parcel: Parcel) -> bool:
    match parcel:
        case Parcel(status=ParcelStatus.DELIVERED):
            return True
        case _:
            return False
```

### Every `match` over a union or an `Enum` ends with exhaustiveness

**Why:** `case _: assert_never(value)` makes a new variant a type error at every `match` that does
not handle it; a silent fall-through returns `None` for it instead.

**Example:**
```python
# WRONG — a new status falls through and the function returns None
def label(status: InvoiceStatus) -> str:
    match status:
        case InvoiceStatus.OPEN:
            return "Open"
        case InvoiceStatus.PAID:
            return "Paid"


# CORRECT — a status added to the Enum is an error here until it is handled
def label(status: InvoiceStatus) -> str:
    match status:
        case InvoiceStatus.OPEN:
            return "Open"
        case InvoiceStatus.PAID:
            return "Paid"
        case _:
            assert_never(status)
```

### A factory dispatches through a mapping, not through `match`

**Why:** kind in, builder out — adding a kind is one entry, and the set of kinds is readable in one
place instead of spread over branches.

**Example:**
```python
# WRONG — every new format edits the function
def build_exporter(export_format: ExportFormat) -> Exporter:
    match export_format:
        case ExportFormat.CSV:
            return CsvExporter()
        case ExportFormat.PDF:
            return PdfExporter()
        case _:
            assert_never(export_format)


# CORRECT — one entry per format
_EXPORTER_BY_FORMAT: Final[Mapping[ExportFormat, Callable[[], Exporter]]] = MappingProxyType({
    ExportFormat.CSV: CsvExporter,
    ExportFormat.PDF: PdfExporter,
})


def build_exporter(export_format: ExportFormat) -> Exporter:
    return _EXPORTER_BY_FORMAT[export_format]()
```

## Iteration

### A comprehension holds one transformation; anything more is a loop

**Why:** the judgement is how much the reader can hold, not how much fits on a line; a nested
comprehension with a condition is three steps written as one.

### A lazy sequence longer than one expression is a generator function

**Why:** anything reading a stream, a file, a cursor or a paginated API yields as it reads, and a
named generator says what it yields; a list built first holds everything in memory at once.

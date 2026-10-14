---
paths:
  - "**/*.py"
---

# Python — Classes

Functions are the default; a class is an upgrade that must be triggered.

## When a Class Earns Its Place

### A class is written only when one of seven triggers holds

**Why:** a module is already a namespace with "methods"; a class without a trigger — `__init__`
plus one method over values it was handed, only `@staticmethod`s, a box for constants — adds `self`
and a constructor to code that needed neither. A partial, a closure or an options dataclass gives
the one thing needed without a lifecycle.

1. **State survives between calls** — a token bucket, a pool, an accumulator, an open session.
2. **Invariants tie values together** — `Money`, `DateRange`: a frozen dataclass with methods.
3. **The behaviour must be swappable** — two implementations behind one contract, or a test fake.
4. **Several operations share the same dependencies** — three or more functions taking the same two
   or more collaborators.
5. **There is a lifecycle** — acquire and release, `__enter__`/`__exit__`, `close()`.
6. **A framework demands it** — `Enum`, `Exception`, a dataclass.
7. **The composition root builds it with collaborators** — a service or an adapter that takes its
   dependencies and settings in its constructor.

## One Actor per Module and Class

### A module or a class answers to one actor — whoever asks for its changes

**Why:** code answering to two actors ships the fix one of them asks for to the other. This is SRP,
not "does one thing", and the test is *who*, not *which layer*.
**Except:** knowledge both actors share — what counts as regular hours — lives once, on the data; if
they come to mean different things, those are two rules with two names.

**Example:**
```python
# WRONG — one module, two actors: a pay fix finance asks for ships with HR's hours report
def _regular_hours(timesheet: Timesheet, *, week_hours: Decimal = REGULAR_WEEK_HOURS) -> Decimal:
    return min(timesheet.hours_worked, week_hours)


def calculate_pay(timesheet: Timesheet) -> Decimal:  # finance
    return _regular_hours(timesheet) * timesheet.hourly_rate


def report_hours(timesheet: Timesheet, *, working_days: int) -> HoursReport:  # HR
    regular = _regular_hours(timesheet)
    return HoursReport(regular=regular, total=timesheet.hours_worked, working_days=working_days)


# CORRECT — timesheet.py: the rule both actors share, on the data
@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Timesheet:
    hours_worked: Decimal
    hourly_rate: Decimal

    def regular_hours(self, *, week_hours: Decimal = REGULAR_WEEK_HOURS) -> Decimal:
        return min(self.hours_worked, week_hours)


# CORRECT — payroll.py, finance's module
def calculate_pay(timesheet: Timesheet) -> Decimal:
    return timesheet.regular_hours() * timesheet.hourly_rate


# CORRECT — hours_report.py, HR's module
def report_hours(timesheet: Timesheet, *, working_days: int) -> HoursReport:
    regular = timesheet.regular_hours()
    return HoursReport(regular=regular, total=timesheet.hours_worked, working_days=working_days)
```

## Inversion and Composition

### Collaborators arrive through the constructor, never built inside

**Why:** one built inside cannot be replaced in a test, and the signature hides what it needs.

**Example:**
```python
# WRONG — the repository is built inside: no test can hand in a fake
@final
class DocumentService:
    def __init__(self, pool: DatabasePool) -> None:
        self._documents = PostgresDocumentRepository(pool)

    def archive(self, document_id: DocumentId) -> None:
        self._documents.mark_archived(document_id)


# CORRECT — it arrives from the composition root
@final
class DocumentService:
    def __init__(self, *, documents: DocumentRepository) -> None:
        self._documents = documents

    def archive(self, document_id: DocumentId) -> None:
        self._documents.mark_archived(document_id)
```

### A class inherits only what it is; reuse is composition

**Why:** a class inherits a contract, or a base whose fields and methods it *is*; behaviour wanted
only for its methods — an HTTP call, a retry, a formatter — arrives as a collaborator, because a
base class collecting helpers ties every subclass to all of them and no test can swap one out.
**Except:** a mixin adds behaviour over the class's own contract, holds no state and declares
`__slots__ = ()`.

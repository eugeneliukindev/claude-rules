---
paths:
  - "**/*.py"
---

# Python — Classes

Functions are the default; a class is an upgrade that must be triggered. A module is already a
namespace with "methods", so a class has to offer something a module does not.

**Write a class when at least one is true:**

1. **State survives between calls** — a token bucket, a pool, an accumulator, an open session.
2. **Invariants tie values together** — `Money`, `DateRange`. That is a frozen dataclass with
   methods, not a "service" class.
3. **The behaviour must be swappable** — two or more implementations behind one contract, or a test
   needs a fake.
4. **Several operations share the same dependencies** — three or more functions in a module taking
   the same two or more collaborators. Those repeated parameters *are* a constructor; repeated
   *values* that form one concept are a parameter object instead (`functions.md`).
5. **There is a lifecycle** — acquire/release, `__enter__`/`__exit__`, `close()`.
6. **A framework demands it** — `Enum`, `Exception`, a dataclass.

**Reliable signs of a class that should not exist**: `__init__` plus one method
(`Calculator(x).calculate()` is `calculate(x)`); only `@staticmethod`s; a box for constants; a
stateless "service" with no dependencies; and **methods that group by who asks for their changes**
rather than by visibility — more than one actor: split the class, do not reorder it.

Before reaching for a class, consider `functools.partial` or a closure, a frozen dataclass of
options, or **splitting the module** — a long module of independent functions is idiomatic Python.

**The rest of SOLID, where it breaks**: depend on abstractions — inject, never instantiate a
collaborator inside a class. A subclass is usable wherever its parent is: it accepts at least what
the parent accepts and returns nothing wider — mypy's `[override]` checks that much — and adds no
precondition, drops no promise and raises nothing new, which nothing checks. A contract holds only
what its consumer calls, and a class inherits only what it *is* — reuse is composition
(`python-contracts`).

## One Actor per Module and Class

This is SRP, and it is not "does one thing" — that rule is for functions. A responsibility is an
**actor**: whoever asks for the change — finance for pay rules, HR for the hours report, the DBA
for the schema. Code answering to two actors does not share a module or a class even when it shares
the data, or a fix one of them asks for ships to the other. **The test is who, not which layer**:
name who would ask to change each function, and two answers are two modules; splitting I/O, domain
and presentation follows from it and does not replace it. The data stays one frozen dataclass; each
actor gets a module of functions over it, or a class of its own when it has dependencies.

```python
# WRONG — one module, two actors: finance changes _regular_hours for pay, HR's report moves too
def _regular_hours(timesheet: Timesheet) -> Decimal: ...
def calculate_pay(timesheet: Timesheet) -> Money: ...        # finance
def report_hours(timesheet: Timesheet) -> HoursReport: ...   # HR

# CORRECT — payroll.py and hours_report.py, each with its own private _regular_hours

# WRONG — one class answers to finance and HR, and both edit _regular_hours for their own reasons
@final
class EmployeeService:
    def __init__(self, timesheets: TimesheetRepository, tax_tables: TaxTables,
                 calendar: WorkCalendar) -> None: ...
    def gross_pay(self, employee_id: EmployeeId, month: Month) -> Money: ...     # finance
    def net_pay(self, employee_id: EmployeeId, month: Month) -> Money: ...       # finance
    def payslip(self, employee_id: EmployeeId, month: Month) -> Payslip: ...     # finance
    def hours_report(self, month: Month) -> HoursReport: ...                     # HR
    def overtime_report(self, month: Month) -> OvertimeReport: ...               # HR
    def absence_report(self, month: Month) -> AbsenceReport: ...                 # HR
    def _regular_hours(self, timesheet: Timesheet) -> Decimal: ...

# CORRECT — one class per actor, each with its own dependencies and its own _regular_hours
@final
class Payroll:
    def __init__(self, timesheets: TimesheetRepository, tax_tables: TaxTables) -> None: ...
    def gross_pay(self, employee_id: EmployeeId, month: Month) -> Money: ...
    def net_pay(self, employee_id: EmployeeId, month: Month) -> Money: ...
    def payslip(self, employee_id: EmployeeId, month: Month) -> Payslip: ...

@final
class HoursReporting:
    def __init__(self, timesheets: TimesheetRepository, calendar: WorkCalendar) -> None: ...
    def hours_report(self, month: Month) -> HoursReport: ...
    def overtime_report(self, month: Month) -> OvertimeReport: ...
    def absence_report(self, month: Month) -> AbsenceReport: ...
```

A layer split passes both wrong versions; the two `_regular_hours` are duplication DRY keeps.

**A contract is a base class with `@abstractmethod` that implementations inherit** — a missing
method fails where the class is defined, not at a distant call site. `Protocol` is for code you
cannot make inherit; the rest is in `python-contracts`.

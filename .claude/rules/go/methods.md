---
paths:
  - "**/*.go"
---

# Go — Methods

Functions are the default; a type with methods is an upgrade that must be triggered. A package is
already a namespace, so a struct has to offer something a package of functions does not.

**Give a type methods when at least one is true:**

1. **State survives between calls** — a rate limiter, a pool, an accumulator, an open connection.
2. **Invariants tie values together** — `Money`, `DateRange`: a value type with unexported fields,
   a constructor that validates, and value receivers.
3. **The behaviour must be swappable** — a consumer depends on an interface, and two or more
   implementations or a test fake satisfy it.
4. **Several operations share the same dependencies** — three or more functions taking the same two
   or more parameters. Those repeated parameters *are* the struct's fields; this is what a Go
   service is.
5. **There is a lifecycle** — open, use, `Close`.
6. **An interface someone else defined demands it** — `error`, `fmt.Stringer`, `http.Handler`,
   `sort.Interface`, `encoding.TextMarshaler`.

**Reliable signs of a type that should not exist**: a constructor plus one method
(`NewCalculator(x).Calculate()` is `Calculate(x)`); an empty struct whose methods use no receiver;
a struct holding only constants; a stateless "service" with no dependencies. And one more, visible
only while reading: **a type whose methods want to be grouped by who asks for their changes**
answers to more than one actor — split the type, do not reorder it.

Before reaching for a type, consider a closure, a `func` parameter, or **splitting the package** —
a package of independent functions is idiomatic Go and does not improve by growing a receiver.

## One Actor per Package and Type

This is SRP, and it is not "does one thing" — that rule is for functions. A responsibility is an
**actor**: whoever asks for the change — finance for pay rules, HR for the hours report, the DBA
for the schema. Code answering to two actors does not share a package or a type even when it
shares the data, or a fix one of them asks for ships to the other. **The test is who, not which
layer**: name who would ask to change each function, and two answers are two packages; splitting
transport, domain and storage follows from it and does not replace it. The data stays one struct;
each actor gets a package of functions over it, or a type of its own when it has dependencies.

```go
// WRONG — one type answers to finance and HR, and both edit regularHours for their own reasons
type EmployeeService struct {
	timesheets TimesheetRepository
	taxTables  TaxTables
	calendar   WorkCalendar
}

func (s *EmployeeService) Payslip(ctx context.Context, id EmployeeID, m Month) (Payslip, error) // finance
func (s *EmployeeService) HoursReport(ctx context.Context, m Month) (HoursReport, error)        // HR
func (s *EmployeeService) regularHours(t Timesheet) time.Duration

// CORRECT — package payroll and package hoursreport, each with its own regularHours
type Payroll struct { // in package payroll
	timesheets TimesheetRepository
	taxTables  TaxTables
}

func (p *Payroll) Payslip(ctx context.Context, id EmployeeID, m Month) (Payslip, error)

type Reporter struct { // in package hoursreport
	timesheets TimesheetRepository
	calendar   WorkCalendar
}

func (r *Reporter) Hours(ctx context.Context, m Month) (HoursReport, error)
```

A layer split passes the wrong version — everything in it is domain logic. The two `regularHours`
are the duplication DRY in `core.md` tells you to keep.

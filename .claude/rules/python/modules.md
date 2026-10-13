---
paths:
  - "**/*.py"
---

# Python — Modules

## Module Layout

### Every module has the same order

**Why:** a reader always knows where to look. Python's own definition order wins where it applies —
a validator comes before the alias built from it; anything else that will not fit is a seam, so the
module is split rather than the list renumbered. Size is a smell, not a limit.

1. Module docstring — one line, always.
2. `from __future__ import annotations`, when the target version needs it.
3. Imports, then `__all__` — the whole of `__init__.py`; in a package others import, every public
   module too.
4. Module-level constants, then type aliases, `NewType`s and type parameters.
5. Module logger, then exception classes.
6. Contracts, then concrete classes, then the models private to this module.
7. Public functions, high-level first; private functions after them, in call order.
8. The `__main__` guard — a single call to `main()`, nothing else.

**Example:**
```python
# WRONG — a constant below the code that reads it, the logger between two functions
def remind(appointment: Appointment, *, texter: TextMessenger) -> None:
    logger.info("reminder sent", extra={"appointment_id": appointment.appointment_id})
    texter.send(appointment.patient_phone, _REMINDER_TEXT)


logger = logging.getLogger(__name__)
_REMINDER_TEXT: Final = "Your appointment is tomorrow"


# CORRECT — docstring, imports, constants, logger, public function, in that order
"""Send reminders for tomorrow's appointments."""

import logging
from typing import Final

from clinic.appointments import Appointment
from messaging import TextMessenger

_REMINDER_TEXT: Final = "Your appointment is tomorrow"

logger = logging.getLogger(__name__)


def remind(appointment: Appointment, *, texter: TextMessenger) -> None:
    logger.info("reminder sent", extra={"appointment_id": appointment.appointment_id})
    texter.send(appointment.patient_phone, _REMINDER_TEXT)
```

### Nothing runs at import beyond constants, the logger and its kin

**Why:** a network call, a file read or a settings object at import makes every import slow and
order-dependent, and a test cannot import the module without the environment it reads. The tracer,
the meter and a context variable record nothing until configured (`python-observability`).

**Example:**
```python
# WRONG — importing the module reads the environment
_settings = Settings()


def main() -> None:
    run(timeout_seconds=_settings.timeout_seconds)


# CORRECT — main() is a function, and it builds the settings
def main() -> None:
    settings = Settings()
    run(timeout_seconds=settings.timeout_seconds)
```

## Encapsulation

### A name used only inside its module or class takes an underscore

**Why:** functions, methods, attributes, constants, type aliases and classes alike — without the
prefix a name reads as surface, and the first outside import makes it surface for good; a library
still serves an internal builder its facade once exposed, with a warning, years later. Constants and
aliases are the ones missed: read quietly from a second module, they get two owners.
**Except:** a script nobody imports (`python-scripts`), and a name a framework reaches through a
decorator — a route, a fixture.

**Example:**
```python
# WRONG — the width, the formatter and the store all read as this module's surface
NUMBER_WIDTH: Final = 6


def format_number(sequence: int) -> str:
    return f"TKT-{sequence:0{NUMBER_WIDTH}d}"


@final
class TicketNumbering:
    def __init__(self, *, sequences: SequenceStore) -> None:
        self.sequences = sequences

    def next_number(self) -> str:
        return format_number(self.sequences.increment("support_ticket"))


# CORRECT — only the class and its one method are used outside, and only they lack the prefix
_NUMBER_WIDTH: Final = 6


def _format_number(sequence: int) -> str:
    return f"TKT-{sequence:0{_NUMBER_WIDTH}d}"


@final
class TicketNumbering:
    def __init__(self, *, sequences: SequenceStore) -> None:
        self._sequences = sequences

    def next_number(self) -> str:
        return _format_number(self._sequences.increment("support_ticket"))
```

### The check runs over sources and tests together

**Why:** a name a test imports is used outside and stays unprefixed; checked over the sources alone,
every such name is reported, gets a prefix, and the tests then import `_private` names. The check is
run after the move that made a name internal (`python-packaging`).

## Facade, Public Module, Internal Module

### A package's `__init__.py` re-exports only the main, general-purpose names its consumers use

**Why:** the facade — imports and `__all__` only, no heavy or optional library — carries the
vocabulary nearly every importer needs; a facade that re-exported everything made a job needing one
enum load a browser driver and an ORM. What only some need, or what pulls a heavy library, stays in
a public module `package/topic.py`; what only siblings use is an internal `_topic.py`, never reached
into. The decision table is in `python-packaging`.
**Except:** an application package nobody outside imports needs no facade; the underscore rule above
holds there all the same.

**Example:**
```python
# WRONG — billing/__init__.py re-exports everything: importing InvoiceStatus loads the PDF engine
from billing.invoices import Invoice, InvoiceLine, InvoiceStatus
from billing.numbering import InvoiceNumbering
from billing.pdf import PdfInvoiceRenderer
from billing.service import InvoiceService

__all__ = [
    "Invoice",
    "InvoiceLine",
    "InvoiceNumbering",
    "InvoiceService",
    "InvoiceStatus",
    "PdfInvoiceRenderer",
]


# CORRECT — the vocabulary every consumer needs; the renderer is imported from billing.pdf
from billing.invoices import Invoice, InvoiceStatus
from billing.service import InvoiceService

__all__ = ["Invoice", "InvoiceService", "InvoiceStatus"]
```

## Imports

### A module is imported as a module, a class or a function by name

**Why:** `labels.print_label(...)` or `print_label(...)` says what is used; a three-level attribute
chain hides it in the middle of an expression.

### A function-level import is allowed for three reasons, written on its line

**Why:** breaking a genuine circular import, loading a heavy or optional implementation on demand,
and a facade exporting implementations whose libraries are separate extras; generic "lazy loading"
is not a reason — restructure instead.

### An annotation that would cycle or pull a heavy dependency goes under `TYPE_CHECKING`

**Why:** the import then costs nothing at runtime.
**Except:** never one a framework reads at runtime — a validating model's field, a route's parameter
— where the guarded name is missing when the framework resolves it; ruff's runtime-evaluated tables
keep those imports real.

**Example:**
```python
# WRONG — the whole PDF engine is imported to annotate one parameter
from billing.pdf import PdfRenderer


def attach_pdf(invoice: Invoice, *, renderer: PdfRenderer) -> None:
    invoice_storage.put(invoice.number, renderer.render(invoice))


# CORRECT — the name exists for the checker only
if TYPE_CHECKING:
    from billing.pdf import PdfRenderer


def attach_pdf(invoice: Invoice, *, renderer: PdfRenderer) -> None:
    invoice_storage.put(invoice.number, renderer.render(invoice))
```

### Every direct dependency is declared, and none is feature-detected

**Why:** a package imported only because another dependency pulls it in disappears when that one
drops it; `try: import x` turns a missing dependency into a code path nobody tested.

### Anything acquired is released by a context manager

**Why:** a file, a lock, a session or a client opened without one stays open when the block raises;
who closes what, and failing cleanup, are in `python-wiring`.

---
name: python-layers
description: >-
  Enforces layer boundaries with import-linter: layers, independence and forbidden contracts, and a
  violation fixed by moving code. Use when adding an import-linter contract, deciding which layer
  code belongs to, untangling a circular import or an ImportError from a partially initialized
  module, or when a domain module imports a framework, a driver or a sibling implementation.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Layers

Dependency direction is enforced by tooling, not by review vigilance: import-linter contracts live
in `pyproject.toml` beside the type checker's configuration, and `lint-imports` runs in CI beside
mypy — a contract nobody runs holds nothing up. Three kinds do the work, and most codebases stop
after the first. How directories are named and nested is a project decision — it follows the
domain, the team and the deployment shape; what is fixed is which way dependencies point, and that
a contract and its implementations share one directory (`python-contracts`).

## Contracts

### Every package with an order has a `layers` contract: peers on one line, every module placed

**Why:** one contract for the repository leaves everything below the top layer a free-for-all once
it has more than three modules, so a subpackage with its own order gets its own contract. Two lines
are two heights — modules at one height that must not import each other share a line,
`inspections | repairs`, or the next edit invents an order nobody meant. Without `exhaustive = true`
a `tyres.py` added next week belongs to no layer and may import anything.

**Example:**
```toml
# WRONG — three heights where two were meant, and a new module in no layer goes unchecked
[[tool.importlinter.contracts]]
name = "Maintenance layers"
type = "layers"
containers = ["fleet.maintenance"]
layers = ["planner", "inspections", "repairs"]


# CORRECT — peers on one line below the planner; a module in no layer breaks the contract
[[tool.importlinter.contracts]]
name = "Maintenance layers"
type = "layers"
containers = ["fleet.maintenance"]
layers = ["planner", "inspections | repairs"]
exhaustive = true
```

### Implementations behind one contract are independent of each other

**Why:** it is what makes the tenth implementation cost what the second did: when one borrows a
helper from its sibling, the eleventh is a new file plus an edit to the sibling. Every
implementation, plugin or registry handler is in an `independence` contract whose only permitted
edge is to the shared contract — matched by a wildcard, since a listed set misses the next one.

**Example:**
```toml
# WRONG — the implementations are listed, so a third one added later is never checked
[[tool.importlinter.contracts]]
name = "Telematics trackers must not know about each other"
type = "independence"
modules = ["fleet.telematics.geotab", "fleet.telematics.samsara"]


# CORRECT — every module in the package, now and later; only the contract may be shared
[[tool.importlinter.contracts]]
name = "Telematics trackers must not know about each other"
type = "independence"
modules = ["fleet.telematics.*"]
ignore_imports = ["fleet.telematics.* -> fleet.telematics.base"]
```

### An optional library is `forbidden` across the package, with every permitted edge listed

**Why:** "an extra's library is imported only by its own implementation module" is stated everywhere
and checked almost nowhere; the exception list of a `forbidden` contract is the inventory of where
the extra may appear, reviewed whenever it grows. Only `include_external_packages = true` lets the
contract see a library — measured on import-linter 2.15, a domain module importing `stripe` passed
without it, with one warning that the ignored imports matched nothing. An API banned outright goes
to the linter too: `flake8-tidy-imports.banned-api` names the replacement where the import happens,
which a contract cannot.

**Example:**
```toml
# WRONG — external packages are invisible, so the contract passes whatever imports stripe
[tool.importlinter]
root_package = "fleet"

[[tool.importlinter.contracts]]
name = "Optional dependencies live only in their own implementation"
type = "forbidden"
source_modules = ["fleet"]
forbidden_modules = ["stripe", "boto3"]


# CORRECT — the contract sees libraries, and each allowed edge carries its extra
[tool.importlinter]
root_package = "fleet"
include_external_packages = true

[[tool.importlinter.contracts]]
name = "Optional dependencies live only in their own implementation"
type = "forbidden"
source_modules = ["fleet"]
forbidden_modules = ["stripe", "boto3"]
ignore_imports = [
  "fleet.storage.s3 -> boto3",  # extra `s3`: the one module that may use its SDK
  "fleet.billing.stripe_gateway -> stripe",  # extra `stripe`: the one gateway that calls it
]
```

## Violations

### A violation is fixed by moving code or inverting the dependency, never by an allowlist entry

**Why:** an exception added to make a contract pass removes the check for the next import too. The
fix is a contract plus an adapter, with the concrete class chosen at the composition root; an
exception that remains needs the justification of a type suppression and carries its reason on the
line above it.

**Example:**
```python
# WRONG — servicing imports the calendar implementation, so the contract needs an exception
from fleet.garages.google_calendar import GoogleGarageCalendar


def book_service_visit(visit: ServiceVisit, *, calendar: GoogleGarageCalendar) -> None:
    calendar.reserve(visit.garage_id, starts_at=visit.starts_at, vehicle_vin=visit.vehicle_vin)


# CORRECT — it depends on the contract; the composition root passes the Google calendar in
from fleet.garages.base import GarageCalendar


def book_service_visit(visit: ServiceVisit, *, calendar: GarageCalendar) -> None:
    calendar.reserve(visit.garage_id, starts_at=visit.starts_at, vehicle_vin=visit.vehicle_vin)
```

### Domain code imports the standard library and other domain modules only

**Why:** a framework, a driver or a client in the domain ties the rules to one way of storing or
serving them, and every test of a rule pulls the library in. They enter through adapters, and the
domain's types are frozen dataclasses (`types.md`).

**Example:**
```python
# WRONG — a domain entity is a framework's model
from django.db import models


class Vehicle(models.Model):
    vin = models.CharField(max_length=17)
    odometer_km = models.PositiveIntegerField()
    next_service_on = models.DateField()


# CORRECT — the domain owns its type; the boundary maps to it
from dataclasses import dataclass


@final
@dataclass(frozen=True, slots=True, kw_only=True)
class Vehicle:
    vin: str
    odometer_km: int
    next_service_on: date
```

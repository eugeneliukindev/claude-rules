---
name: python-wiring
description: >-
  Designs construction and configuration: one composition root, default collaborators, scopes,
  resource lifetime, settings, constants, parameter objects. Use when writing an entry point or
  an application factory, deciding where an object is built, opening a pool or a client, adding
  a settings field or a constant, or removing a global. Not for which layer imports which
  (python-layers).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Wiring: Composition Root, Resource Lifetime

Which layer may import which is `python-layers`; in an ASGI service the composition root is the
application's lifespan (`python-fastapi`). Collaborators arrive through the constructor
(`classes.md`), plain values instead of the settings object (`functions.md`), nothing runs at import
(`modules.md`), and a test hands in fakes instead of patching (`testing.md`).

## Composition Root

### All construction happens in one place — the composition root

**Why:** the entry point of a worker or CLI, or the application factory of a service, is the one
place that knows every concrete class; a function below it that opens its own resources is a second
root, and no test or second entry point can hand it another.

**Example:**
```python
# WRONG — a second root below main: the intake opens its own pool from a URL it was handed
def run_loan_intake(*, registry_url: str, batch_size: int) -> None:
    with RegistryPool(registry_url) as pool:
        office = LoanOffice(agreements=PostgresAgreementLedger(pool))
        consume_loan_requests(office, batch_size=batch_size)


def main() -> None:
    settings = Settings()
    run_loan_intake(registry_url=settings.registry_url, batch_size=settings.intake_batch_size)


# CORRECT — main builds settings, resources, adapters and services, and hands them down
def main() -> None:
    settings = Settings()
    with RegistryPool(settings.registry_url) as pool:
        office = LoanOffice(agreements=PostgresAgreementLedger(pool))
        consume_loan_requests(office, batch_size=settings.intake_batch_size)
```

### The root chooses an implementation from settings; a class never does

**Why:** a constructor that picks between two implementations from a flag is a second composition
root hidden in a class: it must know every implementation's settings, and a test has to set the
flag to reach the fake.

**Example:**
```python
# WRONG — the channel is chosen inside, from values the reminders should not know
@final
class ReturnReminders:
    def __init__(
        self, *, agreements: AgreementLedger, portal_enabled: bool, portal_url: str
    ) -> None:
        self._agreements = agreements
        self._lender_channel = (
            LenderPortalChannel(base_url=portal_url) if portal_enabled else LenderEmailChannel()
        )

    def remind_ending(self, today: date) -> None:
        for agreement in self._agreements.ending_on(today):
            self._lender_channel.send(agreement.lender_id, f"Loan {agreement.number} ends today")


# CORRECT — the root chose and built the channel; the reminders take the contract
@final
class ReturnReminders:
    def __init__(self, *, agreements: AgreementLedger, lender_channel: LenderChannel) -> None:
        self._agreements = agreements
        self._lender_channel = lender_channel

    def remind_ending(self, today: date) -> None:
        for agreement in self._agreements.ending_on(today):
            self._lender_channel.send(agreement.lender_id, f"Loan {agreement.number} ends today")
```

### A default collaborator is what production runs, and needs no setting

**Why:** `clock: Clock | None = None` then `clock or WallClock()` is what pydantic
(`ns_resolver or NsResolver()`) and the OpenTelemetry SDK (`span_limits or SpanLimits()`) do: the
parameter is a seam for a test or a second root, and the default costs the caller nothing. A default
that needs a setting wastes that setting whenever the collaborator is passed.
**Except:** `is None` instead of `or` when a valid value can be falsy — an empty mapping, `0`. A
plain value — a path, a limit — is no collaborator: it is defaulted in the signature
(`functions.md`).

**Example:**
```python
# WRONG — the default needs a URL, so courier_api_url is wasted whenever couriers are passed
@final
class CourierScheduler:
    def __init__(
        self,
        *,
        courier_api_url: str,
        couriers: CourierBooking | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._couriers = couriers or CourierApiBooking(base_url=courier_api_url)
        self._clock = clock or WallClock()

    def book_courier(self, agreement: LoanAgreement) -> CourierSlot:
        return self._couriers.book(agreement.exhibit_id, earliest=self._clock.now())


# CORRECT — the clock defaults to what production runs; the couriers are built by the root
@final
class CourierScheduler:
    def __init__(self, *, couriers: CourierBooking, clock: Clock | None = None) -> None:
        self._couriers = couriers
        self._clock = clock or WallClock()

    def book_courier(self, agreement: LoanAgreement) -> CourierSlot:
        return self._couriers.book(agreement.exhibit_id, earliest=self._clock.now())
```

### The wiring is plain code; a container, if one is used at all, never leaves the root

**Why:** a container is unnecessary until wiring is measured in hundreds of objects, and one handed
below the root is a service locator: the signature no longer lists what the class needs, and a
test must register every lookup before the first call.
**Except:** module-level names that hold nothing until the root configures them (`modules.md`) —
and the task-queue app object tasks are decorated with, whose pools the worker's startup hook
builds.

**Example:**
```python
# WRONG — the container reached from inside: what the desk needs is known only at run time
@final
class GalleryDesk:
    def __init__(self, *, container: Container) -> None:
        self._container = container

    def assign_gallery(self, exhibit: Exhibit) -> GalleryId:
        return self._container.resolve(GalleryPlanner).free_gallery_for(exhibit)


# CORRECT — the root resolved the planner and passed it in
@final
class GalleryDesk:
    def __init__(self, *, planner: GalleryPlanner) -> None:
        self._planner = planner

    def assign_gallery(self, exhibit: Exhibit) -> GalleryId:
        return self._planner.free_gallery_for(exhibit)
```

### Scopes are explicit: application-scoped objects built once, request-scoped by a passed factory

**Why:** an object with per-request state built once is shared between requests; a pooled resource
built per request exhausts the pool.

**Example:**
```python
# WRONG — one request's glossary built once: the first request's language answers every request
@final
class WallLabelWriter:
    def __init__(self, *, glossary: LabelGlossary) -> None:
        self._glossary = glossary

    def write_label(self, exhibit: Exhibit) -> str:
        return self._glossary.caption(exhibit.title_key, lender=exhibit.lender_name)


# CORRECT — the writer holds the factory; each request builds the glossary for its own locale
@final
class WallLabelWriter:
    def __init__(self, *, glossary_for: Callable[[Locale], LabelGlossary]) -> None:
        self._glossary_for = glossary_for

    def write_label(self, exhibit: Exhibit, *, locale: Locale) -> str:
        return self._glossary_for(locale).caption(exhibit.title_key, lender=exhibit.lender_name)
```

## Resource Lifetime

**Before writing a `with` or `async with` over a pool, a client or a session, a `@contextmanager`,
an `ExitStack`, or a `close()` method, read [lifetime.md](lifetime.md)** — the library's own
context manager, one `with` per known set, the async root, a class closing only what it built,
cleanup that never raises over the block's error, no process-wide mutation.

## Constants

**Before adding a module constant or a constants module, read [constants.md](constants.md)** — a
constant lives beside the one module that owns its concept, never in a grab-bag.

## Settings and Startup

**Before adding or reading a settings field, an environment variable, a feature flag or a secret,
read [settings.md](settings.md)** — typed settings built at the root, the server's apart from the
application's, no branch on the environment's name, validation at startup, secrets without
defaults.

## Parameter Objects

**Before grouping parameters into an options object or forwarding `**kwargs`, read
[parameter-objects.md](parameter-objects.md)** — a concept the callee uses whole, never the
configuration root renamed; typed options through `Unpack`.

---
paths:
  - "**/*.py"
---

# Python — Functions

## What a Function Does

### A function does one thing

**Why:** if describing it needs "and", the caller who wants one half gets both; split it. One actor
per module is a different rule (`classes.md`).

### Values that travel together become one frozen dataclass

**Why:** the same four parameters on five functions are a concept without a name, and the next
function gets three of them in another order (the test is in `python-wiring`); collaborators that
travel together are a constructor instead (`classes.md`, trigger 4).

**Example:**
```python
# WRONG — the stay travels as two loose dates through every signature
def free_rooms(check_in: date, check_out: date, *, rooms: RoomRepository) -> list[Room]:
    return rooms.free_between(check_in, check_out)


# CORRECT — one value, with its invariant checked once
@dataclass(frozen=True, slots=True, kw_only=True)
class Stay:
    check_in: date
    check_out: date

    def __post_init__(self) -> None:
        if self.check_out <= self.check_in:
            raise InvalidStayError(self.check_in, self.check_out)


def free_rooms(stay: Stay, *, rooms: RoomRepository) -> list[Room]:
    return rooms.free_between(stay.check_in, stay.check_out)
```

### What every caller would repeat lives inside the function

**Why:** a parameter is for a value callers actually vary; a retry, an encoding or a reshaping that
every caller passes or does the same way belongs in the body, written once. A setting is the
exception: it is defaulted in the signature, so no caller repeats it and a test still varies it
(below).


## Parameters

### The subject first, then required inputs; dependencies and options by keyword after `*`

**Why:** the call reads as being about its subject, a new dependency never shifts a position, and
the root binds dependencies with `partial(f, mailer=...)`.
**Except:** a payload a library hands in, its name meaning nothing to the caller, is positional-only
(`/`); a signature a framework dictates keeps the framework's order.

**Example:**
```python
# WRONG — the dependency first: the call reads as if it were about the mail
def send_receipt(mailer: Mailer, payment: Payment) -> None:
    mailer.send(payment.customer_email, f"Receipt for {payment.amount}")


# CORRECT — the subject first, the dependency named at every call
def send_receipt(payment: Payment, *, mailer: Mailer) -> None:
    mailer.send(payment.customer_email, f"Receipt for {payment.amount}")


# CORRECT — a payload the webhook library passes positionally
async def on_webhook(body: bytes, /, *, verifier: SignatureVerifier) -> None:
    verifier.verify(body)
```

### A boolean that selects between two behaviours is two functions, or a `Literal` or `Enum`

**Why:** `export(readings, as_csv=True)` hides two bodies behind one name, keyword-only or not.
**Except:** a keyword-only boolean that tunes one behaviour — `sorted(reverse=)`,
`subprocess.run(check=)` — is fine; the test is whether the branches share a body.

**Example:**
```python
# WRONG — keyword-only, and still two behaviours behind one name
def export(readings: Sequence[SensorReading], *, as_csv: bool) -> bytes:
    return render_csv(readings) if as_csv else render_parquet(readings)


# CORRECT — the format is a closed set the caller names
def export(readings: Sequence[SensorReading], export_format: ExportFormat) -> bytes:
    return _RENDERER_BY_FORMAT[export_format](readings)


# CORRECT — one behaviour, tuned: both orders share the whole body
def rank(readings: Sequence[SensorReading], *, descending: bool = False) -> list[SensorReading]:
    return sorted(readings, key=lambda reading: reading.celsius, reverse=descending)
```

### A function or a class takes plain values or a config dataclass, never the settings object

**Why:** middleware that kept the settings object it was given changed behaviour when someone edited
that object after startup; fields copied at construction cannot. The signature of a function taking
`settings: Settings` stops being a dependency list, and a test has to build the whole tree for one
call — an untyped `**kwargs` has the same defect. The settings object is what the environment
filled at start: the entry point reads it and unpacks it, into plain values or, for a group that
travels together, a frozen config dataclass (`python-wiring`).

**Example:**
```python
# WRONG — the signature hides what is read, and a test builds every settings group for one call
@final
class RateFetcher:
    def __init__(self, *, client: HttpClient, settings: Settings) -> None:
        self._client = client
        self._settings = settings

    def fetch(self) -> RateTable:
        return self._client.get_rates(
            self._settings.rates_url, timeout_seconds=self._settings.rates_timeout_seconds
        )


# CORRECT — the signature is the dependency list; the root unpacks the settings
@final
class RateFetcher:
    def __init__(self, *, client: HttpClient, rates_url: str, timeout_seconds: float) -> None:
        self._client = client
        self._rates_url = rates_url
        self._timeout_seconds = timeout_seconds

    def fetch(self) -> RateTable:
        return self._client.get_rates(self._rates_url, timeout_seconds=self._timeout_seconds)
```

### A function uses only its parameters and module constants

**Why:** global mutable state, an imported `settings`, a clock or randomness read inside are inputs
no caller can see and no test can fix.
**Except:** a fresh identifier or token whose value no test compares, and a monotonic reading that
only measures a duration, are made inside.

**Example:**
```python
# WRONG — the clock and the lifetime come from outside, and no test can fix either
def is_expired(token: AccessToken) -> bool:
    return datetime.now(UTC) > token.issued_at + settings.token_lifetime


# CORRECT — both arrive as parameters
def is_expired(token: AccessToken, *, now: datetime, lifetime: timedelta) -> bool:
    return now > token.issued_at + lifetime
```

### A setting a function or a method reads is a keyword parameter defaulted to a module constant

**Why:** a timeout, a limit, a TTL, a size, a retry count, a deadline, an interval, a path — read in
the body, it can be changed only by patching the module; defaulted in the signature
(`*, timeout_seconds: float = _TIMEOUT_SECONDS`), a caller passes nothing and a test passes what it
needs. A constructor takes it the same way and keeps it in a field.
**Except:** the root (`main`, `run`, `lifespan`), a test, a fixture and a signature a framework
parses — a route, a WebSocket endpoint, a broker subscriber, a GraphQL resolver, where a defaulted
parameter is an input the client sets — read the constant where they stand. A decorator's argument
is evaluated at import, and a value fixed by a format or a protocol — a file's magic bytes, a
header's name — is not a setting; both stay as they are.

**Example:**
```python
# WRONG — the limit is read inside: a test of the rejection must upload twenty megabytes
@final
class UploadInbox:
    def __init__(self, *, storage: ObjectStorage) -> None:
        self._storage = storage

    def accept(self, upload: Upload) -> str:
        if upload.size_bytes > _MAX_UPLOAD_BYTES:
            raise UploadTooLargeError(upload.name, limit_bytes=_MAX_UPLOAD_BYTES)
        return self._storage.put(upload.name, upload.content)


# CORRECT — the root passes nothing, and a test of the rejection passes ten bytes
@final
class UploadInbox:
    def __init__(
        self, *, storage: ObjectStorage, max_upload_bytes: int = _MAX_UPLOAD_BYTES
    ) -> None:
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes

    def accept(self, upload: Upload) -> str:
        if upload.size_bytes > self._max_upload_bytes:
            raise UploadTooLargeError(upload.name, limit_bytes=self._max_upload_bytes)
        return self._storage.put(upload.name, upload.content)
```

## Results

### The branch does not pick the return type

**Why:** `str` on one path and `list[str]` on another makes every caller re-discover which it got.
**Except:** a named closed union — `type PaymentOutcome = Captured | Declined`, matched
exhaustively; `None` for a lookup where absence is normal.

### Compute or do, not both

**Why:** a query has no side effects, so it can be called twice or skipped; a command returns `None`
or the outcome of its own effect — the id it assigned, the row count, the item it removed — never a
value a reader would mistake for a lookup, and never behind a `get_` (`naming.md`).

**Example:**
```python
# WRONG — a getter that opens a session when none exists
def get_session(user_id: UserId, *, sessions: SessionStore) -> LoginSession:
    session = sessions.find(user_id)
    return session if session is not None else sessions.open(user_id)


# CORRECT — the command says what it does, and returns the id it assigned
def open_session(user_id: UserId, *, sessions: SessionStore) -> SessionId:
    return sessions.open(user_id).session_id
```

### A result is returned, never written into a parameter

**Why:** a collection passed in to be filled is an output disguised as an input; the caller cannot
tell from the call that it changes.

## Extraction

### A helper is extracted only when it pays, and inlined when a shallow-helper test fires

**Why:** a helper's name, signature and docstring are an interface; it pays only by hiding more than
it exposes. Extract when at least one holds: **real reuse** today; **required as an object** — a
callback, a `key=`, a dispatch value; it **hides genuine complexity** and the name is then enough;
the parent would otherwise **break its limits** and the extraction restores one level of
abstraction; it **needs its own test seam**; it is a **named predicate** (`control-flow.md`).
Inline it when the signature is longer than the body, the reader opens the body anyway, reading the
parent means flipping back and forth, three parameters only rebuild the parent's context, the body
is one call or one expression, or the name is a moment (`_step_two`, `_log_outcome`) not an action.

**Example:**
```python
# WRONG — extracted to make room for a docstring: a stage name, one call site, a one-line body
def import_rates(*, client: RatesClient) -> int:
    rates = client.fetch_all()
    _log_outcome(len(rates), client.request_count)
    return len(rates)


def _log_outcome(imported: int, requests: int) -> None:
    """Log both counts; zero imports alone is ambiguous."""
    logger.info("import finished", extra={"imported": imported, "requests": requests})


# CORRECT — the same call inline, the reason in one line
def import_rates(*, client: RatesClient) -> int:
    rates = client.fetch_all()
    # requests tells an expired key or a rate limit apart from an honestly empty feed
    logger.info("import finished", extra={"imported": len(rates), "requests": client.request_count})
    return len(rates)
```

## Body Layout

### Guards first, the work at one indentation level, the result last

**Why:** a guard that returns or raises at once keeps the happy path at level 1; a happy path nested
inside an `if` makes the reader hold the condition for the whole body. A step below its siblings'
level is extracted, length alone never is.

**Example:**
```python
# WRONG — the work is nested inside the conditions it depends on
def send_receipt(payment: Payment, *, mailer: Mailer) -> None:
    if payment.is_captured:
        if payment.customer_email is not None:
            mailer.send(payment.customer_email, f"Receipt for {payment.amount}")


# CORRECT — the guards return, and the work stands at level 1
def send_receipt(payment: Payment, *, mailer: Mailer) -> None:
    if not payment.is_captured or payment.customer_email is None:
        return

    mailer.send(payment.customer_email, f"Receipt for {payment.amount}")
```

### Each value a later call needs is named on its own line, and the steps fall into blocks

**Why:** a value built inside another call's arguments hides a step — the reader unpicks the
nesting to learn what is made — and when one sibling is named and the other inlined, the asymmetry
suggests a difference that is not there. Named, each line is one step; a blank line separates the
blocks that belong together — what is shared, what is built from it, what is assembled — and none
falls inside a block.
**Except:** a trivial conversion or a literal — `str(order_id)`, `Decimal("0.2")` — stays inline;
naming it adds a line and no meaning.

**Example:**
```python
# WRONG — one channel named, its sibling built inside the constructor call, no blocks
def build_sensor_pipeline(
    *, site: str, serial_port: str, station_name: str = _STATION_NAME
) -> SensorPipeline:
    station = StationIdentity(name=station_name, site=site)
    readings = open_reading_stream(station, port=serial_port)
    return SensorPipeline(readings, open_alarm_channel(station, port=serial_port))


# CORRECT — what is shared, what is built from it, what is assembled: one block each
def build_sensor_pipeline(
    *, site: str, serial_port: str, station_name: str = _STATION_NAME
) -> SensorPipeline:
    station = StationIdentity(name=station_name, site=site)

    readings = open_reading_stream(station, port=serial_port)
    alarms = open_alarm_channel(station, port=serial_port)

    return SensorPipeline(readings, alarms)
```

### A function stays at one level of abstraction

**Why:** an orchestrator that mixes calls to its steps with the arithmetic of one of them makes the
reader switch levels mid-function.

**Example:**
```python
# WRONG — the month-close steps, with the VAT arithmetic of one of them inlined
def close_month(period: BillingPeriod, *, invoices: InvoiceRepository, ledger: Ledger) -> None:
    issued = invoices_in(period, invoices=invoices)
    vat = sum((invoice.total * _VAT_RATE for invoice in issued), start=Decimal(0))
    ledger.record_vat(period, vat.quantize(_CENT, ROUND_HALF_EVEN))
    ledger.lock(period)


# CORRECT — only calls at the orchestrator's own level
def close_month(period: BillingPeriod, *, invoices: InvoiceRepository, ledger: Ledger) -> None:
    issued = invoices_in(period, invoices=invoices)
    ledger.record_vat(period, vat_due(issued))
    ledger.lock(period)
```

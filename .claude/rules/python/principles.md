---
paths:
  - "**/*.py"
---

# Python — Principles

Five, in priority order; when two rules conflict the earlier principle wins. **Correct** — the code
does what its name and signature promise for every input the types allow, and fails loudly
otherwise. **Readable** — a teammate new to the file understands it top-down without opening
others. **Simple** — the least machinery that solves today's problem. **Typed** — illegal states
are unrepresentable; the checker catches the mistake, not the reviewer. **Fast enough, by
measurement** — algorithmic sanity always, anything more with a profile in hand.

## The System as a Whole

### A failure stays where it happened

**Why:** one bad input or one unreachable dependency never stops the run; name what is protected —
this row, this source, this request — and catch at exactly that boundary, recording the reason.
Degradation has a stated direction — skip, retry later, serve stale, return partial — written where
the code makes the choice.

**Example:**
```python
# WRONG — the boundary is the whole loop: one unreachable rate and nothing after it is refreshed
def refresh_rates(currencies: Iterable[Currency], *, source: RateSource, rates: RateStore) -> None:
    try:
        for currency in currencies:
            rates.save(currency, source.fetch(currency))
    except RateSourceError:
        logger.warning("rate refresh failed")


# CORRECT — the boundary is one currency: it is recorded and skipped, the run goes on
def refresh_rates(currencies: Iterable[Currency], *, source: RateSource, rates: RateStore) -> None:
    for currency in currencies:
        try:
            rate = source.fetch(currency)
        except RateSourceError:
            logger.warning("rate fetch failed", extra={"currency": currency})
            continue
        rates.save(currency, rate)
```

### Cost grows slower than the work

**Why:** every external collection has a limit, every fan-out a semaphore, every run a deadline,
every cache an expiry — one without grew per request and was never read; "it has always been
small" is not a bound.

**Example:**
```python
# WRONG — every customer's statement fetched at once, however many customers there are
async def fetch_statements(
    customer_ids: Sequence[CustomerId], *, api: StatementApi
) -> list[Statement]:
    return list(await asyncio.gather(*(api.statement(customer_id) for customer_id in customer_ids)))


# CORRECT — at most max_in_flight requests, under one deadline
async def fetch_statements(
    customer_ids: Sequence[CustomerId],
    *,
    api: StatementApi,
    max_in_flight: int = _MAX_IN_FLIGHT,
    deadline_seconds: float = _STATEMENTS_DEADLINE_SECONDS,
) -> list[Statement]:
    limit = asyncio.Semaphore(max_in_flight)

    async def fetch(customer_id: CustomerId) -> Statement:
        async with limit:
            return await api.statement(customer_id)

    async with asyncio.timeout(deadline_seconds), asyncio.TaskGroup() as group:
        tasks = [group.create_task(fetch(customer_id)) for customer_id in customer_ids]
    return [task.result() for task in tasks]
```

## SOLID

### A module or a class answers to one actor — whoever asks for its changes

**Why:** SRP is about the actor — the person or role who asks for changes — and holds for a module
and a class alike; "does one thing" is the rule for a function, not this one. Code answering to two
actors ships the fix one of them asks for to the other; the test is *who*, not *which layer*.
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

### A new case is data or a new file, never a new branch in something that works

**Why:** this is OCP: a branch added to working code is a change to code that worked; kind in, implementation
out through a mapping the root builds — adding a kind is one entry, deleting one as easy.

**Example:**
```python
# WRONG — each new channel edits the function every other channel depends on
def notify(recipient: Recipient, message: Message, *, channel: Channel) -> None:
    if channel is Channel.EMAIL:
        send_email(recipient.email, message)
    elif channel is Channel.SMS:
        send_sms(recipient.phone, message)


# CORRECT — a new channel is a new notifier and one entry where the root builds the mapping
def notify(
    recipient: Recipient, message: Message, *, notifiers: Mapping[Channel, Notifier]
) -> None:
    notifiers[recipient.preferred_channel].send(recipient, message)
```

### A subclass accepts at least what its parent accepts and returns nothing wider

**Why:** this is LSP: code written against the parent must work with the subclass. A signature
mismatch is a type error, and nothing checks the behaviour — no new precondition, no dropped
promise, no new exception.

**Example:**
```python
class ReadingSink(ABC):
    @abstractmethod
    def record(self, reading: MeterReading) -> RecordedReading: ...


# WRONG — narrows the parameter: a caller passing any MeterReading to a ReadingSink fails here
@final
class SqlReadingSink(ReadingSink):
    def __init__(self, *, readings: ReadingTable, utility_code: str) -> None:
        self._readings = readings
        self._utility_code = utility_code

    @override
    def record(self, reading: VerifiedReading) -> RecordedReading:
        reading_id = self._readings.insert(self._utility_code, reading.meter_id, reading.kwh)
        return RecordedReading(reading_id=reading_id)


# CORRECT — accepts what the parent accepts, and promises something narrower back
@final
class SqlReadingSink(ReadingSink):
    def __init__(self, *, readings: ReadingTable, utility_code: str) -> None:
        self._readings = readings
        self._utility_code = utility_code

    @override
    def record(self, reading: MeterReading) -> BilledReading:
        reading_id = self._readings.insert(self._utility_code, reading.meter_id, reading.kwh)
        return BilledReading(reading_id=reading_id, billing_period=reading.billing_period)
```

### A contract holds only what its consumer calls

**Why:** this is ISP: a consumer handed more depends on it — its fake must implement it, and a
change to a method it never calls reaches it anyway. One class may implement several contracts; the
split is in what the consumer is given, not in the storage.
**Except:** split when a consumer that needs a different set exists, not in advance — a catalogue
every caller uses whole stays one contract.

**Example:**
```python
# WRONG — the specimen count receives the whole catalogue, writes included
class SpecimenCatalogue(ABC):
    @abstractmethod
    def add(self, specimen: Specimen) -> None: ...

    @abstractmethod
    def specimens_of(self, genus: Genus) -> list[Specimen]: ...


def count_specimens(genus: Genus, *, catalogue: SpecimenCatalogue) -> SpecimenCount:
    return SpecimenCount(genus=genus, specimen_count=len(catalogue.specimens_of(genus)))


# CORRECT — the specimen count depends on the one capability it uses
class SpecimenLookup(ABC):
    @abstractmethod
    def specimens_of(self, genus: Genus) -> list[Specimen]: ...


def count_specimens(genus: Genus, *, catalogue: SpecimenLookup) -> SpecimenCount:
    return SpecimenCount(genus=genus, specimen_count=len(catalogue.specimens_of(genus)))
```

### Collaborators arrive through the constructor, never built inside

**Why:** this is dependency inversion by injection: the class depends on the contract, and the
composition root decides the implementation. One built inside cannot be replaced in a test, and the
signature hides what it needs.

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

## YAGNI, KISS, DRY

### Build what today's requirement needs, with the simplest construction that solves it

**Why:** a speculative option or a pluggable format with one implementation is a branch never known
to work, and a generalisation built for one case is a guess about the second; the boring mechanism —
a function over a class, a dict over a registry — is the one the next reader understands.

**Example:**
```python
# WRONG — a pluggable format nobody asked for, with one implementation
def export_responses(
    responses: Sequence[SurveyResponse],
    *,
    format_factory: Callable[[], ResponseFormatter] = CsvFormatter,
) -> bytes:
    return format_factory().format(responses)


# CORRECT — the one format the requirement names
def export_responses_csv(responses: Sequence[SurveyResponse]) -> bytes:
    return render_csv(responses)
```

### DRY is about knowledge, not text, and waits for the third occurrence

**Why:** identical fragments answering to different actors are not duplication — merged, the next
change arrives as a flag; fragments that must change together are duplication however different
they look — a limit in a validator and in a schema is one constant both read.

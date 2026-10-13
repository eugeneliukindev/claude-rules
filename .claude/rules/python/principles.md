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


# CORRECT — at most _MAX_IN_FLIGHT requests, under one deadline
async def fetch_statements(
    customer_ids: Sequence[CustomerId], *, api: StatementApi
) -> list[Statement]:
    limit = asyncio.Semaphore(_MAX_IN_FLIGHT)

    async def fetch(customer_id: CustomerId) -> Statement:
        async with limit:
            return await api.statement(customer_id)

    async with asyncio.timeout(_STATEMENTS_DEADLINE_SECONDS), asyncio.TaskGroup() as group:
        tasks = [group.create_task(fetch(customer_id)) for customer_id in customer_ids]
    return [task.result() for task in tasks]
```

### A new case is data or a new file, never a new branch in something that works

**Why:** the next person is you, without the context: a branch added to working code is a change to
code that worked; one actor per module, and deleting must be as easy as adding.

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

## YAGNI, KISS, DRY

### Build what today's requirement needs

**Why:** a speculative feature costs everything that must keep it working, and a generalisation
built for one case is a guess about the second; an option nobody sets is a branch never known to
work — a test client's flag did nothing for two majors.

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

### The simplest construction that fully solves the problem, judged where it is used

**Why:** the boring mechanism — a function over a class, a dict over a registry — is the one the
next reader understands; simplest is not shortest.

**Example:**
```python
# WRONG — a registry class with decorators for four fixed tax rates
@final
class TaxRateRegistry:
    def __init__(self) -> None:
        self._rate_by_country: dict[Country, Decimal] = {}

    def register(self, country: Country, rate: Decimal) -> None:
        self._rate_by_country[country] = rate

    def rate(self, country: Country) -> Decimal:
        return self._rate_by_country[country]


# CORRECT — a mapping, readable in one place
_VAT_RATE_BY_COUNTRY: Final = MappingProxyType({
    Country.DE: Decimal("0.19"),
    Country.FR: Decimal("0.20"),
})
```

### DRY is about knowledge, not text, and waits for the third occurrence

**Why:** identical fragments answering to different actors are not duplication — merged, the next
change arrives as a parameter, then a flag, then a branch; fragments that must change together are
duplication however different they look — a limit in a validator and in a schema. A shared
constant often cures it.

**Example:**
```python
# WRONG — one limit, written twice: change one and the published schema and the check disagree
INVOICE_SCHEMA: Final = {"type": "object", "properties": {"lines": {"maxItems": 100}}}


def check_invoice(invoice: Invoice) -> None:
    if len(invoice.lines) > 100:
        raise InvoiceTooLongError(invoice.number)


# CORRECT — one fact, one constant, read by both
MAX_INVOICE_LINES: Final = 100
INVOICE_SCHEMA: Final = {"type": "object", "properties": {"lines": {"maxItems": MAX_INVOICE_LINES}}}


def check_invoice(invoice: Invoice) -> None:
    if len(invoice.lines) > MAX_INVOICE_LINES:
        raise InvoiceTooLongError(invoice.number)
```

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

### A new case is data or a new file, never a new branch in something that works

**Why:** a branch added to working code is a change to code that worked; kind in, implementation
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

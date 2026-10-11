---
paths:
  - "**/tests/**/*.py"
  - "**/test_*.py"
  - "**/conftest.py"
  - "**/testing/**/*.py"
  - "**/fakes.py"
---

# Testing

Supplement to the other Python rules, for writing and reviewing tests. `pytest` is the framework;
its mechanics — async tests, property tests, HTTP and container fixtures, coverage — are in
`python-pytest`.

## Levels

### Most tests are unit, fewer integration, and only critical user flows end-to-end

**Why:** the pyramid keeps the suite fast enough to run on every change. A test belongs to one
level; how the levels are kept apart — directory, marker, naming — is a project decision, that they
are is not.

- **Unit** — one function or class, collaborators replaced by in-memory fakes; fast enough that
  nobody thinks about running them. Every new function and class gets them.
- **Integration** — components against real infrastructure: database, broker, cache.
- **End-to-end** — complete user-facing flows against a running system, critical paths only.

**Example:**
```python
# WRONG — a unit test that needs a running database: the fast suite is no longer fast
def test_renew_subscription_extends_the_period(engine: Engine) -> None:
    subscriptions = PostgresSubscriptionRepository(engine)
    subscriptions.add(_ACTIVE)

    renewed = renew_subscription(_ACTIVE.subscription_id, subscriptions=subscriptions)

    assert renewed.ends_on == date(2027, 3, 1)


# CORRECT — the rule against a fake; the repository's own test is an integration test, marked
def test_renew_subscription_extends_the_period() -> None:
    subscriptions = InMemorySubscriptionRepository([_ACTIVE])

    renewed = renew_subscription(_ACTIVE.subscription_id, subscriptions=subscriptions)

    assert renewed.ends_on == date(2027, 3, 1)


@pytest.mark.integration
def test_postgres_repository_returns_the_subscription_it_stored(engine: Engine) -> None:
    subscriptions = PostgresSubscriptionRepository(engine)
    subscriptions.add(_ACTIVE)

    stored = subscriptions.get(_ACTIVE.subscription_id)

    assert stored == _ACTIVE
```

### An integration test runs against the real infrastructure

**Why:** a mocked database only proves the mock works — the constraint, the transaction and the SQL
dialect are what this level exists to exercise.

**Example:**
```python
# WRONG — the "integration" test of a repository mocks the session it integrates with
async def test_member_repository_finds_saved_member(mocker: MockerFixture) -> None:
    session = mocker.create_autospec(AsyncSession, instance=True)
    repository = PostgresMemberRepository(session=session)

    await repository.add(Member(card_number="C-1042", name="Ann Lee"))

    session.add.assert_called_once()


# CORRECT — the session comes from a database container fixture; the row is read back
async def test_member_repository_finds_saved_member(session: AsyncSession) -> None:
    repository = PostgresMemberRepository(session=session)

    await repository.add(Member(card_number="C-1042", name="Ann Lee"))

    assert await repository.find("C-1042") == Member(card_number="C-1042", name="Ann Lee")
```

## Fakes, Not Mocks

### A contract a unit test depends on has an in-memory fake, held to the contract suite

**Why:** a fake exercises the contract; a `MagicMock` records calls and accepts methods that do not
exist, so a renamed method keeps every mocked test green. The fake lives in `tests/fakes.py`,
inherits the contract like any implementation and passes the same contract suite as the real ones
(`python-contracts`).
**Except:** a contract only integration tests reach needs no fake until a unit test does.

**Example:**
```python
# WRONG — a bare mock stands in for the notifier: send_confirmation does not exist, and passes
def test_booking_confirms_ticket_to_holder(mocker: MockerFixture) -> None:
    notifier = mocker.MagicMock()
    booking = TicketBooking(notifier=notifier)

    booking.book(Seat(row=12, letter="A"), holder="ann@example.com")

    notifier.send_confirmation.assert_called()


# CORRECT — tests/fakes.py: the fake implements the contract and records what it was given
@final
class InMemoryNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    @override
    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


def test_booking_confirms_ticket_to_holder() -> None:
    notifier = InMemoryNotifier()
    booking = TicketBooking(notifier=notifier)

    booking.book(Seat(row=12, letter="A"), holder="ann@example.com")

    assert notifier.sent == [Notification(recipient="ann@example.com", subject="Seat 12A booked")]
```

### Mock only a process boundary you do not own, always against the real class

**Why:** the network and the broker sit behind a third-party class no contract of yours describes;
there the `mocker` fixture (or `unittest.mock.patch` as a context manager) mocks it with
`create_autospec`, so a method it lacks or a wrong argument fails the test. The clock is never
mocked — it is injected and replaced by a manual one (Determinism, below).

**Example:**
```python
# WRONG — a bare mock: the mailer could call any method with any arguments, and pass
def test_smtp_mailer_addresses_recipient(mocker: MockerFixture) -> None:
    smtp = mocker.MagicMock()
    mailer = SmtpMailer(connection=smtp, sender="billing@example.com")

    mailer.send(recipient="ann@example.com", subject="Receipt", body="Paid in full")

    assert smtp.send_message.call_args.args[0]["To"] == "ann@example.com"


# CORRECT — the spec is smtplib's class: a name or a signature it does not have raises
def test_smtp_mailer_addresses_recipient(mocker: MockerFixture) -> None:
    smtp = mocker.create_autospec(smtplib.SMTP, instance=True)
    mailer = SmtpMailer(connection=smtp, sender="billing@example.com")

    mailer.send(recipient="ann@example.com", subject="Receipt", body="Paid in full")

    assert smtp.send_message.call_args.args[0]["To"] == "ann@example.com"
```

### Patching your own module is a design signal: inject the dependency instead

**Why:** `patch("library.registration._send_welcome")` ties the test to a private name and a module
path, so a move that changes no behaviour breaks it; the dependency should have been a constructor
parameter.
**Except:** a boundary that cannot be injected — stdlib internals, third-party module state.

**Example:**
```python
# WRONG — the test reaches into the module and replaces a private function
def test_registration_welcomes_new_member(mocker: MockerFixture) -> None:
    send_welcome = mocker.patch("library.registration._send_welcome")
    registration = Registration(members=InMemoryMemberRepository())

    registration.register("ann@example.com")

    send_welcome.assert_called_once_with("ann@example.com")


# CORRECT — the notifier is a constructor parameter, and the test passes the fake
def test_registration_welcomes_new_member() -> None:
    notifier = InMemoryNotifier()
    registration = Registration(members=InMemoryMemberRepository(), notifier=notifier)

    registration.register("ann@example.com")

    assert notifier.sent == [Notification(recipient="ann@example.com", subject="Welcome")]
```

### Assert the outcome, not the conversation

**Why:** an `assert_called_once_with` chain mirrors the implementation line by line — it breaks on
every refactor and catches nothing the outcome would not. Check the return value or the state of
the fake.

**Example:**
```python
# WRONG — the test restates which repository calls the lending makes
def test_lending_marks_book_on_loan(mocker: MockerFixture) -> None:
    books = mocker.create_autospec(BookRepository, instance=True)
    books.get.return_value = Book(isbn="978-0134757599", is_on_loan=False)
    lending = Lending(books=books)

    lending.lend("978-0134757599", member="C-1042")

    books.get.assert_called_once_with("978-0134757599")
    books.save.assert_called_once_with(Book(isbn="978-0134757599", is_on_loan=True))


# CORRECT — the fake holds the book; the test reads the state the lending left behind
def test_lending_marks_book_on_loan() -> None:
    books = InMemoryBookRepository([Book(isbn="978-0134757599", is_on_loan=False)])
    lending = Lending(books=books)

    lending.lend("978-0134757599", member="C-1042")

    assert books.get("978-0134757599").is_on_loan
```

## Structure

### Arrange, act, assert — three phases, each separated by a blank line

**Why:** the reader finds the action under test without reading the setup; an assertion between two
actions makes one test about two things.

**Example:**
```python
# WRONG — the phases interleave: is the first conversion under test, or the second?
def test_converter_uses_latest_rate() -> None:
    rates = InMemoryExchangeRates()
    rates.publish(Currency.EUR, Currency.USD, Decimal("1.08"))
    converter = Converter(rates=rates)
    first = converter.convert(Money(Decimal(10), Currency.EUR), to=Currency.USD)
    assert first == Money(Decimal("10.80"), Currency.USD)
    rates.publish(Currency.EUR, Currency.USD, Decimal("1.10"))
    second = converter.convert(Money(Decimal(10), Currency.EUR), to=Currency.USD)
    assert second == Money(Decimal("11.00"), Currency.USD)


# CORRECT — the setup, the one action, the outcome
def test_converter_uses_latest_rate() -> None:
    rates = InMemoryExchangeRates()
    rates.publish(Currency.EUR, Currency.USD, Decimal("1.08"))
    rates.publish(Currency.EUR, Currency.USD, Decimal("1.10"))
    converter = Converter(rates=rates)

    converted = converter.convert(Money(Decimal(10), Currency.EUR), to=Currency.USD)

    assert converted == Money(Decimal("11.00"), Currency.USD)
```

### Several input/output cases are one `parametrize`, each `pytest.param` with an `id`

**Why:** copied tests drift apart, and the id is what a failing run prints — `parcel1-expected1`
names nothing; a plain-words scenario names the broken case.
**Except:** a table of scalars alone may leave the ids to pytest, which prints the values.

**Example:**
```python
# WRONG — pytest names the cases parcel0-expected_rate0 and so on
@pytest.mark.parametrize(
    ("parcel", "expected_rate"),
    [
        (Parcel(weight_grams=500, zone=Zone.DOMESTIC), Decimal("4.50")),
        (Parcel(weight_grams=2500, zone=Zone.DOMESTIC), Decimal("9.00")),
        (Parcel(weight_grams=500, zone=Zone.INTERNATIONAL), Decimal("12.00")),
    ],
)
def test_parcel_rate(parcel: Parcel, expected_rate: Decimal) -> None:
    assert parcel_rate(parcel) == expected_rate


# CORRECT — each case says the scenario a failure is about
@pytest.mark.parametrize(
    ("parcel", "expected_rate"),
    [
        pytest.param(
            Parcel(weight_grams=500, zone=Zone.DOMESTIC), Decimal("4.50"), id="light_domestic"
        ),
        pytest.param(
            Parcel(weight_grams=2500, zone=Zone.DOMESTIC), Decimal("9.00"), id="heavy_domestic"
        ),
        pytest.param(
            Parcel(weight_grams=500, zone=Zone.INTERNATIONAL), Decimal("12.00"), id="abroad"
        ),
    ],
)
def test_parcel_rate(parcel: Parcel, expected_rate: Decimal) -> None:
    assert parcel_rate(parcel) == expected_rate
```

### A test you write is a file in the suite, and it stays

**Why:** a check run once inline and then deleted proved nothing to the next change. The folder the
tests write their outputs to is in `.gitignore`.

**Example:**
```bash
# WRONG — checked once in the terminal, gone with it
python -c "from shipping.rates import parcel_rate; print(parcel_rate(sample_parcel()))"

# CORRECT — the same check, a test every later change runs too
uv run pytest tests/unit/shipping/test_rates.py
```

## Names and Assertions

### A test name is a specification

**Why:** the name is what a failing run prints; `test_<unit>_<scenario>_<expected>` or behaviour
phrasing says what broke before anyone opens the file. Never `test_1`, `test_happy_path`, or a name
that only repeats the function's.

**Example:**
```python
# WRONG — the report says "test_allow_2 failed", and nothing about what was expected
def test_allow_2() -> None:
    bucket = TokenBucket(capacity=1, refill_per_second=0, clock=ManualClock(_NOON))
    bucket.allow()

    allowed = bucket.allow()

    assert not allowed


# CORRECT — the name states the scenario and the expected outcome
def test_allow_rejects_request_when_bucket_is_empty() -> None:
    bucket = TokenBucket(capacity=1, refill_per_second=0, clock=ManualClock(_NOON))
    bucket.allow()

    allowed = bucket.allow()

    assert not allowed
```

### One behaviour per test

**Why:** a test that checks two behaviours stops at the first failure and hides the second, and its
name cannot state both. Several asserts are fine when they verify facets of one outcome.

**Example:**
```python
# WRONG — renewal and cancellation in one test: a broken renewal hides the cancellation
def test_subscription_renewal() -> None:
    subscription = make_subscription(renews_on=date(2026, 3, 1))

    subscription.renew()
    subscription.cancel()

    assert subscription.renews_on == date(2026, 4, 1)
    with pytest.raises(SubscriptionCancelledError, match="cancelled"):
        subscription.renew()


# CORRECT — one behaviour each, and each name says which
def test_renew_moves_renewal_date_by_one_month() -> None:
    subscription = make_subscription(renews_on=date(2026, 3, 1))

    subscription.renew()

    assert subscription.renews_on == date(2026, 4, 1)


def test_renew_is_refused_after_cancellation() -> None:
    subscription = make_subscription(is_cancelled=True)

    with pytest.raises(SubscriptionCancelledError, match="cancelled"):
        subscription.renew()
```

### `pytest.raises` takes `match=`, or the test compares the error's payload

**Why:** a bare `pytest.raises(SeatTakenError)` passes on the wrong one — raised by the arrange
step, or for another seat. `match=` takes a distinctive fragment of the message, or the test
compares the whole structured payload the error carries (`excinfo.value.errors() == [...]`); the
carried data is asserted too.

**Example:**
```python
# WRONG — any SeatTakenError passes, including one for a different seat
def test_reserve_rejects_taken_seat() -> None:
    venue = Venue(seats=[Seat(row=12, letter="A")])
    venue.reserve(Seat(row=12, letter="A"), holder="ann@example.com")

    with pytest.raises(SeatTakenError):
        venue.reserve(Seat(row=12, letter="A"), holder="bob@example.com")


# CORRECT — the message fragment and the carried seat pin the error down
def test_reserve_rejects_taken_seat() -> None:
    venue = Venue(seats=[Seat(row=12, letter="A")])
    venue.reserve(Seat(row=12, letter="A"), holder="ann@example.com")

    with pytest.raises(SeatTakenError, match="seat 12A is taken") as excinfo:
        venue.reserve(Seat(row=12, letter="A"), holder="bob@example.com")

    assert excinfo.value.seat == Seat(row=12, letter="A")
```

### Warnings are errors in the suite, and an expected one is asserted

**Why:** with `filterwarnings = ["error"]` a deprecation fails the day it appears, not the release
that removes the API. A test of a deprecated path asserts the warning with `pytest.warns(...,
match=...)`, and such tests sit together, so removing the path deletes them in one place.

**Example:**
```python
# WRONG — the warning is silenced: nothing says this test covers a path that is going away
@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_import_reads_legacy_csv() -> None:
    members = import_members(_LEGACY_CSV)

    assert members == [Member(card_number="C-1042", name="Ann Lee")]


# CORRECT — the deprecation is part of the asserted behaviour
def test_import_reads_legacy_csv() -> None:
    with pytest.warns(DeprecationWarning, match="legacy CSV"):
        members = import_members(_LEGACY_CSV)

    assert members == [Member(card_number="C-1042", name="Ann Lee")]
```

## Data

### Fixtures are factories, not shared constants

**Why:** a shared object a dozen tests silently depend on changes for all of them the day one test
needs it different; a factory hands each test a valid default it overrides in one place. Shared
fixtures and factories live in the nearest `conftest.py`; one a single module uses lives there.

**Example:**
```python
# WRONG — one shared subscription: the test that needs it cancelled edits it for everyone
@pytest.fixture
def subscription() -> Subscription:
    return Subscription(subscriber="ann@example.com", plan=Plan.MONTHLY, renews_on=date(2026, 3, 1))


# CORRECT — each test builds the subscription it needs and states only what matters to it
def make_subscription(
    *,
    plan: Plan = Plan.MONTHLY,
    renews_on: date = date(2026, 3, 1),
    is_cancelled: bool = False,
) -> Subscription:
    return Subscription(
        subscriber="ann@example.com", plan=plan, renews_on=renews_on, is_cancelled=is_cancelled
    )
```

### Test data says only what matters

**Why:** values the behaviour depends on are explicit in the test, everything else comes from the
factory defaults — the reader sees what the outcome turns on. A magic value outside a parametrize
table gets the same named-constant treatment as production code.

**Example:**
```python
# WRONG — five fields, and only the start time matters to a reminder
def test_reminder_is_due_a_day_before_appointment() -> None:
    appointment = Appointment(
        patient="Ann Lee",
        doctor="Dr. Okafor",
        room="3B",
        starts_at=datetime(2026, 5, 4, 9, 30, tzinfo=UTC),
        duration=timedelta(minutes=30),
    )

    reminder_at = reminder_time(appointment)

    assert reminder_at == datetime(2026, 5, 3, 9, 30, tzinfo=UTC)


# CORRECT — the start time is the one value the test states
def test_reminder_is_due_a_day_before_appointment() -> None:
    appointment = make_appointment(starts_at=datetime(2026, 5, 4, 9, 30, tzinfo=UTC))

    reminder_at = reminder_time(appointment)

    assert reminder_at == datetime(2026, 5, 3, 9, 30, tzinfo=UTC)
```

## Determinism

### Time, randomness and order are fixed by the test, and a wait polls with a timeout

**Why:** a test that reads the real clock or sleeps is slow, and flaky on a loaded runner. Time
comes from the injected clock — `time-machine` only for code you do not own that reads the clock
itself; randomness is seeded; `pytest-randomly` surfaces hidden ordering dependencies; a wait polls
with a timeout instead of `sleep()`. Unit tests may use pytest's sandboxes such as `tmp_path`; they
never touch the network, real time or global state.

**Example:**
```python
# WRONG — the real clock and a real wait: a second of every run, and flaky under load
def test_session_expires_after_idle_timeout() -> None:
    sessions = SessionStore(idle_timeout=timedelta(seconds=1), clock=SystemClock())
    session_id = sessions.open("ann@example.com")

    time.sleep(1.1)

    assert sessions.find(session_id) is None


# CORRECT — tests/fakes.py: a clock the test moves; the boundary is exact and nothing waits
@final
class ManualClock(Clock):
    def __init__(self, now: datetime) -> None:
        self._now = now

    @override
    def now(self) -> datetime:
        return self._now

    def advance(self, elapsed: timedelta) -> None:
        self._now += elapsed


def test_session_expires_after_idle_timeout() -> None:
    clock = ManualClock(datetime(2026, 5, 4, 9, 0, tzinfo=UTC))
    sessions = SessionStore(idle_timeout=timedelta(minutes=30), clock=clock)
    session_id = sessions.open("ann@example.com")

    clock.advance(timedelta(minutes=30))

    assert sessions.find(session_id) is None
```

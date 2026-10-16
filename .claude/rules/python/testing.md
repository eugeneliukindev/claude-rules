---
paths:
  - "**/tests/**/*.py"
  - "**/test_*.py"
  - "**/conftest.py"
  - "**/testing/**/*.py"
  - "**/fakes.py"
---

# Testing

Supplement to the other Python rules, for writing and reviewing tests; `pytest` is the framework.

## Levels

### A unit test replaces collaborators with fakes; an integration test uses real infrastructure

**Why:** most tests are unit - one function or class, fast enough that nobody thinks about running
them, and every new function and class gets them; integration tests exercise the constraint, the
transaction and the SQL dialect, which a mocked database only pretends to. A test belongs to one
level, and the levels are kept apart by directory or marker.

**Example:**
```python
# WRONG - the "integration" test of a repository mocks the connection it integrates with
def test_member_repository_finds_saved_member(mocker: MockerFixture) -> None:
    connection = mocker.create_autospec(sqlite3.Connection, instance=True)
    repository = SqliteMemberRepository(connection=connection)

    repository.add(Member(card_number="C-1042", name="Ann Lee"))

    connection.execute.assert_called_once()


# CORRECT - a real database from a fixture, migrated; the row is read back
def test_member_repository_finds_saved_member(connection: sqlite3.Connection) -> None:
    repository = SqliteMemberRepository(connection=connection)

    repository.add(Member(card_number="C-1042", name="Ann Lee"))

    assert repository.find("C-1042") == Member(card_number="C-1042", name="Ann Lee")
```

### A test you write is a file in the suite, and it stays

**Why:** a check run once inline and then deleted proved nothing to the next change.

**Example:**
```bash
# WRONG - checked once in the terminal, gone with it
python -c "from shipping.rates import parcel_rate; print(parcel_rate(sample_parcel()))"

# CORRECT - the same check, a test every later change runs too
uv run pytest tests/unit/shipping/test_rates.py
```

## Structure

### A test is Arrange-Act-Assert with one act, and its name states the behaviour as given, when, then

**Why:** a failing test should read as the broken specification. `test_<when>_<then>`, or
`test_given_..._when_..._then_...` where the setup decides it, names the behaviour; `test_renew` names a
function. The body is three phases separated by blank lines - arrange, one act, assert - so the call
under test is found at a glance; a second act is a second test.

**Example:**
```python
# WRONG - named for the function, two acts, no phases: a failure says only that renew broke
def test_renew() -> None:
    loan = make_loan(due_on=date(2026, 6, 1))
    loan.renew(days=14)
    assert loan.due_on == date(2026, 6, 15)
    loan.renew(days=14)
    assert loan.renewal_count == 2


# CORRECT - the name is the specification, and one act sits between its phases
def test_renewing_loan_moves_due_date_by_requested_days() -> None:
    loan = make_loan(due_on=date(2026, 6, 1))

    loan.renew(days=14)

    assert loan.due_on == date(2026, 6, 15)
```

## Fakes, Not Mocks

### A contract a unit test depends on has an in-memory fake, the test asserts the outcome, and only a process boundary you do not own is mocked, against the real class

**Why:** a `MagicMock` accepts methods that do not exist, so a renamed method keeps every test
green, and an `assert_called_once_with` chain breaks on every refactor. The fake inherits the
contract and passes its contract suite. Patching your own module means a missing constructor
parameter. A third-party class gets `mocker.create_autospec(smtplib.SMTP, instance=True)`; the
clock is injected.
**Except:** a contract only integration tests reach needs no fake until a unit test does.

**Example:**
```python
# WRONG - a bare mock stands in for the notifier: send_confirmation does not exist, and passes
def test_booking_confirms_ticket_to_holder(mocker: MockerFixture) -> None:
    notifier = mocker.MagicMock()
    booking = TicketBooking(notifier=notifier)

    booking.book(Seat(row=12, letter="A"), holder="ann@example.com")

    notifier.send_confirmation.assert_called()


# CORRECT - tests/fakes.py: the fake implements the contract and records what it was given
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

## Assertions and Data

### Cases are one `parametrize`, each `pytest.param` with an `id`

**Why:** copied tests drift apart, and the id is what a failing run prints - `parcel1-expected1`
names nothing.
**Except:** a table of scalars alone may leave the ids to pytest, which prints the values.

**Example:**
```python
# WRONG - pytest names the cases parcel0-expected_rate0 and so on
@pytest.mark.parametrize(
    ("parcel", "expected_rate"),
    [
        (Parcel(weight_grams=500, zone=Zone.DOMESTIC), Decimal("4.50")),
        (Parcel(weight_grams=500, zone=Zone.INTERNATIONAL), Decimal("12.00")),
    ],
)
def test_parcel_rate(parcel: Parcel, expected_rate: Decimal) -> None:
    assert parcel_rate(parcel) == expected_rate


# CORRECT - each case says the scenario a failure is about
@pytest.mark.parametrize(
    ("parcel", "expected_rate"),
    [
        pytest.param(Parcel(weight_grams=500, zone=Zone.DOMESTIC), Decimal("4.50"), id="domestic"),
        pytest.param(
            Parcel(weight_grams=500, zone=Zone.INTERNATIONAL), Decimal("12.00"), id="abroad"
        ),
    ],
)
def test_parcel_rate(parcel: Parcel, expected_rate: Decimal) -> None:
    assert parcel_rate(parcel) == expected_rate
```

### An expected error or warning is pinned with `match=`, and warnings are errors in the suite

**Why:** a bare `pytest.raises(SeatTakenError)` passes on the wrong one - raised by the arrange
step, or for another seat; the carried data is asserted too. With `filterwarnings = ["error"]` a
deprecation fails the day it appears, and a test of a deprecated path asserts it with
`pytest.warns(..., match=...)`.

**Example:**
```python
# WRONG - any SeatTakenError passes, including one for a different seat
def test_reserve_rejects_taken_seat() -> None:
    venue = Venue(seats=[Seat(row=12, letter="A")])
    venue.reserve(Seat(row=12, letter="A"), holder="ann@example.com")

    with pytest.raises(SeatTakenError):
        venue.reserve(Seat(row=12, letter="A"), holder="bob@example.com")


# CORRECT - the message fragment and the carried seat pin the error down
def test_reserve_rejects_taken_seat() -> None:
    venue = Venue(seats=[Seat(row=12, letter="A")])
    venue.reserve(Seat(row=12, letter="A"), holder="ann@example.com")

    with pytest.raises(SeatTakenError, match="seat 12A is taken") as excinfo:
        venue.reserve(Seat(row=12, letter="A"), holder="bob@example.com")

    assert excinfo.value.seat == Seat(row=12, letter="A")
```

### Each test arranges its own data through the code's public functions, else through the library's API in a factory; nothing seeded is shared

**Why:** a public function changes only with behaviour and validates on the way in. Where none
reaches a state, the data is bulk or the test checks the stored row, a factory in
`tests/factories.py` writes through the library's API (`session.add`). A helper the test does not
check - a `session_add()` wrapper - breaks it for its own reasons; a class-wide seed couples every
test to every row. Each test builds only what it asserts on.
**Except:** reference data no test writes may be seeded once per session.

**Example:**
```python
# WRONG - a class-wide seed through the project's row helper: every test depends on every row
@pytest.fixture(scope="class", autouse=True)
def seeded_subscriptions(database: Database) -> None:
    insert_row(database, "subscriptions", subscriber="ann@example.com", plan="monthly")
    insert_row(database, "subscriptions", subscriber="bob@example.com", plan="yearly")


# CORRECT - the test arranges through the same public functions a client calls
def test_renewing_yearly_plan_moves_date_by_a_year(subscriptions: SubscriptionStore) -> None:
    subscription_id = subscribe(
        "ann@example.com", plan=Plan.YEARLY, starts_on=date(2026, 3, 1), subscriptions=subscriptions
    )

    renewed = renew(subscription_id, subscriptions=subscriptions)

    assert renewed.renews_on == date(2027, 3, 1)
```

## Determinism

### Time, randomness and order are fixed by the test, and a wait polls with a timeout

**Why:** a test that reads the real clock or sleeps is slow, and flaky on a loaded runner. Time
comes from the injected clock - `time-machine` only for code you do not own that reads the clock
itself; randomness is seeded; a wait polls with a timeout instead of `sleep()`. Unit tests never
touch the network, real time or global state.

**Example:**
```python
# WRONG - the real clock and a real wait: a second of every run, and flaky under load
def test_session_expires_after_idle_timeout() -> None:
    sessions = SessionStore(idle_timeout=timedelta(seconds=1), clock=SystemClock())
    session_id = sessions.open("ann@example.com")

    time.sleep(1.1)

    assert sessions.find(session_id) is None


# CORRECT - tests/fakes.py: a clock the test moves; the boundary is exact and nothing waits
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

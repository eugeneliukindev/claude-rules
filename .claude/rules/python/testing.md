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

**Why:** most tests are unit — one function or class, fast enough that nobody thinks about running
them, and every new function and class gets them; integration tests exercise the constraint, the
transaction and the SQL dialect, which a mocked database only pretends to. A test belongs to one
level, and the levels are kept apart by directory or marker.

**Example:**
```python
# WRONG — the "integration" test of a repository mocks the connection it integrates with
def test_member_repository_finds_saved_member(mocker: MockerFixture) -> None:
    connection = mocker.create_autospec(sqlite3.Connection, instance=True)
    repository = SqliteMemberRepository(connection=connection)

    repository.add(Member(card_number="C-1042", name="Ann Lee"))

    connection.execute.assert_called_once()


# CORRECT — a real database from a fixture, migrated; the row is read back
def test_member_repository_finds_saved_member(connection: sqlite3.Connection) -> None:
    repository = SqliteMemberRepository(connection=connection)

    repository.add(Member(card_number="C-1042", name="Ann Lee"))

    assert repository.find("C-1042") == Member(card_number="C-1042", name="Ann Lee")
```

### A test you write is a file in the suite, and it stays

**Why:** a check run once inline and then deleted proved nothing to the next change.

**Example:**
```bash
# WRONG — checked once in the terminal, gone with it
python -c "from shipping.rates import parcel_rate; print(parcel_rate(sample_parcel()))"

# CORRECT — the same check, a test every later change runs too
uv run pytest tests/unit/shipping/test_rates.py
```

## Fakes, Not Mocks

### A contract a unit test depends on has an in-memory fake, and the test asserts the outcome

**Why:** a fake exercises the contract; a `MagicMock` accepts methods that do not exist, so a
renamed method keeps every mocked test green, and an `assert_called_once_with` chain mirrors the
implementation and breaks on every refactor. The fake lives in `tests/fakes.py`, inherits the
contract and passes the same contract suite as the real implementations; the test checks the
return value or the fake's state. Patching your own module — `patch("library.registration._send")`
— means the dependency should have been a constructor parameter.
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
there `mocker.create_autospec(smtplib.SMTP, instance=True)` makes a method it lacks or a wrong
argument fail the test. The clock is never mocked — it is injected (Determinism, below).

## Assertions and Data

### Cases are one `parametrize`, each `pytest.param` with an `id`

**Why:** copied tests drift apart, and the id is what a failing run prints — `parcel1-expected1`
names nothing.
**Except:** a table of scalars alone may leave the ids to pytest, which prints the values.

**Example:**
```python
# WRONG — pytest names the cases parcel0-expected_rate0 and so on
@pytest.mark.parametrize(
    ("parcel", "expected_rate"),
    [
        (Parcel(weight_grams=500, zone=Zone.DOMESTIC), Decimal("4.50")),
        (Parcel(weight_grams=500, zone=Zone.INTERNATIONAL), Decimal("12.00")),
    ],
)
def test_parcel_rate(parcel: Parcel, expected_rate: Decimal) -> None:
    assert parcel_rate(parcel) == expected_rate


# CORRECT — each case says the scenario a failure is about
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

**Why:** a bare `pytest.raises(SeatTakenError)` passes on the wrong one — raised by the arrange
step, or for another seat; the carried data is asserted too. With `filterwarnings = ["error"]` a
deprecation fails the day it appears, and a test of a deprecated path asserts it with
`pytest.warns(..., match=...)`.

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

### Fixtures are factories with valid defaults; a test states only the values it turns on

**Why:** a shared object a dozen tests silently depend on changes for all of them the day one test
needs it different; a `make_subscription(*, plan=..., renews_on=...)` factory in the nearest
`conftest.py` hands each test a default it overrides in one place, so the reader sees what the
outcome depends on.
**Except:** a frozen value every test only reads — an id, an instant — is a module constant.

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

## Determinism

### Time, randomness and order are fixed by the test, and a wait polls with a timeout

**Why:** a test that reads the real clock or sleeps is slow, and flaky on a loaded runner. Time
comes from the injected clock — `time-machine` only for code you do not own that reads the clock
itself; randomness is seeded; a wait polls with a timeout instead of `sleep()`. Unit tests never
touch the network, real time or global state.

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

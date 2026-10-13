---
name: python-persistence
description: >-
  Designs persistence whatever the ORM: a transaction per use case, a unit of work, repositories
  returning domain objects, N+1, keyset pagination, optimistic locking, upserts and SKIP LOCKED.
  Use when deciding where a transaction begins and ends, writing a repository, paginating a query,
  or guarding against lost updates.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Persistence

These rules hold for any ORM or query builder. How to spell them in SQLAlchemy is
`python-sqlalchemy`, in raw asyncpg `python-asyncpg`; a DataLoader for GraphQL is
`python-strawberry`; schema changes are `python-migrations`.

## Transactions

### One use case is one transaction, opened by the service in a unit of work

**Why:** the service method is the boundary — entry points do not manage transactions, and
repositories do not commit, or a failed second write leaves the first one committed. The unit of
work is a context manager that opens one transaction, exposes the repositories bound to it, commits
on a clean exit, rolls back on an exception and releases its connection; one kept past the use case
holds a pooled connection and serves what it read earlier to the next one. The `with` is written in
the service — a decorator or middleware that wraps everything hides the boundary and makes a
two-transaction use case impossible to see.

**Example:**
```python
# WRONG — each repository commits its own write: a failed seat reservation leaves a booking
@final
class TicketBooking:
    def __init__(self, *, bookings: BookingRepository, seats: SeatRepository) -> None:
        self._bookings = bookings
        self._seats = seats

    def book(self, request: BookingRequest) -> BookingId:
        booking_id = self._bookings.add(Booking.create(request))
        self._seats.reserve(request.seat_ids)
        return booking_id


# CORRECT — one unit of work: both writes commit together or neither does
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def book(self, request: BookingRequest) -> BookingId:
        with self._unit_of_work() as unit:
            booking_id = unit.bookings.add(Booking.create(request))
            unit.seats.reserve(request.seat_ids)
        return booking_id
```

### Nothing slow or irreversible runs inside a transaction

**Why:** a slow call holds row locks for its whole duration, and a rollback cannot unsend an email.
Side effects run after commit; one that must be atomic with the data is an outbox row written in
the same transaction and published separately (the consuming side: `python-workers`).

**Example:**
```python
# WRONG — the mail server's latency holds row locks, and a rollback cannot unsend the email
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: Callable[[], UnitOfWork], mailer: Mailer) -> None:
        self._unit_of_work = unit_of_work
        self._mailer = mailer

    def book(self, request: BookingRequest) -> BookingId:
        with self._unit_of_work() as unit:
            booking_id = unit.bookings.add(Booking.create(request))
            self._mailer.send_confirmation(request.holder_email, booking_id)
        return booking_id


# CORRECT — the email goes after commit, when the booking it confirms exists
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: Callable[[], UnitOfWork], mailer: Mailer) -> None:
        self._unit_of_work = unit_of_work
        self._mailer = mailer

    def book(self, request: BookingRequest) -> BookingId:
        with self._unit_of_work() as unit:
            booking_id = unit.bookings.add(Booking.create(request))
        self._mailer.send_confirmation(request.holder_email, booking_id)
        return booking_id
```

### An async unit of work is entered with `async with`

**Why:** a cancelled task must roll back like a failed one, and the cancellation reaches
`__aexit__` as an exception. A `begin()` … `commit()` pair written by hand commits nothing and rolls
back nothing when the task is cancelled between them, and the connection goes back to the pool
mid-transaction.

**Example:**
```python
# WRONG — a cancellation between the add and the commit leaves the transaction open
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: AsyncUnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    async def book(self, booking: Booking) -> BookingId:
        unit = await self._unit_of_work.begin()
        booking_id = await unit.bookings.add(booking)
        await unit.commit()
        return booking_id


# CORRECT — commit on a clean exit, rollback on an error or a cancellation alike
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: AsyncUnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    async def book(self, booking: Booking) -> BookingId:
        async with self._unit_of_work() as unit:
            return await unit.bookings.add(booking)
```

### A deadlock or serialization failure retries the whole unit of work, at the level that raises it

**Why:** the database has already rolled the transaction back, so retrying the statement inside it
is meaningless; the retry re-runs the use case from the start, which is safe only because side
effects run after commit. This is the one retry above the adapter (`python-boundaries`). A
serialization failure exists only under `REPEATABLE READ` or `SERIALIZABLE` — under the default
`READ COMMITTED` the second of two read-then-update transactions overwrites the first without an
error, and the retry never fires — so a use case that relies on it opens its unit of work at the
stricter level. The `return` sits inside the loop: a value assigned there and returned after it is
what mypy's `possibly-undefined` reports.

**Example:**
```python
# WRONG — the retry runs inside a transaction the database has already rolled back
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def book(self, request: BookingRequest) -> BookingId:
        with self._unit_of_work() as unit:
            for attempt in _RETRY_ON_CONFLICT:
                with attempt:
                    return unit.bookings.add(Booking.create(request))
        raise AssertionError("unreachable: the last attempt's error propagates from the loop")


# CORRECT — each attempt opens a fresh unit of work, at the level that can raise the conflict
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: UnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work

    def book(self, request: BookingRequest) -> BookingId:
        for attempt in _RETRY_ON_CONFLICT:
            with attempt, self._unit_of_work(isolation=Isolation.REPEATABLE_READ) as unit:
                return unit.bookings.add(Booking.create(request))
        raise AssertionError("unreachable: the last attempt's error propagates from the loop")
```

### Every database connection carries server-side timeouts

**Why:** `statement_timeout` bounds a query, `lock_timeout` a wait for a lock, and
`idle_in_transaction_session_timeout` a transaction the application opened and abandoned, which
otherwise holds its locks until someone kills it. They are set once — on the pool or the database
role — never per query by memory; the client-side half is in `python-boundaries`.

**Example:**
```sql
-- WRONG — no server-side limits: an abandoned transaction holds its row locks indefinitely
CREATE ROLE ticketing LOGIN;

-- CORRECT — every session of the role is bounded, whatever the client forgets
CREATE ROLE ticketing LOGIN;
ALTER ROLE ticketing SET statement_timeout = '5s';
ALTER ROLE ticketing SET lock_timeout = '2s';
ALTER ROLE ticketing SET idle_in_transaction_session_timeout = '30s';
```

## Repositories

### A repository takes and returns domain objects; the ORM row stops at it

**Why:** an ORM row handed to a service carries change tracking — an attribute set "just for this
calculation" is written back at the next flush — and a detached row that lazy-loads after its
transaction closed fails far from the cause. The repository holds query construction only: no
business rules, no commits. A rule computable from loaded data is a pure function over domain
objects that the service loads, calls and saves, so it is tested with plain values and no fake.

**Example:**
```python
# WRONG — the service gets a tracked row: any attribute it sets is written at the next flush
@final
class SqlBookingRepository(BookingRepository):
    def __init__(self, *, rows: BookingRows) -> None:
        self._rows = rows

    @override
    def find(self, booking_id: BookingId) -> BookingRow | None:
        return self._rows.get(booking_id)


# CORRECT — the row stops at the repository; the service gets a frozen Booking
@final
class SqlBookingRepository(BookingRepository):
    def __init__(self, *, rows: BookingRows) -> None:
        self._rows = rows

    @override
    def find(self, booking_id: BookingId) -> Booking | None:
        row = self._rows.get(booking_id)
        if row is None:
            return None
        return Booking(
            booking_id=BookingId(row.id), event_id=EventId(row.event_id), status=row.status
        )
```

### Every relationship is loaded explicitly, and a test pins the statements per use case

**Why:** lazy loading switched off makes an N+1 an error at the first test instead of a page that
quietly runs a hundred queries. It does not catch an explicit query inside a loop — a repository
call per booking is an N+1 the ORM never sees — so an integration test asserts the number of
statements a use case runs, and fails the day it grows.

**Example:**
```python
# WRONG — one query per booking: a hundred bookings are a hundred and one statements
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def holders_of(self, event_id: EventId) -> list[Holder]:
        with self._unit_of_work() as unit:
            bookings = unit.bookings.for_event(event_id)
            return [unit.holders.get(booking.holder_id) for booking in bookings]


# CORRECT — one query for the holders of every booking at once
@final
class TicketBooking:
    def __init__(self, *, unit_of_work: Callable[[], UnitOfWork]) -> None:
        self._unit_of_work = unit_of_work

    def holders_of(self, event_id: EventId) -> list[Holder]:
        with self._unit_of_work() as unit:
            bookings = unit.bookings.for_event(event_id)
            return unit.holders.get_many([booking.holder_id for booking in bookings])
```

## Idempotent Inserts

**Before inserting a row that a repeat — a redelivery, a retry, a double click — may insert again,
read [upserts.md](upserts.md)** — one `INSERT … ON CONFLICT` on the unique key, `DO NOTHING
RETURNING` to tell a repeat apart.

## A Table Used as a Queue

**Before claiming rows from a table that several workers poll, read
[queue-tables.md](queue-tables.md)** — `FOR UPDATE SKIP LOCKED`.

## Pagination

**Before paginating a query, read [pagination.md](pagination.md)** — keyset from the last key seen,
with a unique tiebreaker and a matching index; offset only for a small bounded list.

## Lost Updates

**Before writing a read-modify-write that spans a user's think time or concurrent requests, read
[optimistic-locking.md](optimistic-locking.md)** — a version column, zero rows updated as a
conflict, re-read instead of retried.

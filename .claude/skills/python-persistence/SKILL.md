---
name: python-persistence
description: >-
  Designs persistence whatever the ORM: a transaction per use case committed by the service,
  repositories returning domain objects, N+1, keyset pagination, optimistic locking, upserts and
  SKIP LOCKED. Use when deciding where a transaction begins and ends, writing a repository,
  paginating a query, or guarding against lost updates. Not for the ORM's own API (python-
  sqlalchemy).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Persistence

These rules hold for any ORM or query builder. How to spell them in SQLAlchemy is
`python-sqlalchemy`, in raw asyncpg `python-asyncpg`; a DataLoader for GraphQL is
`python-strawberry`; schema changes are `python-migrations`.

## Transactions

### One use case is one transaction: the edge opens it, repositories share it, the service commits

**Why:** a repository that commits its own write leaves the first write of a use case committed
when the second fails. The edge that receives the work — a request, a message — opens one
transaction per request or message it receives and closes it in an `async with`, which rolls back
whatever was not committed; the repositories are built on that transaction and never commit; the
service commits as its last step, so the use case decides its boundary and its return means
committed. A transaction kept past the request holds a pooled connection and serves what it read
earlier to the next one. `Transaction` is a `Protocol` with `commit` and `rollback`: the driver's
session or connection fits it as it is, and it cannot be made to inherit.

**Example:**
```python
# WRONG — each repository commits its own write: a failed seat reservation leaves a booking
@final
class TicketBooking:
    def __init__(self, *, bookings: BookingRepository, seats: SeatRepository) -> None:
        self._bookings = bookings
        self._seats = seats

    async def book(self, request: BookingRequest) -> BookingId:
        booking_id = await self._bookings.add_and_commit(Booking.create(request))
        await self._seats.reserve_and_commit(request.seat_ids)
        return booking_id


# CORRECT — both repositories write in the request's transaction, and the service commits it
@final
class TicketBooking:
    def __init__(
        self, *, bookings: BookingRepository, seats: SeatRepository, transaction: Transaction
    ) -> None:
        self._bookings = bookings
        self._seats = seats
        self._transaction = transaction

    async def book(self, request: BookingRequest) -> BookingId:
        booking_id = await self._bookings.add(Booking.create(request))
        await self._seats.reserve(request.seat_ids)
        await self._transaction.commit()
        return booking_id
```

### Nothing slow or irreversible runs before the commit

**Why:** a slow call holds row locks for its whole duration, and a rollback cannot unsend an email.
Side effects run after the commit; one that must be atomic with the data is an outbox row written in
the same transaction and published separately (the consuming side: `python-workers`).

**Example:**
```python
# WRONG — the mail server's latency holds row locks, and a rollback cannot unsend the email
@final
class TicketBooking:
    def __init__(
        self, *, bookings: BookingRepository, transaction: Transaction, mailer: Mailer
    ) -> None:
        self._bookings = bookings
        self._transaction = transaction
        self._mailer = mailer

    async def book(self, request: BookingRequest) -> BookingId:
        booking_id = await self._bookings.add(Booking.create(request))
        await self._mailer.send_confirmation(request.holder_email, booking_id)
        await self._transaction.commit()
        return booking_id


# CORRECT — the email goes after the commit, when the booking it confirms exists
@final
class TicketBooking:
    def __init__(
        self, *, bookings: BookingRepository, transaction: Transaction, mailer: Mailer
    ) -> None:
        self._bookings = bookings
        self._transaction = transaction
        self._mailer = mailer

    async def book(self, request: BookingRequest) -> BookingId:
        booking_id = await self._bookings.add(Booking.create(request))
        await self._transaction.commit()
        await self._mailer.send_confirmation(request.holder_email, booking_id)
        return booking_id
```

### A deadlock or serialization failure rolls back and re-runs the whole use case

**Why:** the database has already aborted the transaction, so retrying the statement inside it is
meaningless; the service rolls back and runs the use case again from the start, which is safe only
because side effects run after the commit. This is the one retry above the adapter
(`python-boundaries`). A serialization failure exists only under `REPEATABLE READ` or
`SERIALIZABLE` — under the default `READ COMMITTED` the second of two read-then-update transactions
overwrites the first without an error, and the retry never fires — so the edge opens the
transaction of a use case that relies on it at the stricter level.

**Example:**
```python
# WRONG — the failed statement is retried inside a transaction the database has already aborted
@final
class TicketBooking:
    def __init__(
        self,
        *,
        bookings: BookingRepository,
        seats: SeatRepository,
        transaction: Transaction,
        conflict_attempts: int = _CONFLICT_ATTEMPTS,
    ) -> None:
        self._bookings = bookings
        self._seats = seats
        self._transaction = transaction
        self._conflict_attempts = conflict_attempts

    async def book(self, request: BookingRequest) -> BookingId:
        for _ in range(self._conflict_attempts):
            try:
                booking_id = await self._bookings.add(Booking.create(request))
                break
            except ConcurrentUpdateError:
                continue
        await self._transaction.commit()
        return booking_id


# CORRECT — each attempt rolls back, then runs the whole use case and its commit again
@final
class TicketBooking:
    def __init__(
        self,
        *,
        bookings: BookingRepository,
        seats: SeatRepository,
        transaction: Transaction,
        conflict_attempts: int = _CONFLICT_ATTEMPTS,
    ) -> None:
        self._bookings = bookings
        self._seats = seats
        self._transaction = transaction
        self._conflict_attempts = conflict_attempts

    async def book(self, request: BookingRequest) -> BookingId:
        for _ in range(self._conflict_attempts):
            try:
                booking_id = await self._bookings.add(Booking.create(request))
                await self._seats.reserve(request.seat_ids)
                await self._transaction.commit()
            except ConcurrentUpdateError:
                await self._transaction.rollback()
                continue
            return booking_id
        raise BookingConflictError(request.event_id)
```

### Every database connection carries server-side timeouts

**Why:** `statement_timeout` bounds a query, `lock_timeout` a wait for a lock, and
`idle_in_transaction_session_timeout` a transaction the application opened and abandoned, which
otherwise holds its locks until someone kills it. They are set once — on the pool or the database
role — never per query by memory; the client-side half is in `python-boundaries`.

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
    def __init__(self, *, bookings: BookingRepository, holders: HolderRepository) -> None:
        self._bookings = bookings
        self._holders = holders

    async def holders_of(self, event_id: EventId) -> list[Holder]:
        bookings = await self._bookings.for_event(event_id)
        return [await self._holders.get(booking.holder_id) for booking in bookings]


# CORRECT — one query for the holders of every booking at once
@final
class TicketBooking:
    def __init__(self, *, bookings: BookingRepository, holders: HolderRepository) -> None:
        self._bookings = bookings
        self._holders = holders

    async def holders_of(self, event_id: EventId) -> list[Holder]:
        bookings = await self._bookings.for_event(event_id)
        return await self._holders.get_many([booking.holder_id for booking in bookings])
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

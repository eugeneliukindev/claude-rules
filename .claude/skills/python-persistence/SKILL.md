---
name: python-persistence
description: >-
  Library-agnostic Python persistence design: one use case per transaction, a Unit of Work owning
  the boundary, nothing slow or irreversible inside a transaction, ORM rows converted to domain
  objects at the repository boundary, N+1 treated as an error, keyset pagination instead of offset,
  optimistic locking with a version column. Use when deciding where a transaction begins and ends,
  designing a repository, paginating a query or guarding against lost updates, whatever the ORM;
  the SQLAlchemy API is in python-sqlalchemy, the asyncpg API in python-asyncpg, schema changes in
  python-migrations.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
---

# Persistence

These rules hold for any ORM or query builder. How to spell them in SQLAlchemy is in
`python-sqlalchemy`, in raw asyncpg in `python-asyncpg`; schema changes are `python-migrations`.

## Transactions and Unit of Work

- **One use case — one transaction.** The service method is the transaction boundary. Entry points
  do not manage transactions; repositories do not commit.

```python
# WRONG — each repository commits its own write: a failed reservation leaves an order without stock
def place_order(self, command: PlaceOrder) -> OrderId:
    order_id = self._orders.add(Order.create(command))
    self._stock.reserve(command.skus)
    return order_id

# CORRECT — the service opens one unit of work: both writes commit together or neither does
def place_order(self, command: PlaceOrder) -> OrderId:
    with self._unit_of_work() as unit:
        order_id = unit.orders.add(Order.create(command))
        unit.stock.reserve(command.skus)
    return order_id
```

- **The Unit of Work owns the transaction**: a context manager that opens the session, exposes the
  repositories bound to it, commits on clean exit, rolls back on exception, and closes the session
  with it. A session that outlives its unit of work serves stale rows to the next one.
- **Explicit is the default**: the `with` is written in the service — not a decorator, not
  middleware that silently wraps everything. Implicit transactions hide their boundary and make
  two-transaction use cases impossible to see.
- **Nothing slow or irreversible inside a transaction**: no HTTP calls, no message publishing, no
  mail while holding it. A slow call holds row locks for its whole duration, and a rollback cannot
  unsend an email. Side effects run after commit; if they must be atomic with the data, write an
  outbox row in the same transaction and publish separately; the consuming side is
  `python-workers`.

```python
# WRONG — the mail server's latency holds row locks, and a rollback cannot unsend the email
def place_order(self, command: PlaceOrder) -> OrderId:
    with self._unit_of_work() as unit:
        order_id = unit.orders.add(Order.create(command))
        self._mailer.send_confirmation(command.customer_email, order_id)
    return order_id

# CORRECT — the email goes after commit, when the order it confirms exists
def place_order(self, command: PlaceOrder) -> OrderId:
    with self._unit_of_work() as unit:
        order_id = unit.orders.add(Order.create(command))
    self._mailer.send_confirmation(command.customer_email, order_id)
    return order_id
```

- **Read-only paths don't open write transactions.**
- **Deadlocks and serialization failures are the one retry above the adapter.** The database has
  already rolled the transaction back, so retrying the failed statement inside it is meaningless:
  the retry wraps the whole unit of work and re-runs the use case from the start. That is safe
  only because side effects run after commit. Every other retry lives in the adapter, as the
  `python-boundaries` skill says.

```python
# WRONG — the retry runs inside a transaction the database has already rolled back
def place_order(self, command: PlaceOrder) -> OrderId:
    with self._unit_of_work() as unit:
        for attempt in _RETRY_ON_CONFLICT:
            with attempt:
                order_id = unit.orders.add(Order.create(command))
    return order_id

# CORRECT — each attempt opens a fresh unit of work and re-runs the use case from the start
def place_order(self, command: PlaceOrder) -> OrderId:
    for attempt in _RETRY_ON_CONFLICT:
        with attempt, self._unit_of_work() as unit:
            order_id = unit.orders.add(Order.create(command))
    return order_id
```

- **Domain objects do not hold sessions**; a detached entity passed outward never lazy-loads.

## Repositories and the Domain

- **ORM models are not domain models.** They map to tables and are converted to frozen domain
  objects at the repository boundary; domain code never imports the ORM. An ORM row handed to a
  service carries change tracking with it — an attribute set "just for this calculation" is
  written back at the next flush.

```python
# WRONG — the service gets a tracked row: any attribute it sets is written at the next flush
def find(self, order_id: OrderId) -> OrderRow | None:
    return self._session.get(OrderRow, order_id)

# CORRECT — the row stops at the repository; the service gets a frozen Order
def find(self, order_id: OrderId) -> Order | None:
    row = self._session.get(OrderRow, order_id)
    if row is None:
        return None
    return Order(id=OrderId(row.id), status=row.status, total=row.total)
```

- **Repositories accept and return domain objects** and contain query construction only — no
  business rules, no commits.
- **A rule computable from loaded data is a pure function over domain objects**; the service
  loads, calls it and saves what it returns. The rule is then tested with plain values and no fake,
  and the fakes are left to the few tests of the service that wires it — the useful half of
  "functional core, imperative shell", without a second architecture beside the contracts.
- **Every relationship is loaded explicitly.** Lazy loading is switched off so an N+1 is an error
  at the first test, not a page that quietly runs a hundred queries in production. The query
  states what it loads; design as if an unloaded access always raises.
- **An integration test pins the number of statements per use case.** Switching lazy loading off
  does not catch an explicit query inside a loop — a repository call per order is an N+1 the ORM
  never sees. A count asserted in the test fails the day it grows; how to count is in
  `python-sqlalchemy`. In GraphQL the client chooses the nesting, so every field that loads by key
  goes through a DataLoader built per request (`python-strawberry`).
- **Bulk operations are bulk**: one statement per batch, not one per row. Looping single-row
  writes over thousands of rows is a bug, not a style choice.
- **Pages are keyset, not offset.** `OFFSET 100000` reads and throws away a hundred thousand rows
  for every page, so the last page costs the most and the cost grows with the table — and a row
  inserted between two requests shifts every later page, showing one row twice or skipping one.
  Page from the last key the caller saw, with a unique tiebreaker and an index in exactly that
  order. Offset stays for a small, bounded list where jumping to page N is the feature.

```sql
-- WRONG — the database reads and discards every row before the page
SELECT id, created_at, total FROM orders ORDER BY created_at, id LIMIT 50 OFFSET 100000;

-- CORRECT — the index seeks straight to the last row the caller saw
SELECT id, created_at, total FROM orders
WHERE (created_at, id) > (:last_created_at, :last_id)
ORDER BY created_at, id LIMIT 50;
```

- **A read-modify-write is guarded by a version column.** Two requests that both read version 7
  both write, and the second silently erases the first. The update says
  `WHERE id = :id AND version = :read_version` and sets `version = version + 1`; zero rows updated
  is a conflict, raised as its own error and answered by re-reading — never retried blind, which
  is the lost update again. Row locks (`SELECT … FOR UPDATE`) are for short transactions that
  must not fail; the version column is for edits that span a user's think time.

```sql
-- WRONG — both requests read version 7, and the second write silently erases the first
UPDATE orders SET status = :status WHERE id = :id;

-- CORRECT — a stale version matches no row, and the caller raises zero rows as a conflict
UPDATE orders SET status = :status, version = version + 1
WHERE id = :id AND version = :read_version;
```

- **Column types are the specific ones**: timestamps with time zone, decimal for money, native UUID
  for ids — never a float for money, never text for typed data.
- **Indexes are part of the model** and are reviewed with the query that needs them, never added
  "just in case" — each one is paid for on every write.

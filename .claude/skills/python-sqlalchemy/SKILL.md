---
name: python-sqlalchemy
description: >-
  SQLAlchemy 2.0 practice: select() with session.execute() instead of the legacy Query, Mapped and
  mapped_column declarative models, relationships that raise on lazy access with explicit
  selectinload and joinedload, engine built once with pool_pre_ping, short-lived sessions and
  expire_on_commit, service-owned transaction boundaries, bulk writes and upserts, parameterized
  text() for raw SQL, and migration practice. Use when Python code imports sqlalchemy, defines a
  mapped model, writes a query or a repository, or edits an alembic revision.
---

# SQLAlchemy

Assumes 2.0 style.

## The 2.0 API — `Query` Is Legacy

`select()` with `session.execute(...)` is the API; the ORM `Query` object is documented in the
source as a legacy construct. One query style per codebase, and it is this one:

```python
# WRONG — legacy Query API
users = session.query(User).filter(User.is_active).all()

# CORRECT — 2.0 style
users = session.execute(
    select(User).where(User.is_active)
).scalars().all()
```

- **`.scalars()` when selecting whole entities**, or every row comes back as a one-element tuple.
- **`session.get(User, user_id)` for a primary-key lookup** — it checks the identity map first and
  skips the query when the object is already loaded.
- **`.scalar_one()` / `.scalar_one_or_none()` when exactly one row is the contract.** `.first()`
  hides a broken query behind a plausible answer; `scalar_one()` raises when the assumption breaks.

## Declarative Models

- **`Mapped[...]` and `mapped_column(...)`**, so the model is typed and the type checker sees the
  same shape the ORM does. A bare `Column` gives up both.
- **Optionality is in the annotation**: `Mapped[str]` is `NOT NULL`, `Mapped[str | None]` is
  nullable. Do not restate it with `nullable=` unless overriding.
- **Column types are the specific ones**: timezone-aware timestamps, `Numeric` for money — never
  `Float`, whose rounding is invisible until an invoice is wrong — and a native `UUID` for ids.
- **Indexes live on the model** and are reviewed with the query that needs them.
- **ORM models are not domain models.** They map to tables; the repository converts them to frozen
  domain objects at the boundary.

## Loading — Make N+1 Impossible, Not Unlikely

- **Set `lazy="raise"` on relationships.** Then an unloaded access is an immediate error naming the
  relationship, instead of a page that is quietly a hundred queries. This is the single highest-value
  setting in the library.
- **Load explicitly at the query**: `selectinload` for collections (a second `IN` query),
  `joinedload` for many-to-one (one join). `subqueryload` is the older shape and rarely the right
  answer now.
- **`contains_eager` when you have already joined** and want the ORM to populate from those columns
  rather than issuing another query.
- Async sessions raise on lazy access anyway — design as if they always do, and the sync path stays
  correct for free.

## Sessions and Transactions

- **The engine is built once** in the composition root: explicit pool size, `pool_pre_ping=True` to
  survive a database restart, and a statement timeout so one query cannot hold a connection forever.
- **Sessions are short-lived** and scoped to one unit of work. A session that outlives a request
  accumulates identity-map entries and stale objects.
- **`expire_on_commit=False`** for async and for any code that reads attributes after commit;
  otherwise the first attribute access after `commit()` triggers a refresh — which, on an async
  session, raises.
- **The service owns the transaction boundary**; repositories stage changes on the session they were
  given and never call `commit()`. One use-case, one commit.
- **`session.flush()` when you need the generated id inside the transaction** — not `commit()`,
  which ends it.
- **Nothing slow inside the transaction**: no HTTP, no publishing. Side effects go after commit, or
  into an outbox row written in the same transaction.

## Writing

- **Bulk operations are bulk**: one `insert().values([...])`, one `update().where(...)`. A loop of
  `session.add()` for thousands of rows is a bug, not a style choice.
- **Upsert through the dialect's `on_conflict_do_update`** rather than a select-then-insert race.
- **`returning()`** to get the written rows back in the same round trip.

## Raw SQL

- **`text()` with bound parameters, always.** Never an f-string into query text — including
  `ORDER BY` and table names, which are chosen from a whitelist of constants.
- Raw SQL is for reports and migrations. A raw query in a repository is a query the type checker
  cannot see.

## Migrations

- **Autogenerate, then read and edit.** It misses renames — emitting a drop plus a create, which
  loses the data — and it misses server defaults and constraint changes.
- **No ORM models inside a migration.** Use the migration DSL and inline table definitions, so a
  migration written today still runs after the model changes tomorrow.
- **One logical change per revision**, each with a working downgrade, each backward compatible with
  the currently deployed code.
- **Long locks are planned**: create indexes concurrently, batch backfills, change types via a new
  column.

---
name: python-persistence
description: >-
  Library-agnostic Python persistence design: one use case per transaction, a Unit of Work owning
  the boundary, nothing slow or irreversible inside a transaction, ORM rows converted to domain
  objects at the repository boundary, N+1 treated as an error, and migration discipline — working
  downgrades, separated backfills, planned long locks. Use when deciding where a transaction begins
  and ends, designing a repository, or planning a schema migration, whatever the ORM; the
  SQLAlchemy and alembic API is in python-sqlalchemy.
---

# Persistence

These rules hold for any ORM or query builder. How to spell them in SQLAlchemy and alembic is in
the `python-sqlalchemy` skill.

## Transactions and Unit of Work

- **One use case — one transaction.** The service method is the transaction boundary. Entry points
  do not manage transactions; repositories do not commit.
- **The Unit of Work owns the transaction**: a context manager that opens the session, exposes the
  repositories bound to it, commits on clean exit, rolls back on exception, and closes the session
  with it. A session that outlives its unit of work serves stale rows to the next one.
- **Explicit is the default**: the `with` is written in the service — not a decorator, not
  middleware that silently wraps everything. Implicit transactions hide their boundary and make
  two-transaction use cases impossible to see.
- **Nothing slow or irreversible inside a transaction**: no HTTP calls, no message publishing, no
  mail while holding it. A slow call holds row locks for its whole duration, and a rollback cannot
  unsend an email. Side effects run after commit; if they must be atomic with the data, write an
  outbox row in the same transaction and publish separately.
- **Read-only paths don't open write transactions.**
- **Deadlocks and serialization failures are the one retry above the adapter.** The database has
  already rolled the transaction back, so retrying the failed statement inside it is meaningless:
  the retry wraps the whole unit of work and re-runs the use case from the start. That is safe
  only because side effects run after commit. Every other retry lives in the adapter, as the
  `python-boundaries` skill says.
- **Domain objects do not hold sessions**; a detached entity passed outward never lazy-loads.

## Repositories and the Domain

- **ORM models are not domain models.** They map to tables and are converted to frozen domain
  objects at the repository boundary; domain code never imports the ORM. An ORM row handed to a
  service carries change tracking with it — an attribute set "just for this calculation" is
  written back at the next flush.
- **Repositories accept and return domain objects** and contain query construction only — no
  business rules, no commits.
- **Every relationship is loaded explicitly.** Lazy loading is switched off so an N+1 is an error
  at the first test, not a page that quietly runs a hundred queries in production. The query
  states what it loads; design as if an unloaded access always raises.
- **Bulk operations are bulk**: one statement per batch, not one per row. Looping single-row
  writes over thousands of rows is a bug, not a style choice.
- **Column types are the specific ones**: timestamps with time zone, decimal for money, native UUID
  for ids — never a float for money, never text for typed data.
- **Indexes are part of the model** and are reviewed with the query that needs them, never added
  "just in case" — each one is paid for on every write.

## Migrations

- **One migration per logical schema change**, with an imperative, specific message — not
  `update` or `fix`.
- **A generated migration is a draft, read and edited before it is committed.** A generator diffs
  shapes, not intent: a renamed column looks like a drop plus an add, and running that loses the
  column's data.
- **Every migration has a working downgrade**; an irreversible change is split so the destructive
  step is its own, clearly named revision.
- **Schema migrations never contain data migrations.** A backfill is a separate revision or a
  one-off script: batched, bounded, idempotent, re-runnable after failure.
- **Migrations are backward compatible with the deployed code** — expand, migrate, contract. A
  migration that breaks the running version is an outage.
- **No application models inside migrations**: a migration carries its own inline definition of
  the tables it touches, so a migration written today still runs after the model changes tomorrow.
- **The whole chain is exercised** against an empty database, up and back down, and drift between
  models and migrations fails the check.
- **Long locks are planned**: indexes built concurrently, backfills batched, a type changed by
  adding a new column rather than rewriting the old one in place.

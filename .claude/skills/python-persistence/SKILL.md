---
name: python-persistence
description: >-
  Python persistence discipline: one use-case one transaction, the Unit of Work owning the
  boundary, no slow or irreversible work inside a transaction, explicit relationship loading so
  N+1 is an error, ORM models converted to domain objects at the repository boundary, and
  migration practice including working downgrades, separated backfills and planned long locks. Use
  when touching a Python ORM, a transaction boundary, a repository or a database migration.
---

# Persistence

The library-specific companion is the `python-sqlalchemy` skill.

## Transactions and Unit of Work

- **One use-case — one transaction.** The service method is the transaction boundary. Entry points
  do not manage transactions; repositories do not commit.
- **The Unit of Work owns the transaction**: a context manager that opens the session, exposes the
  repositories bound to it, commits on clean exit and rolls back on exception.
- **Explicit is the default**: the `with` is written in the service — not a decorator, not
  middleware that silently wraps everything. Implicit transactions hide their boundary and make
  two-transaction use-cases impossible to see.
- **Nothing slow or irreversible inside a transaction**: no HTTP calls, no message publishing, no
  mail while holding it. Side effects run after commit; if they must be atomic with the data, write
  an outbox row in the same transaction and publish separately.
- **Read-only paths don't open write transactions.**
- **Retries wrap the whole unit of work.** The use-case must be re-runnable from the start, which
  it is when side effects are after-commit.
- **Domain objects do not hold sessions**; a detached entity passed outward never lazy-loads.

## Database Access

- **The engine is built once** in the composition root, with an explicit pool size, liveness check
  and statement timeout; sessions are short-lived and scoped to one unit of work.
- **Every relationship is loaded explicitly.** Lazy loading is disabled so an N+1 is an error, not
  a slow page. Design as if it always raises.
- **ORM models are not domain models.** They map to tables and are converted to frozen domain
  objects at the repository boundary. Domain code never imports the ORM.
- **Repositories return and accept domain objects**; they contain query construction only — no
  business rules, no commits.
- **Bulk operations are bulk.** Looping single-row writes for thousands of rows is a bug.
- **Raw SQL is parameterized, always**, and is reserved for reports and migrations.
- **Column types are the specific ones**: timestamps with time zone, decimal for money, native UUID
  for ids — never a float for money, never text for typed data.
- **Indexes are part of the model** and are reviewed with the query that needs them, never added
  "just in case".

## Migrations

- **One migration per logical schema change**, generated and then **read and edited** —
  autogeneration misses renames (emitting a drop plus a create, which loses the data), server
  defaults, and constraint changes.
- **Every migration has a working downgrade**; an irreversible change is split so the destructive
  step is its own, clearly named revision.
- **Schema migrations never contain data migrations.** A backfill is a separate revision or a
  one-off script: batched, bounded, idempotent, re-runnable after failure.
- **Migrations are backward compatible with the deployed code** — expand, migrate, contract. A
  migration that breaks the running version is an outage.
- **Revision messages are imperative and specific**, not `update` or `fix`.
- **No ORM models inside migrations**: use the migration DSL and inline table definitions, so a
  migration written today still runs after the model changes tomorrow.
- **The whole chain is exercised** against an empty database, up and back down, and a drift between
  models and migrations is a failure.
- **Long locks are planned**: concurrent index creation, batched backfills, type changes via a new
  column.

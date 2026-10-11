---
name: python-migrations
description: >-
  Library-agnostic schema migration discipline: one migration per logical change, a generated
  migration read as a draft, a working downgrade with the destructive step in its own revision,
  backfills kept out of schema migrations and batched, expand-migrate-contract against the deployed
  code, inline table definitions instead of application models, the whole chain exercised, and
  locks — lock_timeout, CONCURRENTLY, NOT VALID then VALIDATE, volatile defaults, enum values, one
  runner. Use when planning or reviewing a schema migration, planning a backfill or a column
  change, whatever the tool; the alembic mechanics are in python-alembic, the backfill script
  itself in python-scripts.
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/alembic.ini"
---

# Migrations

These rules hold for any migration tool. How alembic spells them is in `python-alembic`.

- **One migration per logical schema change**, with an imperative, specific message — not
  `update` or `fix`.
- **A generated migration is a draft, read and edited before it is committed.** A generator diffs
  shapes, not intent: a renamed column looks like a drop plus an add, and running that loses the
  column's data.
- **Every migration has a working downgrade**; an irreversible change is split so the destructive
  step is its own, clearly named revision.
- **Schema migrations never contain data migrations.** A backfill is a separate revision or a
  one-off script: batched, bounded, idempotent, re-runnable after failure.

```sql
-- WRONG — one statement holds a lock on every row it touches until the last one is written
UPDATE orders SET currency = 'EUR' WHERE currency IS NULL;

-- CORRECT — one bounded batch per transaction, repeated until it updates nothing; a rerun resumes
UPDATE orders SET currency = 'EUR'
WHERE id IN (SELECT id FROM orders WHERE currency IS NULL ORDER BY id LIMIT 1000);
```

- **Migrations are backward compatible with the deployed code** — expand, migrate, contract. A
  migration that breaks the running version is an outage.

```sql
-- WRONG — one release renames the column, and the code still running queries a name that is gone
ALTER TABLE users RENAME COLUMN name TO full_name;

-- CORRECT — three releases, each one survived by the code already deployed
ALTER TABLE users ADD COLUMN full_name TEXT;
-- next release writes both columns, and a backfill copies the old rows in batches, as above:
UPDATE users SET full_name = name
WHERE id IN (SELECT id FROM users WHERE full_name IS NULL ORDER BY id LIMIT 1000);
-- once no deployed code reads the old column:
ALTER TABLE users DROP COLUMN name;
```

- **No application models inside migrations**: a migration carries its own inline definition of
  the tables it touches, so a migration written today still runs after the model changes tomorrow.
- **The whole chain is exercised** against an empty database, up and back down, and drift between
  models and migrations fails the check.
- **Migrations run once per deploy, as a step of their own, never at application or container
  start** — how, from the release's image, is in `python-container`.
## Locks

Measured on PostgreSQL 17; other databases differ in the details, not in the danger.

- **Every DDL statement runs under `SET lock_timeout`.** An `ALTER TABLE` needs an exclusive lock,
  waits behind any open transaction that touched the table, and every query that arrives after it
  queues behind *it* — a plain `SELECT` waited until its own two-second timeout. With a lock
  timeout the migration fails in moments and is retried; without one it takes the table down.

```sql
-- WRONG — waits behind a long transaction, and every read of orders queues behind the ALTER
ALTER TABLE orders ADD COLUMN note TEXT;

-- CORRECT — gives up after two seconds instead of blocking the table; the deploy retries it
SET lock_timeout = '2s';
ALTER TABLE orders ADD COLUMN note TEXT;
```

- **An index on a live table is built `CONCURRENTLY`, outside a transaction** —
  `CREATE INDEX CONCURRENTLY cannot run inside a transaction block` otherwise; how a revision
  steps out of its transaction is `python-alembic`'s `autocommit_block`.
- **A constraint on existing rows is added `NOT VALID`, then validated.** The first statement
  takes a brief lock and checks new rows only; `VALIDATE CONSTRAINT` scans without blocking writes.
  `SET NOT NULL` after a validated `CHECK (column IS NOT NULL)` skips its own full scan.

```sql
-- WRONG — scans every row under a lock that blocks all writes until the scan ends
ALTER TABLE orders ALTER COLUMN currency SET NOT NULL;

-- CORRECT — a quick NOT VALID constraint, a validation that lets writes through, then the flag
ALTER TABLE orders ADD CONSTRAINT orders_currency_not_null CHECK (currency IS NOT NULL) NOT VALID;
ALTER TABLE orders VALIDATE CONSTRAINT orders_currency_not_null;
ALTER TABLE orders ALTER COLUMN currency SET NOT NULL;
```

- **A volatile default rewrites the table.** `ADD COLUMN … DEFAULT now()` is instant; `DEFAULT
  gen_random_uuid()` rewrote every row under an exclusive lock. Add the column without the
  default, set the default, then backfill in batches.
- **A type changes by adding a new column**, never by rewriting the old one in place.
- **A new enum value is added in one revision and used in the next.** `ALTER TYPE … ADD VALUE`
  runs inside a transaction, but the value cannot be used before that transaction commits —
  `unsafe use of new value` — so a backfill that writes it is a revision of its own.
- **One process runs the migrations.** Two replicas that each upgrade on deploy race on the
  version table; the deploy step runs once (`python-container`), or the runner takes an advisory
  lock first.

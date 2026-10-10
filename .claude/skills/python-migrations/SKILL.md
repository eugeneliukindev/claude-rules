---
name: python-migrations
description: >-
  Library-agnostic schema migration discipline: one migration per logical change, a generated
  migration read as a draft, a working downgrade with the destructive step in its own revision,
  backfills kept out of schema migrations, expand-migrate-contract against the deployed code, inline
  table definitions instead of application models, the whole chain exercised, long locks planned.
  Use when planning or reviewing a schema migration, a backfill or a column change, whatever the
  tool; the alembic mechanics are in python-alembic.
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
-- next release writes both columns while a batched backfill copies the old rows:
UPDATE users SET full_name = name WHERE full_name IS NULL;
-- once no deployed code reads the old column:
ALTER TABLE users DROP COLUMN name;
```

- **No application models inside migrations**: a migration carries its own inline definition of
  the tables it touches, so a migration written today still runs after the model changes tomorrow.
- **The whole chain is exercised** against an empty database, up and back down, and drift between
  models and migrations fails the check.
- **Migrations run once per deploy, as a step of their own, never at application or container
  start** — how, from the release's image, is in `python-container`.
- **Long locks are planned**: indexes built concurrently, backfills batched, a type changed by
  adding a new column rather than rewriting the old one in place.

---
name: python-migrations
description: >-
  Plans schema migrations whatever the tool: one change per migration, working downgrades,
  backfills kept apart, expand-migrate-contract, locks. Use when planning or reviewing a schema
  change, a column change or a backfill. Not for alembic's commands (python-alembic).
paths:
  - "**/*.py"
  - "**/pyproject.toml"
  - "**/alembic.ini"
---

# Migrations

These rules hold for any migration tool. How alembic spells them is `python-alembic`; the deploy
step that runs them from the release's image is `python-container`; the backfill script itself is
`python-scripts`.

## Revisions

### A generated migration is a draft, read and edited before it is committed

**Why:** a generator diffs shapes, not intent — a renamed column looks like a drop plus an add, and
running that loses the column's data. One migration holds one logical change, with an imperative,
specific message, never `update` or `fix`.

### Every migration has a working downgrade, and a destructive step is a revision of its own

**Why:** a downgrade nobody ran fails on the night it is needed; the whole chain is exercised
against an empty database, up and back down, and drift between the models and the migrations fails
the check. A step that loses data cannot be undone, so it stands alone and is named for what it
destroys — the revisions around it stay reversible.

**Example:**
```sql
-- WRONG — one revision adds the new column and drops the old: its downgrade cannot restore the data
ALTER TABLE episodes ADD COLUMN duration_seconds INTEGER;
ALTER TABLE episodes DROP COLUMN duration_text;

-- CORRECT — the additive revision reverses cleanly; the drop is a later, separately named revision
-- upgrade
ALTER TABLE episodes ADD COLUMN duration_seconds INTEGER;
-- downgrade
ALTER TABLE episodes DROP COLUMN duration_seconds;
```

### A backfill is not in a schema migration; it runs in bounded, idempotent batches

**Why:** one `UPDATE` over a large table holds a lock on every row it touches until the last one
is written. A backfill is a separate revision or a one-off script: batched, bounded, idempotent,
re-runnable after a failure. A migration carries its own definition of the tables it touches,
never the application's models, so a migration written today still runs after the models change.

**Example:**
```sql
-- WRONG — one statement locks every row it touches until the last one is written
UPDATE episodes SET language = 'en' WHERE language IS NULL;

-- CORRECT — one bounded batch per transaction, repeated until it updates nothing; a rerun resumes
UPDATE episodes SET language = 'en'
WHERE id IN (SELECT id FROM episodes WHERE language IS NULL ORDER BY id LIMIT 1000);
```

### A migration is compatible with the code already deployed: expand, migrate, contract

**Why:** during a rolling deploy the old version runs against the new schema; a migration that
breaks it is an outage. A rename becomes three releases, each survived by the code already running.

**Example:**
```sql
-- WRONG — one release renames the column, and the code still running queries a name that is gone
ALTER TABLE shows RENAME COLUMN name TO display_title;

-- CORRECT — expand, then a release that writes both and a batched backfill, then contract
ALTER TABLE shows ADD COLUMN display_title TEXT;
UPDATE shows SET display_title = name
WHERE id IN (SELECT id FROM shows WHERE display_title IS NULL ORDER BY id LIMIT 1000);
ALTER TABLE shows DROP COLUMN name;
```

### Migrations run once per deploy, by one process, never at application start

**Why:** two replicas that each upgrade on start race on the version table, and a slow migration
holds every replica's startup behind it. The deploy runs one migration step before the new version
starts — or the runner takes an advisory lock first.

## Locks

**Before writing DDL for a table that is live — a column, an index, a constraint, a default, a
type or an enum value — read [locks.md](locks.md)** — `lock_timeout` on every statement,
`CONCURRENTLY`, `NOT VALID` then `VALIDATE`, volatile defaults, a type changed through a new column,
enum values used a revision later.

- Every DDL statement runs under `SET lock_timeout`
- An index on a live table is built `CONCURRENTLY`, outside a transaction
- A constraint on existing rows is added `NOT VALID`, then validated
- A volatile default, a type change and a new enum value each take an extra step

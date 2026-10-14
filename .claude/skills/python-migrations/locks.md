# Locks

## Contents

- `lock_timeout` on every DDL statement
- An index built `CONCURRENTLY`
- A constraint added `NOT VALID`, then validated
- A volatile default, a type change, a new enum value

Measured on PostgreSQL 17; other databases differ in the details, not in the danger.

### Every DDL statement runs under `SET lock_timeout`

**Why:** an `ALTER TABLE` needs an exclusive lock, waits behind any open transaction that touched
the table, and every query that arrives after it queues behind *it* — a plain `SELECT` waited until
its own two-second timeout. With a lock timeout the migration fails in moments and is retried;
without one it takes the table down.

**Example:**
```sql
-- WRONG — waits behind a long transaction, and every read of episodes queues behind the ALTER
ALTER TABLE episodes ADD COLUMN transcript_url TEXT;

-- CORRECT — gives up after two seconds instead of blocking the table; the deploy retries it
SET lock_timeout = '2s';
ALTER TABLE episodes ADD COLUMN transcript_url TEXT;
```

### An index on a live table is built `CONCURRENTLY`, outside a transaction

**Why:** a plain `CREATE INDEX` blocks writes to the table for the whole build. `CONCURRENTLY` lets
them through, and cannot run inside a transaction block — so the revision steps out of its own.

**Example:**
```sql
-- WRONG — writes to episodes wait until the index is built
CREATE INDEX episodes_show_id_idx ON episodes (show_id);

-- CORRECT — writes continue during the build; the statement runs outside a transaction
CREATE INDEX CONCURRENTLY episodes_show_id_idx ON episodes (show_id);
```

### A constraint on existing rows is added `NOT VALID`, then validated

**Why:** the first statement takes a brief lock and checks new rows only; `VALIDATE CONSTRAINT`
scans without blocking writes. `SET NOT NULL` after a validated `CHECK (column IS NOT NULL)` skips
its own full scan.

**Example:**
```sql
-- WRONG — scans every row under a lock that blocks all writes until the scan ends
ALTER TABLE episodes ALTER COLUMN show_id SET NOT NULL;

-- CORRECT — a quick NOT VALID constraint, a validation that lets writes through, then the flag
ALTER TABLE episodes ADD CONSTRAINT episodes_show_id_not_null
    CHECK (show_id IS NOT NULL) NOT VALID;
ALTER TABLE episodes VALIDATE CONSTRAINT episodes_show_id_not_null;
ALTER TABLE episodes ALTER COLUMN show_id SET NOT NULL;
```

### A volatile default, a type change and a new enum value each take an extra step

**Why:** `ADD COLUMN … DEFAULT now()` is instant, but `DEFAULT gen_random_uuid()` rewrote every row
under an exclusive lock — so the column is added without it, the default set after, and old rows
backfilled in batches. A type changes through a new column, never by rewriting the old one in
place. `ALTER TYPE … ADD VALUE` runs inside a transaction, but the value cannot be used before that
transaction commits — `unsafe use of new value` — so the backfill that writes it is the next
revision.

**Example:**
```sql
-- WRONG — a volatile default rewrites the whole table under an exclusive lock
ALTER TABLE episodes ADD COLUMN public_id UUID NOT NULL DEFAULT gen_random_uuid();

-- CORRECT — instant add, the default for new rows, then the old rows in batches
ALTER TABLE episodes ADD COLUMN public_id UUID;
ALTER TABLE episodes ALTER COLUMN public_id SET DEFAULT gen_random_uuid();
UPDATE episodes SET public_id = gen_random_uuid()
WHERE id IN (SELECT id FROM episodes WHERE public_id IS NULL ORDER BY id LIMIT 1000);
```

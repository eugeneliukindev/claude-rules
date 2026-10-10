---
name: go-migrations
description: >-
  Go schema migration discipline: a working down tested up-down-up in CI, schema and data migrated
  separately with resumable batched backfills, expand then contract across deploys, long locks
  planned, the migration tool pinned as a tool directive in go.mod and run as a deploy step rather
  than at application startup. Use when planning or reviewing a schema migration, a backfill, a
  column rename, or wiring a migration tool into a Go project.
paths:
  - "**/*.go"
  - "**/go.mod"
---

# Migrations

Transactions and repositories are `go-persistence`; this file is how the schema changes under them.

- **Every migration has a working down**, tested by running up, down and up again in CI. A down
  that was never run is a down that does not work.
- **Schema and data migrate separately.** A backfill over a large table runs in batches, outside
  the schema migration's transaction, and can be resumed.

  ```go
  // WRONG — one statement is one transaction: a failure near the end rolls back every row
  func backfillTotalCents(ctx context.Context, db *sql.DB) error {
  	_, err := db.ExecContext(ctx, `
  		UPDATE orders SET total_cents = round(total * 100)
  		WHERE total_cents IS NULL AND total IS NOT NULL`)
  	if err != nil {
  		return fmt.Errorf("backfill total_cents: %w", err)
  	}
  	return nil
  }

  // CORRECT — each batch commits alone, and a restart picks up the rows still NULL
  func backfillTotalCents(ctx context.Context, db *sql.DB) error {
  	for {
  		result, err := db.ExecContext(ctx, `
  			UPDATE orders SET total_cents = round(total * 100)
  			WHERE id IN (SELECT id FROM orders
  				WHERE total_cents IS NULL AND total IS NOT NULL LIMIT $1)`, backfillBatchRows)
  		if err != nil {
  			return fmt.Errorf("backfill total_cents: %w", err)
  		}
  		updated, err := result.RowsAffected()
  		if err != nil {
  			return fmt.Errorf("backfill total_cents: %w", err)
  		}
  		if updated == 0 {
  			return nil
  		}
  	}
  }
  ```

  The `total IS NOT NULL` is what ends the loop: a row the update cannot fill would otherwise be
  selected again on every batch.
- **Expand, then contract.** A rename is: add the new column, write both, backfill, read the new
  one, stop writing the old one, drop it — each a separate deploy. A migration that breaks the
  previous release's queries breaks the rollout, because both run at once.

  ```sql
  -- WRONG — one migration: the previous release, still serving during the rollout, selects name
  ALTER TABLE users RENAME COLUMN name TO full_name;

  -- CORRECT — one step per deploy, each compatible with the release before it
  ALTER TABLE users ADD COLUMN full_name text;  -- deploy 1; the code writes both columns
                                                -- deploy 2: backfill, then read full_name
                                                -- deploy 3: the code stops writing name
  ALTER TABLE users DROP COLUMN name;           -- deploy 4
  ```
- **Long locks are planned.** An index on a large table is built concurrently where the database
  supports it; a `NOT NULL` on a populated column is added as a validated constraint first. The
  migration says how long it holds which lock.

  ```sql
  -- WRONG — both scan the whole table while holding a lock that blocks its writes
  CREATE INDEX orders_customer_id_idx ON orders (customer_id);
  ALTER TABLE orders ALTER COLUMN customer_id SET NOT NULL;

  -- CORRECT (PostgreSQL 12+) — the scans run under locks that let reads and writes through
  CREATE INDEX CONCURRENTLY orders_customer_id_idx ON orders (customer_id);  -- not in a transaction
  ALTER TABLE orders ADD CONSTRAINT orders_customer_id_not_null
      CHECK (customer_id IS NOT NULL) NOT VALID;          -- ACCESS EXCLUSIVE, no scan
  ALTER TABLE orders VALIDATE CONSTRAINT orders_customer_id_not_null;  -- SHARE UPDATE EXCLUSIVE
  ALTER TABLE orders ALTER COLUMN customer_id SET NOT NULL;  -- the constraint proves it: no scan
  ALTER TABLE orders DROP CONSTRAINT orders_customer_id_not_null;
  ```
- **The migration tool is a `tool` directive in `go.mod`**, so every developer and CI run the same
  version — and migrations run as a deploy step, never from the application's own startup.

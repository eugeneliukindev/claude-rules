---
name: go-persistence
description: >-
  Go persistence with database/sql or a driver-native pool: one use case per transaction, a
  WithinTx helper owning commit and rollback, nothing slow or irreversible inside a transaction,
  rows scanned into domain types at the repository boundary, rows.Close and rows.Err, N+1 treated
  as an error, nullable columns, pool settings, and migration discipline — working downgrades,
  separated backfills, planned long locks. Use when Go code imports database/sql or a SQL driver,
  opens a transaction, writes a repository, scans rows, or plans a schema migration.
---

# Persistence

The design is library-agnostic; the code below uses `database/sql`. With pgx's native pool the
same rules are carried out as `go-pgx` describes.

## Transactions

**One use case, one transaction, and the use case decides where it begins.** A repository method
never commits — it does not know whether it is the whole operation or one step of three. The
service that implements the use case owns the boundary.

```go
// WithinTx runs fn in a transaction, committing if fn returns nil and rolling back otherwise.
func (s *Store) WithinTx(ctx context.Context, fn func(tx *sql.Tx) error) (err error) {
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return fmt.Errorf("begin transaction: %w", err)
	}
	defer func() {
		if rollbackErr := tx.Rollback(); !errors.Is(rollbackErr, sql.ErrTxDone) {
			err = errors.Join(err, rollbackErr)
		}
	}()

	if err := fn(tx); err != nil {
		return err
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("commit transaction: %w", err)
	}
	return nil
}
```

The deferred `Rollback` runs on every path — a panic in `fn` included, which a server recovers
from while the connection would otherwise stay checked out — and is a no-op returning
`sql.ErrTxDone` after a successful `Commit`.

- **The commit error is the result.** A transaction whose `Commit` failed did not happen, however
  well everything before it went.
- **Nothing slow or irreversible inside a transaction**: no HTTP call, no message published, no
  email. A lock held across a network call is held for that call's timeout, and a message
  published before a rollback announces something that never happened. Publish after the commit —
  or write an outbox row in the same transaction and let a relay send it.
- **A deadlock or serialization failure retries the whole use case**, from `BeginTx`, with a small
  bounded budget — never one statement inside the failed transaction, which the database has
  already aborted. The driver's error code says which failures are retryable.
- **Every query takes the `ctx`** — `QueryContext`, `ExecContext`, `QueryRowContext`. The forms
  without it ignore the request's deadline and cancellation; `noctx` reports them.

## Repositories and the Domain

- **A repository speaks domain types**: `Find(ctx, id OrderID) (Order, error)`, `Save(ctx, Order)
  error`. The row shape, the SQL and the driver's errors stay inside it; `sql.ErrNoRows` becomes the
  package's `ErrNotFound`, a unique violation becomes `ErrAlreadyExists`.
- **A repository method that must join a caller's transaction takes the executor**: an interface
  with `ExecContext`, `QueryContext` and `QueryRowContext`, satisfied by both `*sql.DB` and
  `*sql.Tx`.
- **Scan into a row struct, then convert** — the conversion validates and is where a corrupt row is
  reported with its key, instead of a domain object built half-right.
- **`rows.Close` deferred, and `rows.Err` checked after the loop.** A loop that ends early because
  the connection dropped looks exactly like one that ran out of rows until `Err` is read;
  `sqlclosecheck` and `rowserrcheck` catch both.
- **Name the columns.** `SELECT *` breaks every `Scan` the day a column is added, in the order the
  database chooses.
- **Nullable columns** scan into `sql.Null[T]` in the row struct and become a domain zero value, a
  `(T, bool)`, or an error during conversion — a pointer does not leak into the domain.
- **N+1 is an error, not a performance tweak.** A query inside a loop over the results of another
  query is one `JOIN` or one `WHERE id = ANY($1)`; the loop's length is the page size today and the
  table size next year.
- **Every list query has a `LIMIT`**, and pagination is keyset (`WHERE (created_at, id) > ($1, $2)`)
  wherever the table grows — `OFFSET` reads and discards every skipped row.

```go
// WRONG — one query for the page, then one more per order: 51 round trips for 50 orders
func (r *Repository) Recent(ctx context.Context, limit int) ([]Order, error) {
	rows, err := r.db.QueryContext(ctx, selectRecentOrders, limit)
	if err != nil {
		return nil, fmt.Errorf("query recent orders: %w", err)
	}
	defer rows.Close()

	var orders []Order
	for rows.Next() {
		var row orderRow
		if err := rows.Scan(&row.id, &row.customerID, &row.createdAt); err != nil {
			return nil, fmt.Errorf("scan order: %w", err)
		}
		order, err := row.toOrder()
		if err != nil {
			return nil, err
		}
		if order.Lines, err = r.lines(ctx, order.ID); err != nil {
			return nil, fmt.Errorf("load lines of order %s: %w", order.ID, err)
		}
		orders = append(orders, order)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read recent orders: %w", err)
	}
	return orders, nil
}

// CORRECT — one round trip: the page and its lines joined, grouped while scanning
func (r *Repository) Recent(ctx context.Context, limit int) ([]Order, error) {
	rows, err := r.db.QueryContext(ctx, selectRecentOrdersWithLines, limit)
	if err != nil {
		return nil, fmt.Errorf("query recent orders: %w", err)
	}
	defer rows.Close()

	var orders []Order
	for rows.Next() {
		var row orderLineRow
		if err := rows.Scan(&row.id, &row.customerID, &row.createdAt, &row.sku, &row.quantity); err != nil {
			return nil, fmt.Errorf("scan order line: %w", err)
		}
		order, line, err := row.toDomain()
		if err != nil {
			return nil, err
		}
		if len(orders) == 0 || orders[len(orders)-1].ID != order.ID {
			orders = append(orders, order)
		}
		current := &orders[len(orders)-1]
		current.Lines = append(current.Lines, line)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("read recent orders: %w", err)
	}
	return orders, nil
}
```

`selectRecentOrdersWithLines` limits the orders in a subquery and joins their lines outside it,
ordered by order — a `LIMIT` on the joined rows would cut an order's lines in half. An order with
no lines needs a `LEFT JOIN` and `sql.Null` fields in the row.

## Pool

- **One `*sql.DB` per database for the life of the process**, opened in the composition root and
  passed down. It is a pool, safe for concurrent use; opening one per request exhausts the server.
- **Set the limits explicitly** — `SetMaxOpenConns`, `SetMaxIdleConns`, `SetConnMaxLifetime` —
  against the server's connection limit divided by the replicas. The default of unlimited open
  connections becomes a connection storm during the first traffic spike.
- **`db.PingContext` at startup with a deadline**, so a wrong DSN fails the deploy instead of the
  first request.

## Migrations

- **Every migration has a working down**, tested by running up, down and up again in CI. A down
  that was never run is a down that does not work.
- **Schema and data migrate separately.** A backfill over a large table runs in batches, outside
  the schema migration's transaction, and can be resumed.
- **Expand, then contract.** A rename is: add the new column, write both, backfill, read the new
  one, stop writing the old one, drop it — each a separate deploy. A migration that breaks the
  previous release's queries breaks the rollout, because both run at once.
- **Long locks are planned.** An index on a large table is built concurrently where the database
  supports it; a `NOT NULL` on a populated column is added as a validated constraint first. The
  migration says how long it holds which lock.
- **The migration tool is a `tool` directive in `go.mod`**, so every developer and CI run the same
  version — and migrations run as a deploy step, never from the application's own startup.

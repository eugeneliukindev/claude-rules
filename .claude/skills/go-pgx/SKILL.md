---
name: go-pgx
description: >-
  pgx v5 practice for PostgreSQL: one pgxpool.Pool with explicit limits owned by the composition
  root, transactions through pgx.BeginFunc because pgx never rolls back on context cancellation,
  CollectRows and RowToStructByName instead of hand-written scan loops, pgx.ErrNoRows translated
  at the repository, PgError codes via pgerrcode, ANY($1) with a slice instead of N+1, Batch and
  CopyFrom for bulk work, PgBouncer and the query exec mode, and the stdlib adapter for libraries
  that need *sql.DB. Use when Go code imports github.com/jackc/pgx/v5, pgxpool, pgconn or pgtype.
paths:
  - "**/*.go"
  - "**/go.mod"
---

# pgx

Checked against pgx v5.11.0. Transaction boundaries, repositories and N+1 are designed in
`go-persistence`, schema changes in `go-migrations`; this is how pgx carries them out.

## Native Interface or `database/sql`

**The native interface — `pgxpool.Pool` — for an application that talks only to PostgreSQL.** It
is faster, supports `COPY`, batches, arrays and `LISTEN`, and every method takes a `ctx`; there is
no context-free variant to call by mistake. **`github.com/jackc/pgx/v5/stdlib`** registers pgx as a
`database/sql` driver for the library that insists on a `*sql.DB` — a migration tool, a generic
SQL package — and only for it.

## The Pool

```go
config, err := pgxpool.ParseConfig(settings.databaseURL)
if err != nil {
	return fmt.Errorf("parse database url: %w", err)
}
config.MaxConns = settings.databaseMaxConns
config.MaxConnLifetime = 30 * time.Minute
config.MaxConnIdleTime = 5 * time.Minute

pool, err := pgxpool.NewWithConfig(ctx, config)
if err != nil {
	return fmt.Errorf("create database pool: %w", err)
}
defer pool.Close()

pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
defer cancel()
if err := pool.Ping(pingCtx); err != nil {
	return fmt.Errorf("ping database: %w", err)
}
```

- **One pool per database, built in the composition root**, passed down, and closed there —
  `Close` returns nothing and blocks until every connection is back.
- **`MaxConns` is set, not left at its default** of the larger of 4 and the CPU count, which has
  nothing to do with the server's `max_connections` divided by the replicas.
- **The pool connects lazily**: `NewWithConfig` succeeds against an unreachable server, so `Ping`
  with a deadline is what fails the deploy instead of the first request.
- **Behind PgBouncer in transaction mode**, pgx's default named prepared statements need
  PgBouncer 1.21+ with `max_prepared_statements` above zero; otherwise set
  `config.ConnConfig.DefaultQueryExecMode = pgx.QueryExecModeExec`. Getting this wrong shows as
  prepared-statement errors under load, when PgBouncer hands one session's statements to another
  connection — never in development, where there is no PgBouncer.

## Reading Rows

**`pgx.CollectRows` with a row-mapping function replaces the hand-written loop** — it closes the
rows and returns `rows.Err()`, the two things the loop forgets:

```go
type orderRow struct {
	ID         string    `db:"id"`
	CustomerID string    `db:"customer_id"`
	CreatedAt  time.Time `db:"created_at"`
}

func (r *Repository) Recent(ctx context.Context, limit int) ([]Order, error) {
	rows, err := r.db.Query(ctx, selectRecentOrders, limit)
	if err != nil {
		return nil, fmt.Errorf("query recent orders: %w", err)
	}
	orderRows, err := pgx.CollectRows(rows, pgx.RowToStructByName[orderRow])
	if err != nil {
		return nil, fmt.Errorf("read recent orders: %w", err)
	}
	return toOrders(orderRows)
}
```

- **The row struct is unexported, its fields exported** — `RowToStructByName` sets them by
  reflection, the carve-out `packages.md` names. Every field has a `db` tag, so renaming a Go field
  never renames the column it reads. The struct must have exactly the columns the query returns;
  `RowToStructByNameLax` allows extra fields, which hides a column dropped from the query.
- **`CollectOneRow` for a lookup** returns `pgx.ErrNoRows` when there is none; `CollectExactlyOneRow`
  also fails on a second row. `QueryRow(…).Scan(…)` is the same for a single row read into
  variables.
- **`pgx.ErrNoRows` is translated in the repository** — `errors.Is(err, pgx.ErrNoRows)` becomes the
  package's `ErrNotFound`. (It also matches `sql.ErrNoRows`, so code shared with `database/sql`
  can test either.)
- **A nullable column scans into a pointer** — `*string`, `*time.Time` — or a `pgtype` value, in
  the row struct only; the conversion decides what absence means in the domain.
- **Money and `numeric` never pass through `float64`**: scan into integer minor units or into a
  `pgtype.Numeric`, and convert in the row's conversion (`go-boundaries`).

## Writing and Errors

- **`Exec` returns a `pgconn.CommandTag`**: an `UPDATE` or `DELETE` that matched nothing is
  `tag.RowsAffected() == 0`, and the repository turns that into `ErrNotFound` — PostgreSQL does not
  report it as an error.

```go
// WRONG — an UPDATE that matched nothing is no error to PostgreSQL: a missing order "succeeds"
_, err := r.db.Exec(ctx, updateOrderStatus, id, status)
if err != nil {
	return fmt.Errorf("set status of order %s: %w", id, err)
}
return nil

// CORRECT — zero rows affected is this package's ErrNotFound
tag, err := r.db.Exec(ctx, updateOrderStatus, id, status)
if err != nil {
	return fmt.Errorf("set status of order %s: %w", id, err)
}
if tag.RowsAffected() == 0 {
	return fmt.Errorf("set status of order %s: %w", id, ErrNotFound)
}
return nil
```

- **Constraint violations are recognised by code, not by message.** `pgErr.ConstraintName` says
  which constraint, when a table has more than one. `github.com/jackc/pgerrcode` names every code;
  a literal `"23505"` is a magic string.

```go
// WRONG — the message is for people: lc_messages translates it, and new versions reword it
if err != nil && strings.Contains(err.Error(), "duplicate key") {
	return fmt.Errorf("create user %s: %w", email, ErrEmailTaken)
}

// CORRECT — the SQLSTATE code is the contract
if pgErr, ok := errors.AsType[*pgconn.PgError](err); ok && pgErr.Code == pgerrcode.UniqueViolation {
	return fmt.Errorf("create user %s: %w", email, ErrEmailTaken)
}
```

- **Arguments are always `$n` parameters** — values never formatted into the SQL (`go-security`).
  A list is one parameter: `WHERE id = ANY($1)` with a Go slice, which is also the fix for N+1.
  `pgx.NamedArgs{"status": s}` with `@status` in the SQL when a statement has many parameters.

```go
// WRONG — the IDs are formatted into the SQL: an injection, and a new statement per list length
query := "SELECT id, status FROM orders WHERE id IN ('" + strings.Join(ids, "', '") + "')"
rows, err := r.db.Query(ctx, query)

// CORRECT — the whole slice is one parameter
rows, err := r.db.Query(ctx, "SELECT id, status FROM orders WHERE id = ANY($1)", ids)
```

## Transactions

**pgx does not roll back when the context is cancelled.** Unlike `database/sql`, the `ctx` passed to
`Begin` affects only the `BEGIN`; a transaction abandoned by a cancelled request holds its locks
and its connection until something rolls it back. So every transaction runs through
`pgx.BeginFunc` or `pgx.BeginTxFunc`, which commit when the function returns `nil` and roll back
on an error or a panic:

```go
err := pgx.BeginTxFunc(ctx, s.pool, pgx.TxOptions{IsoLevel: pgx.Serializable}, func(tx pgx.Tx) error {
	if err := s.orders.Save(ctx, tx, order); err != nil {
		return err
	}
	return s.outbox.Append(ctx, tx, OrderPlaced{OrderID: order.ID})
})
```

- **A repository method that can join a transaction takes the executor**, an interface the
  repository's package declares with only what it calls — `Exec`, `Query`, `QueryRow` — which both
  `*pgxpool.Pool` and `pgx.Tx` satisfy.
- **A serialization failure or deadlock** — `pgerrcode.SerializationFailure`,
  `pgerrcode.DeadlockDetected` — **retries the whole `BeginTxFunc`**, with a small budget; nothing
  inside the function retries.
- **A hand-written `Begin` is followed by a deferred rollback whose error is discarded on purpose** —
  `defer func() { _ = tx.Rollback(ctx) }()`, since errcheck rejects a bare `defer tx.Rollback(ctx)`.
  After a successful `Commit` it is a no-op returning `pgx.ErrTxClosed`.

```go
// WRONG — an early return leaves the transaction open, holding its locks and its connection
tx, err := s.pool.Begin(ctx)
if err != nil {
	return fmt.Errorf("begin transaction: %w", err)
}
if err := s.orders.Save(ctx, tx, order); err != nil {
	return fmt.Errorf("place order %s: %w", order.ID, err)
}

// CORRECT — rolled back on every path that does not reach Commit
tx, err := s.pool.Begin(ctx)
if err != nil {
	return fmt.Errorf("begin transaction: %w", err)
}
defer func() {
	_ = tx.Rollback(ctx) // a no-op after Commit; a failed rollback closes the connection
}()
if err := s.orders.Save(ctx, tx, order); err != nil {
	return fmt.Errorf("place order %s: %w", order.ID, err)
}
```

## Bulk Work

- **`CopyFrom` for thousands of rows** — an order of magnitude faster than inserts, inside a
  transaction when it must be all or nothing.

```go
// WRONG — one round trip per line: 10 000 lines are 10 000 INSERTs
for _, line := range lines {
	if _, err := tx.Exec(ctx, insertOrderLine, line.OrderID, line.SKU, line.Quantity); err != nil {
		return fmt.Errorf("insert order line %s: %w", line.SKU, err)
	}
}

// CORRECT — one COPY streams every row
columns := []string{"order_id", "sku", "quantity"}
_, err := tx.CopyFrom(ctx, pgx.Identifier{"order_lines"}, columns,
	pgx.CopyFromSlice(len(lines), func(i int) ([]any, error) {
		return []any{lines[i].OrderID, lines[i].SKU, lines[i].Quantity}, nil
	}))
if err != nil {
	return fmt.Errorf("copy %d order lines: %w", len(lines), err)
}
```

- **A `pgx.Batch` for many small independent statements in one round trip**: queue them,
  `SendBatch`, read every result in order, and `Close` the results, whose error is the first
  failure.

```go
// WRONG — nothing reads the results: every failure is lost, and the connection never returns to
// the pool
s.pool.SendBatch(ctx, batch)

// CORRECT — Close reads every result still unread and returns the first failure
if err := s.pool.SendBatch(ctx, batch).Close(); err != nil {
	return fmt.Errorf("set order statuses: %w", err)
}
```

## Tracing

- **Query tracing is `config.ConnConfig.Tracer`** — `tracelog.TraceLog` with a logger adapter, or an
  OpenTelemetry tracer — configured in the root, never by wrapping the pool.

## Tests

- **Repositories are tested against a real PostgreSQL** — a container started by the test suite or
  the project's compose file — with each test in its own transaction or schema. A mocked pool
  proves only that the mock was called (`testing.md`).

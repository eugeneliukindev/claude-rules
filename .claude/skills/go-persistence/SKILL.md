---
name: go-persistence
description: >-
  Go persistence with database/sql or a driver-native pool: one use case per transaction, a
  WithinTx helper owning commit and rollback, nothing slow or irreversible inside a transaction,
  rows scanned into domain types at the repository boundary, rows.Close and rows.Err, N+1 treated
  as an error, nullable columns, pool settings. Use when Go code imports database/sql or a SQL
  driver, opens a transaction, writes a repository or scans rows; schema changes are in
  go-migrations.
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

```go
// WRONG — published before the commit: a rollback leaves subscribers holding an order that
// never existed
err := s.store.WithinTx(ctx, func(tx *sql.Tx) error {
	if err := s.orders.Save(ctx, tx, order); err != nil {
		return err
	}
	return s.publisher.Publish(ctx, OrderPlaced{OrderID: order.ID})
})

// CORRECT — the event is a row in the same transaction; a relay publishes it once committed
err := s.store.WithinTx(ctx, func(tx *sql.Tx) error {
	if err := s.orders.Save(ctx, tx, order); err != nil {
		return err
	}
	return s.outbox.Append(ctx, tx, OrderPlaced{OrderID: order.ID})
})
```

- **A deadlock or serialization failure retries the whole use case**, from `BeginTx`, with a small
  bounded budget — never one statement inside the failed transaction, which the database has
  already aborted. The driver's error code says which failures are retryable.

```go
// WRONG — the statement is retried inside a transaction the database has already aborted
err := s.store.WithinTx(ctx, func(tx *sql.Tx) error {
	var err error
	for range maxAttempts {
		if err = s.stock.Reserve(ctx, tx, order.Lines); !isRetryable(err) {
			break
		}
	}
	return err
})

// CORRECT — the whole use case runs again, from BeginTx
var err error
for range maxAttempts {
	err = s.store.WithinTx(ctx, func(tx *sql.Tx) error {
		return s.stock.Reserve(ctx, tx, order.Lines)
	})
	if !isRetryable(err) {
		break
	}
}
```

- **Every query takes the `ctx`** — `QueryContext`, `ExecContext`, `QueryRowContext`. The forms
  without it ignore the request's deadline and cancellation; `noctx` reports them.

## Repositories and the Domain

- **A repository speaks domain types**: `Find(ctx, id OrderID) (Order, error)`, `Save(ctx, Order)
  error`. The row shape, the SQL and the driver's errors stay inside it; `sql.ErrNoRows` becomes the
  package's `ErrNotFound`, a unique violation becomes `ErrAlreadyExists`.
- **A repository method that must join a caller's transaction takes the executor**: an interface
  with `ExecContext`, `QueryContext` and `QueryRowContext`, satisfied by both `*sql.DB` and
  `*sql.Tx`.

```go
// WRONG — r.db is the pool: the insert commits on a connection of its own, outside the caller's
// transaction, and stays when that transaction rolls back
func (r *Repository) Save(ctx context.Context, order Order) error {
	if _, err := r.db.ExecContext(ctx, insertOrder, order.ID, order.CustomerID); err != nil {
		return fmt.Errorf("save order %s: %w", order.ID, err)
	}
	return nil
}

// CORRECT — the caller passes the pool or its transaction, and the insert joins whichever it is
type executor interface {
	ExecContext(ctx context.Context, query string, args ...any) (sql.Result, error)
	QueryContext(ctx context.Context, query string, args ...any) (*sql.Rows, error)
	QueryRowContext(ctx context.Context, query string, args ...any) *sql.Row
}

func (r *Repository) Save(ctx context.Context, db executor, order Order) error {
	if _, err := db.ExecContext(ctx, insertOrder, order.ID, order.CustomerID); err != nil {
		return fmt.Errorf("save order %s: %w", order.ID, err)
	}
	return nil
}
```

- **Scan into a row struct, then convert** — the conversion validates and is where a corrupt row is
  reported with its key, instead of a domain object built half-right.
- **Nullable columns** scan into `sql.Null[T]` in the row struct and become a domain zero value, a
  `(T, bool)`, or an error during conversion — a pointer does not leak into the domain.

```go
// WRONG — scanned straight into the domain: any string is a status, and a NULL needs a pointer
var order Order
err := r.db.QueryRowContext(ctx, selectOrderByID, id).
	Scan(&order.ID, &order.Status, &order.ShippedAt)

// CORRECT — scanned into the row shape; toOrder validates and decides what NULL means
var row orderRow
err := r.db.QueryRowContext(ctx, selectOrderByID, id).
	Scan(&row.id, &row.status, &row.shippedAt)

type orderRow struct {
	id        string
	status    string
	shippedAt sql.Null[time.Time]
}

func (row orderRow) toOrder() (Order, error) {
	status, err := ParseOrderStatus(row.status)
	if err != nil {
		return Order{}, fmt.Errorf("order %s: %w", row.id, err)
	}
	return Order{ID: OrderID(row.id), Status: status, ShippedAt: row.shippedAt.V}, nil
}
```

- **`rows.Close` deferred, and `rows.Err` checked after the loop.** A loop that ends early because
  the connection dropped looks exactly like one that ran out of rows until `Err` is read;
  `sqlclosecheck` and `rowserrcheck` catch both.
- **Name the columns.** `SELECT *` breaks every `Scan` the day a column is added, in the order the
  database chooses.
- **N+1 is an error, not a performance tweak.** A query inside a loop over the results of another
  query is one `JOIN` or one `WHERE id = ANY($1)`; the loop's length is the page size today and the
  table size next year.

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

- **Every list query has a `LIMIT`**, and pagination is keyset (`WHERE (created_at, id) > ($1, $2)`)
  wherever the table grows — `OFFSET` reads and discards every skipped row.

```go
// WRONG — OFFSET reads and discards every row before the page: page 1 000 reads 50 000 rows
const selectOrdersPage = `SELECT id, customer_id, created_at FROM orders
	ORDER BY created_at, id LIMIT $1 OFFSET $2`

// CORRECT — keyset: the index seeks straight past the last row the caller saw
const selectOrdersPage = `SELECT id, customer_id, created_at FROM orders
	WHERE (created_at, id) > ($2, $3) ORDER BY created_at, id LIMIT $1`
```

## Pool

- **One `*sql.DB` per database for the life of the process**, opened in the composition root and
  passed down. It is a pool, safe for concurrent use; opening one per request exhausts the server.
- **Set the limits explicitly** — `SetMaxOpenConns`, `SetMaxIdleConns`, `SetConnMaxLifetime` —
  against the server's connection limit divided by the replicas. The default of unlimited open
  connections becomes a connection storm during the first traffic spike.

```go
// WRONG — the defaults: nothing caps open connections, so a spike opens as many as it asks for
db, err := sql.Open("pgx", settings.databaseURL)
if err != nil {
	return fmt.Errorf("open database: %w", err)
}

// CORRECT — chosen against the server's max_connections divided by the replicas
db, err := sql.Open("pgx", settings.databaseURL)
if err != nil {
	return fmt.Errorf("open database: %w", err)
}
db.SetMaxOpenConns(settings.databaseMaxConns)
db.SetMaxIdleConns(settings.databaseMaxConns)
db.SetConnMaxLifetime(30 * time.Minute)
```

- **`db.PingContext` at startup with a deadline**, so a wrong DSN fails the deploy instead of the
  first request.

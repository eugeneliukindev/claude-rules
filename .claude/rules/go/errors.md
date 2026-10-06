---
paths:
  - "**/*.go"
---

# Go — Errors and Logging

## Errors

The example below carries the four broken most often: wrapping with what this call was doing, a
driver's error translated, `errors.Is` instead of `==`, and never `nil, nil` as "absent".

- **Every error is handled exactly once**: returned with context, translated, or logged by the
  code that decides what happens next — never logged *and* returned, which prints the same failure
  once per layer. `_ = f()` is a decision and carries its reason on the line.
- **Wrap with what this function was doing, not with what failed**: `fmt.Errorf("load user %s:
  %w", id, err)`. Lower-case, no trailing punctuation, no "failed to" or "error" — the chain reads
  as one sentence: `charge order 42: load user 7: connection refused`. The callee's own message is
  not repeated.
- **`%w` makes the wrapped error part of your API; `%v` keeps it private.** Wrap what callers may
  branch on. A driver's error crossing a package boundary is translated into this package's own —
  `sql.ErrNoRows` becomes `ErrNotFound` — or every caller now depends on the driver.
- **A package's errors are sentinels or types, never strings to match.** `var ErrNotFound =
  errors.New("order not found")` when the caller only needs to know which; a `*ValidationError`
  with fields when it needs the data. Callers test with `errors.Is` and `errors.AsType`, never with
  `==`, a type assertion or `strings.Contains(err.Error(), …)`.
- **Never `nil, nil`.** A function whose name promises a value returns it or an error; absence that
  is normal is `(T, bool)` or `ErrNotFound`, chosen once per codebase.
- **`panic` is for a bug in this program**, never for an input, a missing file or a dead network,
  and never part of an API — except a `Must` function, for initialisation from a constant input.

```go
// WRONG — the driver's error leaks, nil, nil means absent (so the result is a pointer), and the
// error is logged and returned

// Find returns the order with the given ID, or nil if there is none.
func (r *Repository) Find(ctx context.Context, id OrderID) (*Order, error) {
	var o Order
	err := r.db.QueryRowContext(ctx, selectOrderByID, id).Scan(&o.ID, &o.Status)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		r.logger.ErrorContext(ctx, "query failed", "error", err)
		return nil, err
	}
	return &o, nil
}

// CORRECT — absence is this package's sentinel; the rest is wrapped with what was being done

// Find returns the order with the given ID, or an error wrapping [ErrNotFound].
func (r *Repository) Find(ctx context.Context, id OrderID) (Order, error) {
	var o Order
	err := r.db.QueryRowContext(ctx, selectOrderByID, id).Scan(&o.ID, &o.Status)
	if errors.Is(err, sql.ErrNoRows) {
		return Order{}, fmt.Errorf("find order %s: %w", id, ErrNotFound)
	}
	if err != nil {
		return Order{}, fmt.Errorf("find order %s: %w", id, err)
	}
	return o, nil
}
```

The second `%w` still exposes the driver's error — right in an application, where every caller is
yours; a library writes `%v` there.

## Logging

- **`log/slog`, with a `*slog.Logger` injected like any other dependency.** `slog.Default()` and the
  package-level `slog.Info` are for `main` and nothing else; a library never configures logging,
  and never logs where it could return an error instead.
- **The message is a constant, the data is attributes**: `logger.InfoContext(ctx, "payment
  captured", "order_id", id, "amount_cents", amount)`. Lower-case, event first, no punctuation, no
  values formatted into the string — a message that varies cannot be counted or searched. One
  style of attributes per codebase, key-value or `slog.Attr`; `sloglint` holds the line.
- **The `Context` variants always**, so a handler can attach the trace and the request ID the
  context carries.
- **`ERROR` means someone must look** — never for an expected user mistake or a retried timeout.
- **Never log secrets or PII** — tokens, passwords, card numbers, whole request bodies. Log
  identifiers, not structs; a type that holds a secret implements `slog.LogValuer` and returns a
  redacted value, so that logging it by accident is safe.
- **Configure the handler once, in `main`.** Timing and counters are metrics; never log in a hot
  loop.

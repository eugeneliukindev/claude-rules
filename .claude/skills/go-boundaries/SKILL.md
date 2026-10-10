---
name: go-boundaries
description: >-
  Go process boundaries: wire structs validated at the edge versus domain types inside, a deadline
  on every outbound call, what may and may not be retried, idempotency keys, nested retry budgets,
  explicit serialization and payload versioning, and the handling of time, money and identifiers
  with time.Time, integer minor units and the uuid package. Use when Go code talks to HTTP, gRPC,
  a queue, a cache, a database or a file someone else wrote, or when working with time.Time,
  durations, money, UUIDs or any value crossing the process boundary.
paths:
  - "**/*.go"
  - "**/go.mod"
---

# Boundaries

## Wire Types and Domain Types

Two kinds of struct, and the line between them is the boundary:

- **A wire type mirrors someone else's format** — JSON field names, nullable columns, a protobuf
  message. Its fields are whatever the format allows: pointers for "absent", strings for enums,
  tags for names. It lives in the adapter that speaks the format and nowhere else.
- **A domain type states what the program believes**: defined types, validated values, no tags,
  no pointers standing in for optionality. Business logic sees only these.
- **Conversion happens once, in the adapter, and it is where validation lives.** `toDomain(w
  orderPayload) (Order, error)` checks every rule the format could not, and returns a
  `*ValidationError` naming the field. Past that function, nothing re-validates.
- **A domain type never grows a JSON tag to save a struct.** The day the wire format renames a
  field, the domain renames with it — or a tag starts lying.

```go
// WRONG — the domain type is the wire type: it carries tags, and a missing quantity decodes as 0
type Order struct {
	ID       OrderID `json:"id"`
	Quantity int     `json:"quantity"`
}

// CORRECT — the wire type mirrors the format; toDomain is the one place it is validated
type orderPayload struct {
	ID       string `json:"id"`
	Quantity *int   `json:"quantity"`
}

func (p orderPayload) toDomain() (Order, error) {
	id, err := ParseOrderID(p.ID)
	if err != nil {
		return Order{}, &ValidationError{Field: "id", Err: err}
	}
	if p.Quantity == nil || *p.Quantity <= 0 {
		return Order{}, &ValidationError{Field: "quantity", Err: ErrNotPositive}
	}
	return Order{ID: id, Quantity: *p.Quantity}, nil
}
```

## Outbound Calls: Deadlines, Retries, Idempotency

**Every call that leaves the process has a deadline.** `http.Client{}` with no `Timeout` waits
forever; a `context.Background()` passed to a driver waits as long as the driver does. The
deadline comes from the caller's `ctx` — a request inherits its server's — and an adapter adds a
tighter one for its own call when the dependency is known to be slow:
`ctx, cancel := context.WithTimeout(ctx, 2*time.Second)`; `defer cancel()`.

```go
// WRONG — Background drops the caller's deadline: the call waits as long as the dependency does
price, err := c.pricing.Quote(context.Background(), sku)

// CORRECT — the caller's deadline, tightened for a dependency known to be slow
ctx, cancel := context.WithTimeout(ctx, quoteTimeout)
defer cancel()
price, err := c.pricing.Quote(ctx, sku)
```

**What may be retried:**

- **Retried**: a connection refused, a reset before any response, `429`, `502`, `503`, `504`, a
  deadline on *this attempt* while the overall budget remains — and only for an operation that is
  idempotent or carries an idempotency key.
- **Never retried**: a `4xx` other than `408`/`429` — the request is wrong, and repeating it is
  wrong again; a `context.Canceled` — the caller has gone; a non-idempotent call with no key.

```go
// WRONG — retries a 501 that will answer the same forever, and gives up on a 429 that asked for it
func isRetryableStatus(status int) bool {
	return status >= 500
}

// CORRECT — the statuses that say "try again", and only those
func isRetryableStatus(status int) bool {
	switch status {
	case http.StatusRequestTimeout, http.StatusTooManyRequests, http.StatusBadGateway,
		http.StatusServiceUnavailable, http.StatusGatewayTimeout:
		return true
	default:
		return false
	}
}
```

- **One layer retries.** A client library that retries, wrapped by an adapter that retries, called
  by a job that retries, turns three attempts into twenty-seven. Decide which layer owns it and
  turn the others off.
- **Backoff is exponential with full jitter and a cap**, and the total — attempts × timeout +
  waits — fits inside the caller's deadline. A retry loop that outlives its request does work
  nobody will read.

```go
// WRONG — a fixed sleep: clients that failed together retry together, and Sleep ignores ctx
time.Sleep(retryDelay)

// CORRECT — exponential, capped, full jitter, and the wait ends with the caller's context
backoff := min(baseBackoff<<attempt, maxBackoff)
wait := rand.N(backoff) //nolint:gosec // jitter, not a secret
select {
case <-time.After(wait):
case <-ctx.Done():
	return context.Cause(ctx)
}
```

```go
// WRONG — every attempt mints a new key, so the server sees three different charges
for range maxAttempts {
	err = gateway.Charge(ctx, payment.Amount, uuid.New().String())
	// ...
}

// CORRECT — the payment's own ID, minted when the payment was created, is the key
for range maxAttempts {
	err = gateway.Charge(ctx, payment.Amount, payment.ID.String())
	// ...
}
```

The key is minted **once, with the intent** — when the payment row is written — and stored with
it, so a crash between attempts and a retry from a different process both send the same key.

## Serialization

- **Encode and decode through wire types, never through `map[string]any`** or a domain type.
- **Unknown fields are a decision, made per boundary.** Rejecting them catches a client sending
  `amout`; accepting them lets a producer add fields without a coordinated deploy. Public input is
  usually strict; a feed you consume from a partner usually tolerant. The mechanics are in
  `go-json`.
- **A payload that is stored or queued carries a version**, and the reader handles every version
  still in flight. Schema changes are additive: a new optional field, never a renamed one.

```go
// WRONG — no version: the day a field changes meaning, the messages still queued are read as new
type orderPlacedMessage struct {
	OrderID    string `json:"order_id"`
	TotalCents int64  `json:"total_cents"`
}

// CORRECT — the version travels with the payload, and the reader switches on it
type orderPlacedMessage struct {
	Version    int    `json:"version"`
	OrderID    string `json:"order_id"`
	TotalCents int64  `json:"total_cents"`
}
```

- **Size is bounded before parsing**: `http.MaxBytesReader`, `io.LimitReader`. A decoder reading an
  unbounded body is a memory limit an attacker sets.

## Time

- **Instants are `time.Time`, durations `time.Duration`**, never `int64` seconds or a formatted
  string inside the program. Both cross the wire through one explicit format: RFC 3339 with an
  offset, or Unix milliseconds — chosen per protocol and written down.
- **Store and transmit UTC**; convert to a zone only to display, with a `*time.Location` loaded by
  name — `time.LoadLocation("Europe/Berlin")` — never a fixed offset, which is wrong half the year.

```go
// WRONG — +01:00 is Berlin only in winter: from late March to late October it is an hour off
berlin := time.FixedZone("CET", 60*60)

// CORRECT — the zone's rules, daylight saving included
berlin, err := time.LoadLocation("Europe/Berlin")
if err != nil {
	return "", fmt.Errorf("load time zone: %w", err)
}
```

- **Compare with `Equal`, `Before`, `After`, never `==`.** `==` compares the location and the
  monotonic reading too, and two `time.Time` for the same instant can differ in both.

```go
// WRONG — false for the same instant read back from the database, in UTC and without a
// monotonic reading
isSettled := order.PaidAt == payment.CapturedAt

// CORRECT — compares the instants and nothing else
isSettled := order.PaidAt.Equal(payment.CapturedAt)
```

- **Elapsed time for metrics and timeouts uses the real monotonic clock**: `start := time.Now();
  …; time.Since(start)`. A `time.Time` that went through `Round(0)`, a database or JSON has lost
  the monotonic reading, and subtracting it across a clock adjustment gives a negative duration.
- **A decision that depends on the date uses the injected clock** (`functions.md`); a test fixes
  it, and `testing/synctest` makes timers and `time.Sleep` instantaneous and deterministic.

## Money

```go
// WRONG — float64 cannot hold 0.1: 0.1 + 0.2 is 0.30000000000000004
type Price struct {
	Amount   float64
	Currency Currency
}

// CORRECT — integer minor units: 19.99 EUR is 1999
type Price struct {
	MinorUnits int64
	Currency   Currency
}
```

- **Integer minor units with the currency beside them.** Arithmetic on two `Money` values checks
  the currency and returns an error on a mismatch; rounding happens once, at a named point, with a
  stated mode. Where amounts need more precision than minor units — FX rates, tax on fractions of a
  cent — a decimal type, never `float64`.
- **The number of minor units is a property of the currency** — two for EUR, zero for JPY, three
  for KWD — looked up, not assumed.

## Identifiers

- **IDs are defined types** — `type OrderID struct{ uuid.UUID }` or `type OrderID string` — so an
  order ID cannot be passed as a customer ID. Embed the UUID rather than writing `type OrderID
  uuid.UUID`, which drops `String`, `MarshalText` and every other method of `UUID`.

```go
// WRONG — a new defined type drops every method: id.String() no longer compiles, and JSON writes
// the 16 bytes rather than the UUID
type OrderID uuid.UUID

// CORRECT — embedding keeps String, MarshalText, UnmarshalText and the rest
type OrderID struct{ uuid.UUID }
```

- **New identifiers come from the standard `uuid` package** on Go 1.27 and later: `uuid.New()`
  where nothing depends on the order, `uuid.NewV7()` where the ID is a database key and insertion
  order should follow creation time. Before 1.27, the same API from a maintained module.
- **An ID from outside is parsed, not trusted**: `uuid.Parse` at the boundary, and the error names
  the field.
- **An ID is not a secret.** A V7 ID leaks its creation time, any ID leaks in logs and URLs.
  Capability-bearing tokens are `crypto/rand.Text()` — see `go-security`.

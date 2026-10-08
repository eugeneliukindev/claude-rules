---
name: go-types
description: >-
  Go type design decisions: the precision ladder from a bare string to a defined type, an iota
  enum, a validated value type and a closed set of variants; generics versus interfaces, type
  parameter constraints and the limits of generic methods; narrowing any with type switches;
  iterators with iter.Seq and range-over-func; and the checks that enforce them. Use when choosing
  a representation for a Go value, writing a generic function or type, replacing a map[string]any,
  modelling "one of several kinds", or writing a function that yields a sequence.
---

# Types — Reference

`types.md` holds what applies to every edit; this is the reasoning behind it and the cases that
need more than a line.

## The Precision Ladder

Every value sits on a ladder, and the right rung is the lowest one that makes the wrong value
unrepresentable — or, where Go cannot do that, catches it at the one place values enter:

1. **A bare primitive** — `string`, `int64`. Right only for a value with no rules: free text, a
   count.
2. **A defined type** — `type OrderID string`, `type Cents int64`. Costs nothing at run time and
   stops every swap of two IDs at compile time. Methods attach here: `func (c Cents) String()`.
3. **An enum** — a defined type with `iota` constants and an invalid zero.
4. **A value type with a constructor** — unexported fields, `NewEmail(raw) (Email, error)`, value
   receivers. Every `Email` in the program was validated once, at the boundary.
5. **A closed set of variants** — a sealed interface with one struct per variant, switched
   exhaustively.

```go
// WRONG — every field a primitive: any string is a status, any int a price in any unit
type Order struct {
	ID       string
	Status   string
	Price    int
	Customer string
}

// CORRECT — every field at its narrowest honest type
type Order struct {
	ID       OrderID
	Status   OrderStatus
	Price    Cents
	Customer CustomerID
}
```

A defined type does **not** stop a conversion: `OrderID(userInput)` compiles. What it stops is the
accident — passing a `CustomerID` where an `OrderID` was meant. The deliberate conversion belongs
in exactly one parsing function at the boundary.

Rung 4 closes that gap for a value with rules: the conversion itself is unavailable.

```go
// WRONG — an exported field: Email{Address: "not an email"} compiles, and nothing validated it
type Email struct {
	Address string
}

// CORRECT — the field is unexported, so NewEmail is the only way to an Email
type Email struct {
	address string
}

func NewEmail(raw string) (Email, error) {
	parsed, err := mail.ParseAddress(raw)
	if err != nil {
		return Email{}, fmt.Errorf("parse email %q: %w", raw, ErrInvalidEmail)
	}
	return Email{address: parsed.Address}, nil
}

func (e Email) String() string {
	return e.address
}
```

## Enums

```go
type OrderStatus int

const (
	OrderStatusUnknown OrderStatus = iota // the zero value: an order nobody set a status on
	OrderStatusPending
	OrderStatusPaid
	OrderStatusShipped
)
```

- **The zero value is `Unknown` or invalid.** A zero that means `Pending` is the status every
  struct built without one silently gets, and the bug looks like data.
- **`String` is generated**: `//go:generate go tool stringer -type=OrderStatus`, with `stringer` a
  `tool` directive in `go.mod`. Hand-written `String` methods drift from the constants.
- **A wire format stores the name, not the number.** `iota` values renumber when a constant is
  inserted; implement `MarshalText`/`UnmarshalText` and reject unknown names there.

```go
var orderStatusByName = map[string]OrderStatus{
	"pending": OrderStatusPending,
	"paid":    OrderStatusPaid,
	"shipped": OrderStatusShipped,
}

func (s *OrderStatus) UnmarshalText(text []byte) error {
	status, ok := orderStatusByName[string(text)]
	if !ok {
		return fmt.Errorf("unknown order status %q", text)
	}
	*s = status
	return nil
}
```

- **A `string`-based enum** — `type Currency string` with constants — is right when the value is
  already a stable name on the wire and nothing iterates the set.
- **Exhaustiveness is a linter's job**: `exhaustive` reports a `switch` missing a constant. The
  `default` arm still fails, because a value read from outside may be none of them.

## A Closed Set of Variants

Go has no sum type. The idiom is an interface with an unexported marker method, so no other package
can add a variant, and a type switch whose `default` fails:

```go
type PaymentOutcome interface {
	isPaymentOutcome()
}

type Captured struct{ TransactionID string }
type Declined struct{ Reason string }

func (Captured) isPaymentOutcome() {}
func (Declined) isPaymentOutcome() {}

func describe(outcome PaymentOutcome) string {
	switch o := outcome.(type) {
	case Captured:
		return "captured as " + o.TransactionID
	case Declined:
		return "declined: " + o.Reason
	default:
		panic(fmt.Sprintf("unknown payment outcome %T", outcome))
	}
}
```

`gochecksumtype` checks these switches the way `exhaustive` checks enums, given a
`//sumtype:decl` comment on the interface. Reach for this only when the variants carry different
data; when they differ only in a name, it is an enum.

## `any` and Narrowing

- **`any` is a boundary type.** It arrives from a decoder, a `context.Value`, a plugin; it is
  narrowed on the first line and never travels further.
- **Narrow with a type switch or a comma-ok assertion**, and fail with the type in the message:
  `fmt.Errorf("unexpected %T in config", v)`.
- **`map[string]any` is a struct nobody wrote.** Decode into a struct — unknown keys can be
  rejected there, and a missing key is a zero value you can check, not a panic on assertion.

```go
// WRONG — JSON numbers arrive in an any as float64, so this ok is always false
var request map[string]any
if err := json.Unmarshal(body, &request); err != nil {
	return 0, fmt.Errorf("decode search request: %w", err)
}
limit, ok := request["limit"].(int)

// CORRECT — the struct is the schema: "limit": "ten" fails the decode, which names the field
var request searchRequest
if err := json.Unmarshal(body, &request); err != nil {
	return 0, fmt.Errorf("decode search request: %w", err)
}
limit := request.Limit
```

- **`context.Value` carries request-scoped data that crosses APIs** — a trace ID, an
  authenticated principal — under an unexported key type, read through a typed accessor. Never a
  dependency, never an optional parameter.

```go
// WRONG — a string key any package can collide with, and every reader writes its own assertion
ctx = context.WithValue(ctx, "principal", principal)

// CORRECT — an unexported key type no other package can construct, behind two typed functions
type principalKey struct{}

func WithPrincipal(ctx context.Context, principal Principal) context.Context {
	return context.WithValue(ctx, principalKey{}, principal)
}

func PrincipalFrom(ctx context.Context) (Principal, bool) {
	principal, ok := ctx.Value(principalKey{}).(Principal)
	return principal, ok
}
```

## Generics or Interfaces

- **A type parameter when the code is the same for every type**: a container, `slices`-style
  algorithms, a typed cache, a function over `cmp.Ordered`. The test: write it for `int`, then for
  `string` — if only the type names changed, it is generic.
- **An interface when the behaviour differs per type.** `Notifier` has a different `Send` for
  each implementation; a type parameter there is an interface with extra steps.
- **Constraints say what the body needs**, no more: `[T any]` when it only moves values,
  `[T comparable]` for map keys and `==`, `[T cmp.Ordered]` for `<`, `[S ~[]E, E any]` to accept
  and return the caller's named slice type rather than a bare `[]E`.

```go
// WRONG — []T discards the caller's named slice type, and a string key makes every caller format one
func Deduplicate[T any](items []T, key func(T) string) []T

// CORRECT — ~[]E keeps the caller's named type; comparable is exactly what map keys need
func Deduplicate[S ~[]E, E any, K comparable](items S, key func(E) K) S {
	seen := make(map[K]struct{}, len(items))
	unique := make(S, 0, len(items))
	for _, item := range items {
		k := key(item)
		if _, ok := seen[k]; ok {
			continue
		}
		seen[k] = struct{}{}
		unique = append(unique, item)
	}
	return unique
}
```

- **Generic methods exist since Go 1.27 — on concrete types only.** An interface method cannot
  declare type parameters, and a generic method never satisfies an interface method. Write one
  where the receiver's state is needed — `(*Rand).N[Int intType]` is the standard library's —
  and a generic function otherwise.

```go
// WRONG — does not compile: "interface method must have no type parameters"
type BlobStore interface {
	Load[T any](ctx context.Context, key string) (T, error)
}

// CORRECT — the interface stays plain, and the type parameter lives on a function over it
type BlobStore interface {
	Load(ctx context.Context, key string) ([]byte, error)
}

func LoadJSON[T any](ctx context.Context, store BlobStore, key string) (T, error) {
	var value T
	data, err := store.Load(ctx, key)
	if err != nil {
		return value, fmt.Errorf("load %s: %w", key, err)
	}
	if err := json.Unmarshal(data, &value); err != nil {
		return value, fmt.Errorf("decode %s: %w", key, err)
	}
	return value, nil
}
```

- **Do not make a type generic to avoid writing two small functions.** A type parameter on a
  struct infects every signature that mentions it.

## Iterators

A function returning `iter.Seq[V]` or `iter.Seq2[K, V]` is ranged over directly, and the caller's
`break` stops the producer.

- **Return an iterator when the caller may stop early or the source is unbounded** — pages of an
  API, rows of a file, a tree walk. Return a slice when the caller always wants everything and the
  size is small; `slices.Collect` turns one into the other.
- **An iterator that can fail yields `iter.Seq2[V, error]`**, or stores the error for an `Err()`
  method read after the loop, as `bufio.Scanner` does. Pick one shape per codebase.
- **The yield result is obeyed**: when `yield` returns `false`, the producer returns at once —
  ignoring it panics at run time.

```go
// WRONG — yield's result is ignored: after the caller's break, the next yield panics with
// "range function continued iteration after function for loop body returned false"
func (b *Batch) Pending() iter.Seq[Order] {
	return func(yield func(Order) bool) {
		for _, order := range b.orders {
			if order.Status == OrderStatusPending {
				yield(order)
			}
		}
	}
}

// CORRECT — a false from yield ends the producer at once
func (b *Batch) Pending() iter.Seq[Order] {
	return func(yield func(Order) bool) {
		for _, order := range b.orders {
			if order.Status == OrderStatusPending && !yield(order) {
				return
			}
		}
	}
}
```

- **Iterator names follow the standard library's** — the family in `naming.md`.

```go
// All yields the orders page by page, fetching the next page only when the caller asks for it.
func (c *Client) All(ctx context.Context) iter.Seq2[Order, error] {
	return func(yield func(Order, error) bool) {
		cursor := ""
		for {
			page, err := c.fetchPage(ctx, cursor)
			if err != nil {
				yield(Order{}, err)
				return
			}
			for _, order := range page.Orders {
				if !yield(order, nil) {
					return
				}
			}
			if page.NextCursor == "" {
				return
			}
			cursor = page.NextCursor
		}
	}
}
```

## Enforcement

| Check | What it catches |
|---|---|
| `exhaustive` | a `switch` over an enum missing a constant |
| `gochecksumtype` | a type switch over a sealed interface missing a variant |
| `forcetypeassert` | a one-value type assertion that panics on the input nobody tested |
| `govet` `composites` | an unkeyed literal of a struct from another package |
| `modernize` / `go fix` | `interface{}`, hand-written `min`, `reflect.TypeOf` where `TypeFor` fits |
| `unconvert` | a conversion to the type the value already has |

---
name: go-json
description: >-
  encoding/json and encoding/json/v2 practice: wire structs with explicit tags, omitzero versus
  omitempty, the defaults that differ between v1 and v2 (duplicate names, case-insensitive
  matching, nil slices, invalid UTF-8, time.Duration), rejecting unknown fields, large integers,
  custom MarshalText and MarshalJSON methods, streaming with jsontext, and bounded input. Use when
  Go code imports encoding/json, encoding/json/v2 or encoding/json/jsontext, writes json struct
  tags, implements a marshaler, or decodes a request or response body.
---

# JSON

The boundary rules — wire types versus domain types, versioning, size limits — are in
`go-boundaries`. This is the mechanics.

## Which Package

Since Go 1.27 `encoding/json` is implemented on top of `encoding/json/v2` but **keeps v1's
behaviour**; `encoding/json/v2` is the new API with different defaults. Both read the same struct
tags. New code on a 1.27 floor uses v2 for its stricter defaults; existing code keeps v1 until its
tests have been run against v2's semantics. Mixing the two over one wire type is how the same
payload decodes differently in two services.

| Behaviour | `encoding/json` (v1) | `encoding/json/v2` |
|---|---|---|
| duplicate object names | accepted, last wins | rejected |
| field name matching | case-insensitive | case-sensitive (`case:ignore` per field) |
| nil slice / nil map | `null` | `[]` / `{}` |
| invalid UTF-8 | replaced with U+FFFD | rejected |
| `omitempty` omits | `false`, `0`, `""`, nil, empty slice/map | what encodes as `""`, `null`, `[]`, `{}` |
| unknown members | ignored | ignored |
| `time.Duration` | integer nanoseconds | **error**: no default representation |

The first four are why v2 is safer at a trust boundary: a duplicate name or a case variant is how
two services that both "validated" a payload end up disagreeing about what it said.

## Wire Structs

- **Every field has an explicit tag** with its wire name — `json:"customer_id"`. An untagged field
  is named by its Go identifier, so renaming the field renames the API. `musttag` and
  `tagliatelle` hold the line and the naming style.
- **`omitzero` over `omitempty`**, in both packages: it omits the Go zero value or a value whose
  `IsZero()` reports true — so it works for `time.Time` and `netip.Addr`, where `omitempty` never
  omits — and it means the same in v1 and v2, where `omitempty` does not (the table above).
- **Absent and zero are different only where the format says so.** A `*int` or a `json:",omitzero"`
  on a field the API documents as optional; a plain `int` everywhere else.
- **Durations cross the wire in a stated unit**: `TimeoutMillis int64 \`json:"timeout_ms"\``, or a
  defined type implementing `MarshalText` as `time.Duration.String()`. A bare `time.Duration`
  encodes as nanoseconds in v1 and fails in v2.
- **A large integer is a string on the wire** — `json:",string"` — when the other side might be a
  language whose numbers are `float64`, which loses precision past 2^53.

  ```go
  // WRONG — a JavaScript client reads the ID 9007199254740993 as 9007199254740992
  type paymentPayload struct {
  	ID int64 `json:"id"`
  }

  // CORRECT — the digits travel as a string, and both sides parse them exactly
  type paymentPayload struct {
  	ID int64 `json:"id,string"`
  }
  ```
- **`json:"-"` on every field that must never be serialized** — a secret, a cache, an internal
  flag. Better still, keep such fields off wire types altogether.

```go
// WRONG — the interval has no unit on the wire, and omitempty never omits a time.Time
type subscriptionPayload struct {
	ID        string        `json:"id"`
	Interval  time.Duration `json:"interval"`
	StartedAt time.Time     `json:"started_at,omitempty"`
}

// CORRECT — the unit is in the name, and omitzero omits the zero time
type subscriptionPayload struct {
	ID              string    `json:"id"`
	IntervalSeconds int64     `json:"interval_seconds"`
	StartedAt       time.Time `json:"started_at,omitzero"`
}
```

## Decoding Input

- **Unknown fields are rejected at a public input** — `jsonv2.RejectUnknownMembers(true)`, or
  `Decoder.DisallowUnknownFields()` in v1 — so a typo fails loudly instead of being a default.
  A feed you consume from someone else usually stays tolerant; the choice is per boundary.

  ```go
  // WRONG — {"quantiy": 3} decodes as quantity 0, and the typo becomes an order for nothing
  err := jsonv2.UnmarshalRead(body, &request)

  // CORRECT — an unknown member is an error the client sees
  err := jsonv2.UnmarshalRead(body, &request, jsonv2.RejectUnknownMembers(true))
  ```
- **One value per body.** After decoding, a v1 `Decoder` must be checked for trailing data —
  `dec.More()` or a second `Decode` returning `io.EOF` — or `{"a":1}{"a":2}` is accepted.
  `jsonv2.UnmarshalRead` reads exactly one value and rejects anything after it.

  ```go
  // WRONG — {"quantity":1}{"quantity":2} decodes as the first object; the second is never read
  dec := json.NewDecoder(body)
  dec.DisallowUnknownFields()
  if err := dec.Decode(&request); err != nil {
  	return orderRequest{}, fmt.Errorf("decode order request: %w", err)
  }

  // CORRECT — a second Decode must find the end of the body
  dec := json.NewDecoder(body)
  dec.DisallowUnknownFields()
  if err := dec.Decode(&request); err != nil {
  	return orderRequest{}, fmt.Errorf("decode order request: %w", err)
  }
  if err := dec.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
  	return orderRequest{}, errors.New("decode order request: data after the first value")
  }
  ```
- **Never decode into `any` or `map[string]any`** to inspect later. Numbers become `float64` and
  lose precision, and the shape check moves from one place to everywhere the map is read. Where a
  field's shape depends on another field, decode the discriminator into a small struct first, then
  the body into the matching type — or keep the variant raw with `jsontext.Value` until the
  discriminator is known.

  ```go
  // WRONG — every reader re-checks the shape, and amount_cents arrives as a float64
  var event map[string]any
  if err := jsonv2.Unmarshal(data, &event); err != nil {
  	return fmt.Errorf("decode event: %w", err)
  }
  if event["type"] == "order_refunded" {
  	refund, _ := event["data"].(map[string]any)
  	amountCents, _ := refund["amount_cents"].(float64)
  	orderID, _ := refund["order_id"].(string)
  	return refunds.Record(ctx, orderID, int64(amountCents))
  }
  return fmt.Errorf("decode event: unknown type %v", event["type"])

  // CORRECT — the discriminator first; the variant stays raw until its type is known
  type eventPayload struct {
  	Type string         `json:"type"`
  	Data jsontext.Value `json:"data"`
  }

  var event eventPayload
  if err := jsonv2.Unmarshal(data, &event); err != nil {
  	return fmt.Errorf("decode event: %w", err)
  }
  switch event.Type {
  case "order_refunded":
  	var refund refundPayload
  	if err := jsonv2.Unmarshal(event.Data, &refund); err != nil {
  		return fmt.Errorf("decode %s event: %w", event.Type, err)
  	}
  	return refunds.Record(ctx, refund.OrderID, refund.AmountCents)
  default:
  	return fmt.Errorf("decode event: unknown type %q", event.Type)
  }
  ```

## Custom Encoding

- **`MarshalText`/`UnmarshalText` before `MarshalJSON`/`UnmarshalJSON`.** A type that is a string
  on the wire — an ID, an enum, a currency — implements the text pair, and JSON, map keys, flags
  and `slog` all pick it up. The JSON pair is for a type whose wire shape is an object or array.
- **An `UnmarshalText` validates**: an enum rejects unknown names, an ID rejects malformed input.
  Unmarshalling is the boundary, and this method is the only code that sees the raw value.
- **A method on a value receiver for marshalling, a pointer receiver for unmarshalling** — the
  standard library's own shape; a pointer-receiver `MarshalJSON` is silently skipped for map values
  and for anything passed by value.

  ```go
  // WRONG — a pointer receiver: encoding/json (v1) skips it for a status held by value, and
  // json.Marshal(order) writes "status":1
  func (s *OrderStatus) MarshalText() ([]byte, error) {
  	return []byte(s.String()), nil
  }

  func (s *OrderStatus) UnmarshalText(text []byte) error {
  	parsed, err := ParseOrderStatus(string(text))
  	if err != nil {
  		return fmt.Errorf("unmarshal order status: %w", err)
  	}
  	*s = parsed
  	return nil
  }

  // CORRECT — marshalling on the value, unmarshalling on the pointer; an unknown name is an error
  func (s OrderStatus) MarshalText() ([]byte, error) {
  	return []byte(s.String()), nil
  }

  func (s *OrderStatus) UnmarshalText(text []byte) error {
  	parsed, err := ParseOrderStatus(string(text))
  	if err != nil {
  		return fmt.Errorf("unmarshal order status: %w", err)
  	}
  	*s = parsed
  	return nil
  }
  ```
- **v2 adds caller-side marshalers** — `jsonv2.WithMarshalers(jsonv2.MarshalFunc(…))` — to encode
  a type you do not own without wrapping it.

## Streaming

`jsontext.Decoder` and `jsontext.Encoder` work token by token. Use them for a document too large to
hold — an array of a million records read one element at a time — and for transforming JSON without
a Go type. Everything else decodes whole values.

```go
// WRONG — every order is held in memory before the first one is imported
var orders []orderPayload
if err := jsonv2.UnmarshalRead(r, &orders); err != nil {
	return fmt.Errorf("decode orders: %w", err)
}
for _, order := range orders {
	if err := i.save(ctx, order); err != nil {
		return fmt.Errorf("import order %s: %w", order.ID, err)
	}
}

// CORRECT — one element in memory at a time
dec := jsontext.NewDecoder(r)
token, err := dec.ReadToken()
if err != nil {
	return fmt.Errorf("decode orders: %w", err)
}
if token.Kind() != jsontext.KindBeginArray {
	return fmt.Errorf("decode orders: got %v, want an array", token.Kind())
}
for dec.PeekKind() != jsontext.KindEndArray {
	var order orderPayload
	if err := jsonv2.UnmarshalDecode(dec, &order); err != nil {
		return fmt.Errorf("decode orders: %w", err)
	}
	if err := i.save(ctx, order); err != nil {
		return fmt.Errorf("import order %s: %w", order.ID, err)
	}
}
```

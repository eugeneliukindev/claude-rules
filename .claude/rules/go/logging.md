---
paths:
  - "**/*.go"
---

# Go — Logging

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
- **Configure the handler once, in `main`, as `slog.NewJSONHandler`** — logs are JSON. Timing and
  counters are metrics; never log in a hot loop.

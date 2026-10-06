---
name: go-http
description: >-
  Go net/http practice for servers and clients: ServeMux method and wildcard patterns, handlers as
  thin adapters over a service, server timeouts, request body limits, middleware shape, writing
  errors and JSON responses, graceful shutdown; one shared http.Client with a timeout, requests
  built with a context, response bodies always closed and drained, status codes checked, and
  testing with httptest. Use when Go code imports net/http, writes a handler, a middleware, an
  http.Server or an http.Client, or calls an HTTP API.
---

# net/http

The design holds for any router; how gin carries it out, and where it differs, is in `go-gin`.

## Server

**The standard `ServeMux` routes by method and path wildcard** — `mux.HandleFunc("GET
/orders/{id}", h.getOrder)`, then `r.PathValue("id")`. A router dependency is justified by a
feature it has and `ServeMux` does not, not by habit.

**A handler is an adapter.** It decodes the request into a wire type, converts it into domain
input, calls one service method, and encodes the result. Business rules in a handler are rules
that a queue consumer or a CLI cannot reach.

```go
func (h *OrderHandler) getOrder(w http.ResponseWriter, r *http.Request) {
	id, err := ParseOrderID(r.PathValue("id"))
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid order id")
		return
	}

	order, err := h.orders.Find(r.Context(), id)
	if errors.Is(err, ErrNotFound) {
		writeError(w, http.StatusNotFound, "order not found")
		return
	}
	if err != nil {
		h.logger.ErrorContext(r.Context(), "find order failed", "order_id", id, "error", err)
		writeError(w, http.StatusInternalServerError, "internal error")
		return
	}

	writeJSON(w, http.StatusOK, toOrderResponse(order))
}
```

- **Every `http.Server` sets its timeouts.** `ReadHeaderTimeout` at minimum — without it one slow
  client holds a connection open forever (`gosec` G112) — and `ReadTimeout`, `WriteTimeout`,
  `IdleTimeout` chosen for the slowest legitimate request. `http.ListenAndServe(addr, h)` sets
  none of them, so it is for examples only.
- **Bodies are bounded before decoding** (`go-boundaries`), in a handler with
  `r.Body = http.MaxBytesReader(w, r.Body, maxBodyBytes)`.
- **The internal error is logged; the client gets a stable message and a status.** Never
  `err.Error()` in a response — it leaks table names, file paths and the shape of the network.
- **`r.Context()` is the request's lifetime**: it is cancelled when the client goes away, and every
  call the handler makes takes it.
- **Write the status once, headers before it.** `w.WriteHeader` after a `Write` is ignored with a
  log line; set `Content-Type` before either.
- **Middleware is `func(http.Handler) http.Handler`**, composed in one visible place in the root.
  A middleware that wraps `ResponseWriter` implements `Unwrap() http.ResponseWriter`, so
  `http.ResponseController` still reaches `Flush` and deadlines.
- **Browser-facing endpoints that change state are wrapped in `http.CrossOriginProtection`**
  (Go 1.25), which rejects cross-site non-safe requests using `Sec-Fetch-Site` and `Origin`.
- **Shutdown is `server.Shutdown(ctx)` with a deadline**; `ListenAndServe` then returns
  `http.ErrServerClosed`, which is not an error. The pattern is in `go-concurrency`.

## Client

- **One `*http.Client` per destination, built in the root, with `Timeout` set** — or a deadline on
  every request's context. `http.DefaultClient` and `http.Get` have no timeout at all.
- **Requests carry the caller's context**: `http.NewRequestWithContext(ctx, method, url, body)`;
  `noctx` reports the forms without it.
- **The body is closed on every path** — `defer resp.Body.Close()` right after the error check
  (`bodyclose`) — so the connection returns to the pool. Since Go 1.27 `Close` drains what was not
  read; before it, `io.Copy(io.Discard, resp.Body)` first.
- **A response is not a success until its status says so.** `Do` returns `nil` error for a `500`;
  check `resp.StatusCode` and turn anything unexpected into an error that carries the status and a
  bounded prefix of the body.
- **Read with a limit**: `io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes))` — a misbehaving
  server can send gigabytes.
- **The adapter translates**: transport errors and statuses become this package's errors —
  `ErrNotFound`, `*RateLimitedError{RetryAfter}` — and nothing above the adapter imports
  `net/http`. Retries follow `go-boundaries`.

```go
// WRONG — the default client has no timeout, the request no context; the status is ignored,
// and the body is neither closed nor bounded
func (c *Client) FetchUser(ctx context.Context, id UserID) (User, error) {
	endpoint := c.baseURL.JoinPath("users", url.PathEscape(string(id)))
	resp, err := http.Get(endpoint.String())
	if err != nil {
		return User{}, fmt.Errorf("fetch user %s: %w", id, err)
	}

	var payload userPayload
	if err := json.UnmarshalRead(resp.Body, &payload); err != nil {
		return User{}, fmt.Errorf("decode user %s: %w", id, err)
	}
	return payload.toDomain()
}

// CORRECT
func (c *Client) FetchUser(ctx context.Context, id UserID) (User, error) {
	endpoint := c.baseURL.JoinPath("users", url.PathEscape(string(id)))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), http.NoBody)
	if err != nil {
		return User{}, fmt.Errorf("build user request: %w", err)
	}
	resp, err := c.http.Do(req)
	if err != nil {
		return User{}, fmt.Errorf("fetch user %s: %w", id, err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return User{}, fmt.Errorf("fetch user %s: %w", id, ErrNotFound)
	}
	if resp.StatusCode != http.StatusOK {
		prefix, _ := io.ReadAll(io.LimitReader(resp.Body, maxErrorBodyBytes)) // best effort, for the message
		return User{}, fmt.Errorf("fetch user %s: status %d: %q", id, resp.StatusCode, prefix)
	}

	var payload userPayload
	if err := json.UnmarshalRead(io.LimitReader(resp.Body, maxResponseBytes), &payload); err != nil {
		return User{}, fmt.Errorf("decode user %s: %w", id, err)
	}
	return payload.toDomain()
}
```

`json` here is `encoding/json/v2`. `JoinPath` does **not** escape: it joins and cleans, so an ID of
`../admin` would leave `/users`. `url.PathEscape` keeps a `/` or `?` inside the ID, and `UserID`
rejects `.` and `..` when it is parsed — both are needed.

## Testing

- **A handler is tested with `httptest.NewRecorder` and `httptest.NewRequest`** — no network, no
  port — and asserted on the status, the headers and the decoded body.
- **A client is tested against `httptest.NewServer`** serving canned responses, including the
  failures: a `500`, a slow response past the timeout, a truncated body.
- **On Go 1.27, `httptest.NewTestServer` runs inside a `testing/synctest` bubble** over an
  in-memory network, so timeouts are tested without waiting for them.

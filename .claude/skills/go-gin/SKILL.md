---
name: go-gin
description: >-
  gin web framework practice: gin confined to the transport layer, gin.New with chosen middleware
  instead of gin.Default, an http.Server with timeouts instead of engine.Run, trusted proxies set
  so ClientIP cannot be spoofed, c.Request.Context() because *gin.Context never cancels by
  default, ShouldBind instead of Bind, binding tags on wire structs, validator messages translated,
  bounded bodies and unknown fields, error responses in one place, c.Copy for goroutines, and
  testing through engine.ServeHTTP. Use when Go code imports github.com/gin-gonic/gin, writes a
  gin handler, middleware, route group or binding.
paths:
  - "**/*.go"
  - "**/go.mod"
---

# gin

Checked against gin v1.12.0, which needs Go 1.25 or later. Servers, handlers as adapters,
timeouts and shutdown are designed in `go-http`; this is how gin carries them out, and where it
quietly does something else.

## gin Stays in the Transport Layer

- **Handlers are the only code that sees `*gin.Context`.** A handler binds the request, calls a
  service with plain values and a `context.Context`, and writes the response. A service that takes
  a `*gin.Context` cannot be called from a queue consumer, a CLI or a test without an HTTP request.
- **Handlers are methods on a struct holding the services**, and the routes are registered by one
  function — `func registerRoutes(engine *gin.Engine, orders *OrderHandler)` — which tests call too.

## The Engine and the Server

```go
gin.SetMode(gin.ReleaseMode) // process-wide: set once, in main, before any engine exists

engine := gin.New()
engine.Use(gin.Recovery(), accessLog(logger))
if err := engine.SetTrustedProxies(settings.trustedProxyCIDRs); err != nil {
	return fmt.Errorf("set trusted proxies: %w", err)
}
registerRoutes(engine, orderHandler)

server := &http.Server{
	Addr:              settings.listenAddress,
	Handler:           engine,
	ReadHeaderTimeout: 5 * time.Second,
	ReadTimeout:       30 * time.Second,
	WriteTimeout:      30 * time.Second,
	IdleTimeout:       2 * time.Minute,
}
```

- **`gin.New()` and the middleware you chose**, not `gin.Default()`, whose logger writes its own
  text format to stdout beside the application's JSON logs.
- **Never `engine.Run`** — it is `http.ListenAndServe`: no timeouts and nothing to call `Shutdown`
  on. The engine is an `http.Handler`; the server around it is configured and shut down as
  `go-http` and `go-concurrency` describe.
- **Trusted proxies are set explicitly.** By default gin trusts `X-Forwarded-For` from every
  address, so `c.ClientIP()` is whatever the client wrote — a rate limit or an audit log keyed on
  it is keyed on input. `SetTrustedProxies(nil)` when nothing sits in front, the load balancer's
  CIDRs when something does.
- **`gin.SetMode` and the `binding` package variables are process-wide**, so they are set in
  `main`, before the engine is built — never in a handler, a constructor or a test helper that
  runs in parallel.

## Context

**Every call a handler makes takes `c.Request.Context()`, never `c`.** `*gin.Context` implements
`context.Context`, but unless `engine.ContextWithFallback` is set its `Done()` returns `nil` and its
`Deadline()` reports none: a query given `c` keeps running after the client has gone.

```go
// WRONG — c compiles as a context.Context, and is never cancelled
order, err := h.orders.Find(c, id)

// CORRECT — the request's context ends when the client disconnects or the server shuts down
order, err := h.orders.Find(c.Request.Context(), id)
```

- **`*gin.Context` is pooled and reused after the handler returns.** Work that outlives the handler
  gets `c.Copy()` — or better, the values it needs and a context from `context.WithoutCancel`
  (`go-concurrency`), so no gin type crosses the goroutine.

```go
// WRONG — c goes back to gin's pool when the handler returns, and the goroutine reads whichever
// request uses it next
h.tasks.Go(func() {
	ctx, cancel := context.WithTimeout(c, auditTimeout)
	defer cancel()
	if err := h.audit.Record(ctx, c.Param("id"), c.ClientIP()); err != nil {
		h.logger.WarnContext(ctx, "audit record failed", "error", err)
	}
})

// CORRECT — the values are read now; the context keeps the request's values, not its cancellation
id, clientIP := c.Param("id"), c.ClientIP()
detached := context.WithoutCancel(c.Request.Context())
h.tasks.Go(func() {
	ctx, cancel := context.WithTimeout(detached, auditTimeout)
	defer cancel()
	if err := h.audit.Record(ctx, id, clientIP); err != nil {
		h.logger.WarnContext(ctx, "audit record failed", "error", err)
	}
})
```

`h.tasks` is a `*sync.WaitGroup` the root waits on after `Shutdown`, so the goroutine has an owner.

- **Values a middleware attaches** — the authenticated user, the request ID — go into the request's
  context under an unexported key, read through a typed accessor, so the service layer can read
  them without gin. `c.Set` and `c.Get` hand back `any`.

## Binding and Validation

- **`ShouldBindJSON`, never `BindJSON`.** The `Bind` family aborts and writes 400 itself, so the
  status the handler then chooses is silently dropped — a 422 goes out as 400 with the handler's
  body. `Should` returns the error and the handler answers.

```go
// WRONG — BindJSON has already written 400 and aborted: this 422 goes out as a 400
var request createOrderRequest
if err := c.BindJSON(&request); err != nil {
	c.JSON(http.StatusUnprocessableEntity, toBindingProblem(err))
	return
}

// CORRECT — ShouldBindJSON only returns the error, and the handler answers
var request createOrderRequest
if err := c.ShouldBindJSON(&request); err != nil {
	c.JSON(http.StatusUnprocessableEntity, toBindingProblem(err))
	return
}
```

- **Bind into a wire struct**, with `json` and `binding` tags — `binding:"required,min=1"` — never
  into a domain type; the handler converts afterwards (`go-boundaries`).
- **`required` means "not the zero value"**: a `quantity` of `0` or a `bool` of `false` fails it
  before any other rule runs. A field where zero is a legitimate answer is a pointer, or is not
  `required`.

```go
// WRONG — required rejects the zero value, so "is_gift": false fails as if it were missing
type giftRequest struct {
	SKU    string `json:"sku" binding:"required"`
	IsGift bool   `json:"is_gift" binding:"required"`
}

// CORRECT — a pointer: nil is missing, false is an answer
type giftRequest struct {
	SKU    string `json:"sku" binding:"required"`
	IsGift *bool  `json:"is_gift" binding:"required"`
}
```

- **Path and query parameters bind too**: `ShouldBindUri` with `uri:"id"` tags. A field whose type
  validates itself through `encoding.TextUnmarshaler` needs the option spelled out —
  `uri:"id,parser=encoding.TextUnmarshaler"` (gin 1.12). Without it gin assigns the raw string and
  `UnmarshalText` never runs.

```go
// WRONG — gin assigns the raw string: any ID binds, and OrderID.UnmarshalText never runs
type orderURI struct {
	ID OrderID `uri:"id" binding:"required"`
}

// CORRECT — the parser option makes gin call OrderID.UnmarshalText
type orderURI struct {
	ID OrderID `uri:"id,parser=encoding.TextUnmarshaler" binding:"required"`
}
```

- **Unknown JSON fields are rejected by `binding.EnableDecoderDisallowUnknownFields = true`**, set in
  `main` — a process-wide choice, so the per-boundary decision in `go-json` becomes one decision
  for the whole server.
- **The body is bounded by a middleware** that wraps `c.Request.Body` in `http.MaxBytesReader`, and
  the handler answers 413 when the error is an `*http.MaxBytesError`. Built with the `go_json` or
  `sonic` tags, gin's JSON decoder loses that error type, and an oversized body becomes a 400.

```go
// WRONG — an oversized body is answered as if it were malformed
if err := c.ShouldBindJSON(&request); err != nil {
	c.JSON(http.StatusBadRequest, toBindingProblem(err))
	return
}

// CORRECT — the limit's own error is a 413
if err := c.ShouldBindJSON(&request); err != nil {
	if _, ok := errors.AsType[*http.MaxBytesError](err); ok {
		c.JSON(http.StatusRequestEntityTooLarge, errorBody{Message: "request body too large"})
		return
	}
	c.JSON(http.StatusBadRequest, toBindingProblem(err))
	return
}
```

- **Validation errors are translated before they reach the client.** The raw message names Go
  struct fields — `Key: 'createOrderRequest.Quantity' Error:Field validation for 'Quantity' failed
  on the 'required' tag` — which is internal and useless to the caller. In `main`, take the engine
  — `validate, ok := binding.Validator.Engine().(*validator.Validate)` — register a tag-name
  function that returns the `json` name, and map each `validator.FieldError` to the field and the
  rule. The validator caches each struct on first use, so the registration comes before any
  request is bound.

```go
// WRONG — the client reads "Key: 'createOrderRequest.Quantity' Error:Field validation for…"
if err := c.ShouldBindJSON(&request); err != nil {
	c.JSON(http.StatusBadRequest, errorBody{Message: err.Error()})
	return
}

// CORRECT — each failure is named by its JSON field and its rule
if err := c.ShouldBindJSON(&request); err != nil {
	c.JSON(http.StatusBadRequest, toBindingProblem(err))
	return
}

validate.RegisterTagNameFunc(func(field reflect.StructField) string { // in main
	name, _, _ := strings.Cut(field.Tag.Get("json"), ",")
	return name
})

func toBindingProblem(err error) errorBody {
	fieldErrs, ok := errors.AsType[validator.ValidationErrors](err)
	if !ok {
		return errorBody{Message: "malformed request body"}
	}
	body := errorBody{Message: "invalid request"}
	for _, fieldErr := range fieldErrs {
		problem := fieldProblem{Field: fieldErr.Field(), Rule: fieldErr.Tag()}
		body.Fields = append(body.Fields, problem)
	}
	return body
}
```

## Responses and Errors

- **One way to write an error, chosen per codebase**: either the handler calls a `writeError(c,
  err)` helper that maps domain errors to statuses, or it calls `c.Error(err)` and returns, and one
  middleware maps the collected errors after `c.Next()`. Both in one codebase means some errors
  are written twice and some never.
- **A middleware that rejects** — authentication, rate limiting — calls `c.AbortWithStatusJSON` and
  returns; plain `c.JSON` lets the rest of the chain run.

```go
// WRONG — the 401 is written, and the chain runs on: the handler serves an anonymous caller
func requireUser(c *gin.Context) {
	if _, ok := UserFrom(c.Request.Context()); !ok {
		c.JSON(http.StatusUnauthorized, errorBody{Message: "sign in required"})
		return
	}
}

// CORRECT — Abort stops the handlers after this one from running
func requireUser(c *gin.Context) {
	if _, ok := UserFrom(c.Request.Context()); !ok {
		c.AbortWithStatusJSON(http.StatusUnauthorized, errorBody{Message: "sign in required"})
		return
	}
}
```

- **`gin.Recovery` writes a 500 for a panic**; the panic is a bug, logged with the stack, and the
  client gets a stable body — never the panic value.

## Tests

The router is tested through `engine.ServeHTTP` with `httptest.NewRecorder`, using the same
`registerRoutes` the server uses and fakes behind the handlers. `gin.SetMode(gin.TestMode)` once in
`TestMain`. Each test asserts the status, the headers and the decoded body — the three things a
client sees — and covers a binding failure, a domain error and the success path.

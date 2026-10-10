---
name: go-testify
description: >-
  testify practice for Go tests: require for preconditions and assert for independent facets,
  expected before actual, errors checked with ErrorIs and ErrorAs rather than by message, the type
  and monotonic-clock traps in Equal, InDelta for floats, JSONEq and ElementsMatch, Eventually and
  EventuallyWithT without require inside, suites that cannot run in parallel, testify/mock kept
  away from your own interfaces, and the testifylint checks. Use when Go test code imports
  github.com/stretchr/testify — assert, require, suite or mock.
paths:
  - "**/*.go"
  - "**/go.mod"
---

# testify

Checked against testify v1.12.1 and `testifylint` in golangci-lint 2.14. Everything in
`testing.md` still applies — tables, arrange-act-assert, fakes over mocks, errors by identity;
testify replaces the `if got != want { t.Errorf(…) }` lines and nothing else.

## `require` or `assert`

- **`require` when the rest of the test depends on it**, `assert` when it is one independent facet
  of the outcome. An error check is always `require` — the lines after it read a value that is
  zero or `nil` when the call failed, and `assert` lets them run into a nil-pointer panic that
  hides the real failure. `testifylint`'s `require-error` reports `assert.NoError` and friends.
- **`require` only on the test's own goroutine.** It calls `t.FailNow`, which must not be called
  from another goroutine (`go-require`). A goroutine sends its error back on a channel, and the
  test checks it after waiting.

  ```go
  // WRONG — t.FailNow must run on the test's goroutine; from here it ends only this one
  done := make(chan struct{})
  go func() {
  	defer close(done)
  	require.NoError(t, worker.Run(ctx))
  }()
  cancel()
  <-done

  // CORRECT — the goroutine sends its error back, and the test checks it after waiting
  done := make(chan error, 1)
  go func() {
  	done <- worker.Run(ctx)
  }()
  cancel()
  require.NoError(t, <-done)
  ```
- **In a test, a goroutine starts with `wg.Add(1)`, `go` and `defer wg.Done()`, not `wg.Go`.**
  `testifylint`'s `go-require` reads the body of a `go` statement and not the closure handed to
  `wg.Go`, so the shorter form `core.md` asks for hides a `require` on the wrong goroutine from the
  one check that finds it.

## Arguments

- **Expected first, actual second** — `require.Equal(t, want, got)`. The failure message labels
  them, and reversed arguments print a lie (`expected-actual`).
- **`Equal` compares types as well as values.** `assert.Equal(t, 5, total)` fails when `total` is
  an `int64` or a `Cents`, printing `expected: int(5), actual: int64(5)`. Write the expected value
  in the actual's type — `Cents(500)` — rather than reaching for `EqualValues`, which also hides
  a conversion the code under test got wrong.

  ```go
  // WRONG — total is a Cents, so this fails on equal amounts: int(500) is not Cents(500)
  assert.Equal(t, 500, total)

  // CORRECT — the expected value in the actual's type
  assert.Equal(t, Cents(500), total)
  ```
- **Two `time.Time` for the same instant can fail `Equal` with identical output** — one carries a
  monotonic clock reading or a different location and the other does not. Compare instants with
  `assert.WithinDuration(t, want, got, 0)` or `assert.True(t, want.Equal(got), …)`; better still,
  the injected clock returns a fixed value and the test compares to that.

  ```go
  // WRONG — createdAt holds a monotonic reading the stored value lost: the same instant fails
  assert.Equal(t, createdAt, order.CreatedAt)

  // CORRECT — compares the instants, whatever the location or clock reading
  assert.WithinDuration(t, createdAt, order.CreatedAt, 0)
  ```
- **Floats with `InDelta` or `InEpsilon`**, never `Equal` (`float-compare`).
- **Collections with their own assertions**: `Len`, `Empty`, `ElementsMatch` for order-insensitive
  equality, `Subset`, `Contains`. `assert.Equal(t, 3, len(items))` prints two numbers; `assert.Len`
  prints the collection.
- **`JSONEq` for JSON**, which ignores key order and whitespace — never `Equal` on two strings.
- **A message argument only when the subtest name does not already say it.** `t.Run` names the
  case; `require.NoError(t, err, "creating order")` repeats it.

## Errors

```go
// WRONG — Nil on an error, the arguments reversed, and the failure identified by its text
order, err := service.Place(t.Context(), cart)
assert.Nil(t, err)
assert.Equal(t, order.Status, StatusPending)

_, err = service.Place(t.Context(), emptyCart)
assert.EqualError(t, err, "place order: cart is empty")

// CORRECT — require for what later lines need, expected first, the error by identity
order, err := service.Place(t.Context(), cart)
require.NoError(t, err)
assert.Equal(t, StatusPending, order.Status)

_, err = service.Place(t.Context(), emptyCart)
require.ErrorIs(t, err, ErrEmptyCart)
```

- **`ErrorIs` for a sentinel, `ErrorAs` for a type** — then assert the fields the error carries:
  `var validation *ValidationError; require.ErrorAs(t, err, &validation); assert.Equal(t,
  "quantity", validation.Field)`. `error-is-as` reports `assert.True(t, errors.Is(…))`.
- **`EqualError` and `ErrorContains` only for an error the code under test does not own** — a
  third-party error with no sentinel to match. Anywhere else they pin the wording, which is free
  to change, and pass on the wrong error that happens to share it.
- **`NoError`, never `Nil`, for an error** (`error-nil`): the failure then prints the error.

## Waiting

- **`testing/synctest` first** (`go-concurrency`): it makes waiting instant and deterministic.
- **`Eventually` runs its condition on another goroutine**, every tick. The condition reads shared
  state through the same synchronisation the code uses, or `-race` reports the test; and it never
  calls `require` with the test's `t`.
- **`EventuallyWithT` when the condition is several assertions**: the function receives an
  `*assert.CollectT` and asserts against it — `assert.Len(c, sent, 1)` — and only the last tick's
  failures are reported.

  ```go
  // WRONG — require with the test's t, called on the condition's goroutine
  assert.Eventually(t, func() bool {
  	sent := notifier.Sent()
  	require.Len(t, sent, 1)
  	return sent[0].Recipient == "ann@example.com"
  }, time.Second, 10*time.Millisecond)

  // CORRECT — the assertions go to c, and a failed require ends only this tick
  assert.EventuallyWithT(t, func(c *assert.CollectT) {
  	sent := notifier.Sent()
  	require.Len(c, sent, 1)
  	assert.Equal(c, "ann@example.com", sent[0].Recipient)
  }, time.Second, 10*time.Millisecond)
  ```

## Suites

**`suite` does not support parallel tests**, by its own documentation, and its `SetupTest` state
is shared by every method of the struct. Plain test functions with a constructor helper and
`t.Cleanup` give the same setup without either problem. A project that already uses suites keeps
them consistent: no field written by one test method and read by another, and per-test state built
in `SetupTest`, never in `SetupSuite`.

## `testify/mock`

`mock` is the generated-mock style `testing.md` argues against: it records calls and passes
whatever the expectations allowed. Your own interfaces get hand-written fakes. Where a project
already has `mockery` mocks:

- **The test still asserts the outcome** — the returned value, the state the fake or the database
  ends in. `AssertExpectations` alone is a test of the call sequence.
- **Arguments are matched exactly**, not with `mock.Anything` in every slot — an argument nobody
  checks is one the code can get wrong.
- **`.Once()` where a second call would be a bug** — a duplicate charge, a second email.

```go
// WRONG — any amount, any number of times: a double charge of the wrong amount passes
gateway.On("Charge", mock.Anything, mock.Anything).Return(nil)

// CORRECT — the exact amount, exactly once; the context is the one slot left open
gateway.On("Charge", mock.Anything, Cents(1999)).Return(nil).Once()
```

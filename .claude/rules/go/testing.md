---
paths:
  - "**/*_test.go"
  - "**/testdata/**"
  - "**/*test/*.go"
---

# Testing

Supplement to the other Go rules, for writing and reviewing tests. `testing` is the framework and
`go-cmp` compares; a project already using testify keeps it (`go-testify`) — consistency wins.

## Levels

Most tests are unit tests, fewer are integration, and only critical user flows are e2e — that
keeps `go test ./...` fast enough for every change. A test belongs to exactly one level. How they
are separated — a build tag, `testing.Short()`, a directory — is a project decision; that a plain
`go test ./...` runs only the first is not.

- **Unit** — one function or type in isolation, collaborators replaced by in-memory fakes. Every
  new function and type gets them.
- **Integration** — against real infrastructure: a mocked database only proves the mock works.
- **E2e** — complete user-facing flows against a running system, critical paths only.

## Fakes, Not Mocks

- **Every interface a package consumes has a hand-written fake** — an in-memory map or a recorded
  slice, in the test file or an `xxxtest` package beside the code. A fake exercises the behaviour;
  a generated mock records calls and passes whatever the test author expected.
- **At a boundary you do not own, the standard library's doubles come first**: `httptest.NewServer`
  for the network, `fstest.MapFS` for files, `testing/synctest` for the clock.
- **Swapping a package-level `var sendWelcome = smtp.Send` in a test is a design signal**: the
  dependency should have been a field. Fix the constructor.
- **Assert outcomes, not conversations.** Check the fake's state or the return value; call-count
  expectations mirror the implementation line by line, break on every refactor and catch nothing.

```go
// WRONG — a generated mock of our own interface, and the conversation is the assertion
func TestRegisterUserSendsWelcome(t *testing.T) {
	ctrl := gomock.NewController(t)
	notifier := mocks.NewMockNotifier(ctrl)
	notifier.EXPECT().Send(gomock.Any(), Welcome{Recipient: "ann@example.com"}).Return(nil)

	err := RegisterUser(t.Context(), notifier, "ann@example.com")

	if err != nil {
		t.Fatalf("RegisterUser() error = %v", err)
	}
}

// CORRECT — a fake records what was sent, and the outcome is asserted
func TestRegisterUserSendsWelcome(t *testing.T) {
	notifier := &fakeNotifier{}

	err := RegisterUser(t.Context(), notifier, "ann@example.com")

	if err != nil {
		t.Fatalf("RegisterUser() error = %v", err)
	}
	want := []Message{Welcome{Recipient: "ann@example.com"}}
	if diff := cmp.Diff(want, notifier.sent); diff != "" {
		t.Errorf("sent messages mismatch (-want +got):\n%s", diff)
	}
}
```

## Structure

- **Arrange, act, assert**, separated by blank lines — the call under test is found at a glance.
- **Several input/output combinations are one table**, run with `t.Run` per case, each named for
  the scenario in plain words — the name is what a failing run prints and `-run` selects.
- **A failure message names the call, what came back and what was expected, in that order**:
  `t.Errorf("Total(%v) = %v, want %v", prices, got, want)`. `got` before `want`, everywhere.
- **`t.Fatal` when the rest of the test cannot run, `t.Error` otherwise**, and `t.Fatal` only from
  the test's own goroutine.

```go
func TestTotalIncludesTax(t *testing.T) {
	tests := []struct {
		name    string
		prices  []Cents
		taxRate Percent
		want    Cents
	}{
		{name: "two items ten percent tax", prices: []Cents{10000, 5000}, taxRate: 10, want: 16500},
		{name: "empty cart costs nothing", prices: nil, taxRate: 10, want: 0},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Total(tt.prices, tt.taxRate)

			if got != tt.want {
				t.Errorf("Total(%v, %v) = %v, want %v", tt.prices, tt.taxRate, got, tt.want)
			}
		})
	}
}
```

- **Helpers take `t` first and call `t.Helper()`**, releasing what they open with `t.Cleanup`;
  `t.Context()`, `t.TempDir()`, `t.Setenv()` and `t.Chdir()` replace the hand-rolled versions.
- **`t.Parallel()` where the test shares nothing**; it and `-shuffle=on` surface hidden shared state.
- **`package x_test` for black-box tests of the exported API and every `Example`**; in-package tests
  for the rest, as the standard library does.

## Naming and Data

- **Test names are specifications**, one behaviour each: `TestLimiterRejectsWhenBucketIsEmpty`,
  subtests in words. Never `Test1`, `TestHappyPath`, or a name that only repeats the function.
- **An error is checked by identity, never by text**: `errors.Is(err, ErrNotFound)`, or
  `errors.AsType[*ValidationError](err)` and then its fields. A test that asserts `err != nil` alone
  passes on the wrong error.
- **Fixtures are constructors with defaults** — `newOrder(t, withStatus(StatusPaid))` — never a
  package-level `testOrder` a dozen tests share and one mutates. Values relevant to the behaviour
  are explicit in the test; golden files live in `testdata/`, regenerated behind an `-update` flag.
- **Determinism is enforced**: time comes from an injected clock or a `synctest` bubble, randomness
  is seeded, `-race` runs in CI, and waiting polls with a deadline instead of `time.Sleep`.
- **A parser, a decoder or anything fed untrusted bytes gets a `Fuzz` test** seeded with the table's
  inputs; a found failure lands in `testdata/fuzz` and stays as a regression case.

## Coverage

- **Go measures statements, not branches**: an `if` whose condition was never false reads as covered.
- **No single magic number**: domain packages aim at ~100%, adapters are covered by integration
  tests, generated code and `main` are excluded explicitly. The floor only ratchets up.
- **Coverage finds untested code; it is never a target** — a line coloured green proves nothing.

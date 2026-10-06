---
name: go-examples
description: >-
  Standards for Go examples that ship — an Example function in an _test.go file, a README snippet,
  a program under examples/: testable examples with an Output comment, naming that attaches an
  example to its symbol, the smallest complete program, realistic reserved data such as
  example.com, deterministic output, one example per error case, and versioned with the API. Use
  when writing or reviewing a Go Example function, a README code block, or a runnable example
  program that will be published.
---

# Shipped Examples

An example is read more often than the documentation around it, copied more often than any other
code, and trusted completely. A wrong one is a bug in every program that copies it.

## `Example` Functions Are the Default

- **An example lives in `example_test.go`, in `package x_test`**, so it uses only the exported API,
  exactly as a caller would — with the package name in every call.
- **The name attaches it**: `ExampleParse` documents `Parse`, `ExampleClient_Do` the method `Do`,
  `ExampleParse_relativeTime` a second scenario of `Parse` — the suffix after `_` starts lower-case
  and names the scenario. `go doc -ex` lists them, and pkg.go.dev shows each beside its symbol.
- **An example with an `// Output:` comment is a test**: `go test` runs it and fails when the
  output differs. Every example that can print something does, so it cannot rot unnoticed. One
  without output compiles but never runs; that is right only for an example that needs a network
  or a server.
- **`// Unordered output:`** when the order is a map's — never sort in the example only to make it
  testable, which shows the caller a step they do not need.

```go
func ExampleParse() {
	amount, err := money.Parse("19.99 EUR")
	if err != nil {
		log.Fatal(err)
	}
	fmt.Println(amount.Minor(), amount.Currency())
	// Output: 1999 EUR
}
```

`log.Fatal` is right here and nowhere else: an example is a `main` in miniature, and the reader
should see that the error is handled without seeing a handling policy that is not the point.

## What Makes One Good

- **The smallest complete thing.** Every import, every value; nothing elided with `...`. A reader
  pastes it into a file and it runs.
- **Ordered by the caller's goal**: the first example of a package is the call nine users in ten
  came for, not the type the author found most interesting.
- **Realistic, reserved data**: `example.com`, `user@example.com`, `192.0.2.1` (TEST-NET), amounts
  and names that look like the domain — never `foo`, `bar`, `test123`, and never a real company or
  person.
- **Deterministic**: no clock, no randomness, no map iteration in the printed output; where the
  API takes a clock, the example passes a fixed one.
- **One example per error a caller must handle**: `ExampleParse_invalidCurrency` shows the error
  and the `errors.Is` check, so the recovery is as copyable as the success.
- **Follows every rule the rest of the code does** — wrapped errors, a `ctx`, keyed literals. An
  example that cuts a corner teaches the corner.

## README and `examples/`

- **A README block is a copy of an `Example` function or of a program under `examples/`**, never
  written only for the README — then the test suite checks it. A tool or a CI step that extracts
  the blocks and compiles them is the alternative; proofreading is not.
- **A program under `examples/` is a `main` package that builds with `go build ./...`**, has its
  own short README line saying what it shows, and avoids flags unless flags are the point.
- **Examples are versioned with the API**: the change that renames a function updates every
  example in the same commit — which the compiler forces, as long as every example compiles.

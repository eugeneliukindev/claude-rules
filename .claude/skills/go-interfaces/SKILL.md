---
name: go-interfaces
description: >-
  Go interfaces and their implementations: consumer-side declaration, where several
  implementations of one capability live, the compile-time assertion, embedding interfaces and
  structs without leaking an API, optional capabilities discovered by assertion, and where a test
  fake lives. Use when writing a second implementation of something, adding a fake for a test,
  embedding a type, declaring an interface a producer will satisfy, or deciding where the
  implementations of one capability go.
---

# Interfaces and Implementations

When a type earns methods and the core interface rules are in `interfaces.md`; naming is in
`naming.md`. This is what comes after: where the pieces live and how they meet.

## Who Declares the Interface

**The consumer, by default.** A package that needs to send notifications declares a one-method
`Notifier` beside the code that calls it, and every implementation satisfies it without importing
that package. Go's structural typing exists for exactly this: the implementation does not need to
know the consumer's name, so the consumer can be written — and tested — first.

**The producer declares it in two cases, and both are deliberate:**

- **A capability with several implementations the producer ships**, all used through one
  interface by code the producer does not know — `io.Reader`, `hash.Hash`, `fs.FS`. Then the
  interface, its documented contract and the implementations are one package's API.
- **An extension point** — an interface third parties implement so the producer can call them: a
  `database/sql/driver.Driver`, a `slog.Handler`. The producer is the consumer here.

Outside those, an interface exported next to its only implementation is a header file: it doubles
every change and lets nobody substitute anything.

## A Capability and Its Implementations

When the producer does own the interface, one package per capability holds it, and each
implementation that brings its own dependency gets its own package, so importing the interface
never imports a driver:

```
notify/
    notify.go          // Notifier interface, Message, the errors callers test for
    notifytest/        // a fake Notifier other packages' tests can use
    smtpnotify/        // SMTPNotifier — the only package that imports the SMTP client
    slacknotify/       // SlackNotifier — the only package that imports the Slack SDK
```

- **The interface's package imports nothing an implementation needs.** That is what makes the
  split worth having: a new implementation is a new package, no existing file changes, and a
  binary that uses only SMTP never links the Slack SDK.
- **An implementation with no dependency of its own stays in the interface's package** —
  `notify.NewLogNotifier` writing to a `*slog.Logger` costs nothing to import.
- **A helper only one implementation uses is unexported and stays with it** — never in a shared
  `util`.
- **No interface, no group.** An implementation that will only ever be the only one is a single
  concretely named package; the group appears when the second implementation does, or when a test
  needs a fake.

## The Compile-Time Assertion

```go
var _ notify.Notifier = (*SMTPNotifier)(nil)
```

Write it where an implementation must satisfy an interface it never otherwise mentions — a
producer-declared interface, `http.Handler`, `encoding.TextMarshaler`. A method renamed on the
interface then fails at the implementation, not at a call site three packages away. Where the
consumer passes the type to a function taking the interface in the same package, the call already
checks it, and the assertion is noise.

## Embedding

- **Embedding an interface in a struct is a decorator**: the struct overrides some methods and the
  embedded value answers the rest, as `sort.Reverse` wraps a `sort.Interface`. The embedded value
  is never `nil` outside a test fake — calling a method nobody overrode on a `nil` one panics.
- **Embedding a struct promotes its whole method set into your API.** `type Store struct{
  *sql.DB }` hands every caller `Exec`, `Close` and `SetMaxOpenConns`. A named field and the
  methods you mean to expose say what the type is.
- **Embedding interfaces in an interface composes capabilities**: `io.ReadCloser` is `Reader` plus
  `Closer`. Compose only what one consumer genuinely needs together.

## Optional Capabilities

A consumer may check whether a value also implements something more — `io.WriterTo`,
`http.Flusher` — with a comma-ok assertion and fall back when it does not. This is how the
standard library grows behaviour without growing interfaces. **Wrapping a value hides its optional
methods** — the `http.ResponseWriter` case is in `go-http`.

## Fakes

- **A fake satisfying a consumer's interface lives in the consumer's test file** — it is three
  lines, and it is private to the tests that use it.
- **A fake other packages' tests need is exported from an `xxxtest` package** beside the interface
  — `notifytest.Recorder` — as the standard library ships `httptest` and `fstest`. It is built
  from the same contract tests the real implementations run, so it cannot drift.
- **A contract test is one function every implementation runs**: `notifytest.Run(t, newNotifier)`
  exercises the documented behaviour against any constructor. The second implementation is where
  it pays for itself.

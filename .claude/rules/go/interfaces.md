---
paths:
  - "**/*.go"
---

# Go — Interfaces

- **The consumer defines the interface**, in its own package, with only the methods it calls. The
  producer returns its concrete type and declares no interface for it: `orders` takes a
  `PaymentGateway` with one `Charge` method, and the provider's client never hears the name. This is
  what keeps the producer free to grow methods and the consumer free to be tested with a
  three-line fake.
- **Accept interfaces, return structs.** A constructor returning an interface hides the methods the
  caller may need; `ireturn` checks it. The carve-out is a function
  whose whole point is to choose among implementations, and `error`.
- **No interface before a second implementation or a fake needs one** — one declared next to its
  only implementation is a header file. **The smaller, the stronger**: `io.Reader` is one method,
  and a consumer that needs ten methods of a dependency is doing that dependency's work.
- **A compile-time assertion where an implementation must satisfy an interface it never mentions**:
  `var _ http.Handler = (*Router)(nil)`. The failure then arrives at the type, not at a distant
  call site. Where implementations live, embedding, sealed sets and fakes: `go-interfaces`.

---
paths:
  - "**/*.py"
---

# Python — Control Flow

- **Extract any condition with more than two operands into a named predicate.** The linter measures
  the complexity but cannot name the concept:

  ```python
  if order.is_delivered and not order.is_disputed and order.paid_at > cutoff: ...  # WRONG
  if _is_eligible_for_refund(order, cutoff=cutoff): ...  # CORRECT — the name says what they meant
  ```
- **`match` is structural pattern matching, not a `switch`.** Use it to destructure a closed union
  of variants or nested data; not to compare one scalar against constants, and not for two branches.
- **A bare name in a pattern binds, it does not compare**, whatever its case — the one thing about
  `match` worth memorising. Constants in patterns are dotted:

  ```python
  case Order(status=PAID): ...              # WRONG — matches every order and binds PAID
  case Order(status=OrderStatus.PAID): ...  # CORRECT — compares
  ```
- **Every `match` over a union or `Enum` ends with exhaustiveness**: `case _: assert_never(value)`,
  or a named error. A silent fall-through is forbidden.
- **A factory dispatches through a mapping, not through `match`.** Kind in, builder out:
  `_BUILDER_BY_KIND[source.kind](**options)`. Adding a kind is one entry, and the set is readable
  in one place instead of spread over branches.
- **A comprehension holds one transformation; anything more is a loop.** The judgement is about
  how much the reader can hold, not how much fits.
- **Write a generator function for any lazy sequence longer than a one-line expression**, and for
  anything reading from a stream, file, cursor or paginated API.

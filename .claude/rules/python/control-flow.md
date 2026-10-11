---
paths:
  - "**/*.py"
---

# Python — Control Flow

- **Extract a condition into a named predicate when its operands together name a concept the reader
  would otherwise reconstruct**, whatever their count; one that already reads as what it means stays
  inline — `if user is None or user.is_blocked`. The linter counts operands, it cannot name them:

  ```python
  if order.is_delivered and not order.is_disputed and order.paid_at > cutoff: ...  # WRONG
  if _is_eligible_for_refund(order, cutoff=cutoff): ...  # CORRECT — the name says what they meant
  if user is None or user.is_blocked: ...  # CORRECT — inline: it already reads as what it means
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

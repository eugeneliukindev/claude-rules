---
paths:
  - "**/*.py"
---

# Python — Control Flow

### A condition becomes a named predicate when its operands together name a concept

**Why:** the reader would otherwise reconstruct the concept from the operands every time —
`_is_renewable(loan, today=today)` over three `and`-ed fields.
**Except:** a condition that already reads as what it means stays inline, whatever its length —
`if user is None or user.is_blocked`.

### Every `match` over a union or an `Enum` ends with `case _: assert_never(value)`

**Why:** a new variant is then a type error at every `match` that does not handle it; a silent
fall-through returns `None` for it instead. A `match` that only compares one scalar against
constants is an `if` or a mapping.

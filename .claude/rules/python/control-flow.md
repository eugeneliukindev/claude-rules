---
paths:
  - "**/*.py"
---

# Python - Control Flow

- **Turn a condition into a named predicate when its operands together name a concept.** The reader otherwise rebuilds the concept from the operands every time; a condition that already reads as what it means stays inline, whatever its length.
- **End every `match` over a union or an `Enum` with `case _: assert_never(value)`.** A new variant is then a type error at every `match` that misses it, where a fall-through returns `None`.
- **Write a `match` that only compares one scalar against constants as an `if` or a mapping.**

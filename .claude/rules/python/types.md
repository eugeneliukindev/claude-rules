---
paths:
  - "**/*.py"
---

# Python — Types and Data

The decisions behind these are in the `python-types` skill; these apply everywhere.

- **mypy `--strict` clean**, which is what makes the annotations mandatory. `T | None`, never
  `Optional[T]`; on a 3.12+ floor PEP 695 generics (`class Repository[T: Entity]`), never
  `TypeVar` + `Generic`.
- **Parameters take `collections.abc` ABCs, returns are concrete.** `Mapping[str, int]` in,
  `dict[str, int]` out. This is also what handles variance.
- **"Unknown" is spelled `object`, which forces narrowing; `Any` means "stop checking"**, and a
  function *returning* it spreads that silence to every caller. `Any` stays in the one position
  where a library fixes the signature and there is nothing to narrow to.
- **`@dataclass(frozen=True, slots=True, kw_only=True)` by default.** `frozen` is about mutability,
  `slots` about the attribute set, `kw_only` about the call site — the one usually forgotten:
  `Transfer(recipient_id, sender_id, amount)` type-checks and moves the money backwards. Positional
  construction survives only where the order is the concept — `Point(x, y)`, `Range(low, high)`.
  Drop `frozen` only for a genuine aggregate root that must change over time, and say so in its
  name — `Cart`, `Session`; derive copies with `dataclasses.replace()`. A mutable connection URL let
  callers leak changes into each other's connections; making it immutable broke every one of them.
- **`@override` on every overriding method**; `@final` on classes not designed for subclassing;
  `-> Never` on functions that always raise. **`Final` on module- and class-level constants** —
  worth the annotation because the checker then rejects reassignment and infers the literal type;
  a codebase that decides the reverse decides it once, not per constant.
- **`tuple` over `list` for fixed sequences**, `frozenset` over `set`, `MappingProxyType` to expose
  a dict read-only. **Never mutate arguments** — a function that does is named for it and annotated
  `MutableSequence`; everything else copies and returns. **Never return internal mutable state**
  from a getter: field descriptors handed out that way were mutated and reused by callers, and the
  library had to keep supporting it.
- **A string that is user-facing or used twice is a constant** or an `Enum` member. The linter
  catches the magic *number*; a repeated literal string it will not.

---
paths:
  - "**/*.py"
---

# Python — Classes

Functions are the default; a class is an upgrade that must be triggered.

## When a Class Earns Its Place

### A class is written only when one of seven triggers holds

**Why:** a class without one — `__init__` plus one method, only `@staticmethod`s, a box for
constants — adds `self` and a constructor a module or a closure did not need.

1. **State survives between calls** — a pool, a session.
2. **Invariants tie values together** — `Money`: a frozen dataclass.
3. **The behaviour is swappable** — behind a contract, or for a fake.
4. **Three or more functions share two collaborators.**
5. **There is a lifecycle** — acquire and release.
6. **A framework demands it** — `Enum`, `Exception`.
7. **The root builds it with collaborators** — a service, an adapter.

## Composition

### A class inherits only what it is; reuse is composition

**Why:** a class inherits a contract, or a base whose fields and methods it *is*; behaviour wanted
only for its methods — an HTTP call, a retry, a formatter — arrives as a collaborator, because a
base class collecting helpers ties every subclass to all of them and no test can swap one out.
**Except:** a mixin adds behaviour over the class's own contract, holds no state and declares
`__slots__ = ()`.

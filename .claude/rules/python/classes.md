---
paths:
  - "**/*.py"
---

# Python - Classes

## When a Class Earns Its Place

- **Write a function by default, and a class only when one of seven triggers holds.** Without one, `__init__` plus one method, only `@staticmethod`s or a box for constants adds `self` and a constructor a module or a closure did not need.

1. State survives between calls: a pool, a session.
2. Invariants tie values together: `Money`, a frozen dataclass.
3. The behaviour is swappable: behind a contract, or for a fake.
4. Three or more functions share two collaborators.
5. There is a lifecycle: acquire and release.
6. A framework demands it: `Enum`, `Exception`.
7. The root builds it with collaborators: a service, an adapter.

## Composition

- **Inherit only what the class is, and reuse through composition.** Inherit a contract, or a base whose fields and methods the class is; take behaviour wanted only for its methods (an HTTP call, a retry, a formatter) as a collaborator, since a base that collects helpers ties every subclass to all of them and no test can swap one.
- **Write a mixin only to add behaviour over the class's own contract, with no state and `__slots__ = ()`.**

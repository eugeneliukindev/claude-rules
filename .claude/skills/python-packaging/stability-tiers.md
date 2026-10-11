# Stability Tiers

| path | what it promises |
|---|---|
| `yourpkg/` | the public surface, under the deprecation rules (`deprecation.md`) |
| `yourpkg/experimental/` | may change or vanish in any release |
| `yourpkg/deprecated/` | still works, is going away, and says so on use |
| `yourpkg/v1/` | the previous major, shipped alongside for migration |
| `yourpkg/_internal/` | not yours |

### A stability tier is a package, so the import line states the terms

**Why:** a promise in a changelog is read once; one in the import path is re-read at every call
site — `from atlas.experimental.routing import Router` says what the caller depends on. The
tier's `__init__.py` states the contract in one line, as `pydantic/experimental/__init__.py` does:
*"contains potential new features that are subject to change."* Moving between tiers is the
release event, and a move of a file is what a reviewer sees.
**Except:** a tier nobody needs — an application has one surface, and a library usually needs
`_internal/` and nothing more until the first thing it regrets shipping.

**Example:**
```python
# WRONG — atlas/routing.py: the promise lives in a docstring the caller never opens
"""Routing. Experimental: may change in any release."""


@final
class Router:
    def __init__(self, *, graph: RoadGraph) -> None:
        self._graph = graph


# CORRECT — atlas/experimental/routing.py: the path carries the promise, and
# atlas/experimental/__init__.py says it once for the tier
@final
class Router:
    def __init__(self, *, graph: RoadGraph) -> None:
        self._graph = graph
```

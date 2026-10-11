# Hiding a Whole Subsystem

A library's large private area is a sub-package; the facade rules are in `SKILL.md`.

### The private area is `_internal/`, with the underscore

**Why:** the name is the boundary, not a docstring. `pydantic` and `pip` ship `_internal/`. NumPy
shipped `numpy/core/` documented as private but named public; downstream imported from it for
years, and undoing that took a dedicated NEP, compatibility stubs and a lint rule to fix other
people's code.

**Example:**
```text
# WRONG — documented as private, named public: users import from it within a release
atlas/
    __init__.py
    internal/
        __init__.py        # "This package is private."
        geometry.py


# CORRECT — the underscore says it in every import line that reaches in
atlas/
    __init__.py
    _internal/
        __init__.py
        geometry.py
```

### Whether the modules inside repeat the underscore is decided once for the whole area

**Why:** PEP 8 says they need not — *"An interface is also internal if any containing namespace is
internal"* — and `pip` follows it, with plain `cli/` and `models/` inside `_internal/`. `pydantic`
prefixes all twenty-eight (`_fields.py`, `_repr.py`), so a module read on its own, grepped for or
seen in a traceback still says what it is. Either works; a tree where half the modules carry the
prefix leaves nobody able to say which half is deliberate.

**Example:**
```text
# WRONG — some prefixed, some not, and no rule says which
atlas/_internal/
    _geometry.py
    projection.py
    _tiles.py


# CORRECT — one choice, applied to every module in the area
atlas/_internal/
    _geometry.py
    _projection.py
    _tiles.py
```

### The private area's `__init__.py` is empty

**Why:** a facade declares a contract, and there is none to declare here; internal code imports
the module it needs directly. `pydantic/_internal/__init__.py` is zero bytes.

**Example:**
```python
# WRONG — atlas/_internal/__init__.py re-exports, so every internal import loads the whole area
from atlas._internal._geometry import haversine_km
from atlas._internal._projection import to_web_mercator
from atlas._internal._tiles import tile_for

__all__ = ["haversine_km", "tile_for", "to_web_mercator"]


# CORRECT — atlas/_internal/__init__.py is empty; atlas/_routing.py imports what it uses
from atlas._internal._geometry import haversine_km
```

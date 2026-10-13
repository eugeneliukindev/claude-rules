# Hiding a Whole Subsystem

A library's large private area is a sub-package; the facade rules are in `SKILL.md`.

### The private area is `_internal/`, with the underscore

**Why:** the name is the boundary, not a docstring. `pydantic` and `pip` ship `_internal/`. NumPy
shipped `numpy/core/` documented as private but named public; downstream imported from it for
years, and undoing that took a dedicated NEP, compatibility stubs and a lint rule to fix other
people's code.

### Whether the modules inside repeat the underscore is decided once for the whole area

**Why:** PEP 8 says they need not — *"An interface is also internal if any containing namespace is
internal"* — and `pip` follows it, with plain `cli/` and `models/` inside `_internal/`. `pydantic`
prefixes all twenty-eight (`_fields.py`, `_repr.py`), so a module read on its own, grepped for or
seen in a traceback still says what it is. Either works; a tree where half the modules carry the
prefix leaves nobody able to say which half is deliberate.

### The private area's `__init__.py` is empty

**Why:** a facade declares a contract, and there is none to declare here; internal code imports
the module it needs directly. `pydantic/_internal/__init__.py` is zero bytes.

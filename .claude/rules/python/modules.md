---
paths:
  - "**/*.py"
---

# Python — Modules

## Module Layout and Encapsulation

Every module has the same order, so a reader always knows where to look:

1. Module docstring — one line, always.
2. `from __future__ import annotations`, when the target version needs it.
3. Imports.
4. `__all__` — the whole of `__init__.py`; in a package others import, every public module too.
5. **Module-level constants.**
6. Type aliases, `NewType`s, type parameters.
7. Module logger.
8. Exception classes.
9. Contract-ABCs and protocols, then concrete classes, then the models private to this module.
10. Public functions, high-level first — the step-down rule applies to modules as to classes.
11. Private functions, in call order.
12. The `__main__` guard — a single call to `main()`, nothing else.

**Where Python's definition order overrides this one, it wins** — a validator comes before the
type alias built from it. Anything else that will not fit is a seam — a constant derived from a class
means the module holds two things — so **split it** rather than renumber the list.

- **Size is a smell, not a limit.** The linters enforce a ceiling; the seam is your judgement.
- **No executable statements at import time** beyond constants, the logger and its kin — tracer,
  meter, a context variable (`python-observability`) — no network, file reads or settings, which
  make imports slow and order-dependent. **`main()` is a function.**
  ```python
  # WRONG — importing the module reads the environment, and a test cannot import it without one
  _settings = Settings()
  # CORRECT — the entry point builds settings and hands their fields down
  def main() -> None:
      run(timeout_seconds=Settings().timeout_seconds)
  ```

## Every Top-Level Name Not Used Outside Takes an Underscore

Classes, functions, constants and type aliases alike — a settings section only the root holds, a row
shape only its repository builds, a limit only its function reads: `_RetrySettings`, `_OrderRow`,
`_MAX_BATCH_ROWS`. Without the prefix the name reads as surface, and the first outside import makes
it surface for good — a library still serves an internal builder its facade once exposed, with a
warning, years later. A one-off script nobody imports is the exception (`python-scripts`).
**Constants and aliases are the ones missed**: read quietly from a second module, they get two owners.

The test is mechanical — `find_unprefixed_names.py ROOT`, in `python-packaging` — and runs
**after** the move that made a name internal. A name a framework reaches through a decorator (a
route, a command, a fixture) has a caller the search cannot see; the script lists it apart.

## Facade, Public Module, Internal Module

Who imports a module decides its name. The **facade** `__init__.py` — imports and `__all__` only,
and light: no heavy or optional library — carries the vocabulary nearly every importer needs. A
**public module** `package/topic.py` holds what only some need or what pulls a heavy library; an
**internal module** `_topic.py` is for its siblings, renamed public when needed outside, never
reached into. A facade that re-exported everything made a job needing one enum load a browser driver
and an ORM. The decision table: `python-packaging`.

## Imports

- **Import modules for modules, names for classes and functions.** Then call `invoices.issue(...)`
  or `issue_invoice(...)` — never a three-level attribute chain, which hides what is used.
- **A function-level import is flagged, and exactly three reasons buy the suppression**: breaking a
  genuine circular import, loading a heavy or optional implementation on demand, and a facade that
  exports implementations whose libraries are separate extras. Each carries the reason on the line.
  Generic "lazy loading" is not one of them — restructure instead.
- **Annotations that would create a cycle or pull a heavy dependency go under `TYPE_CHECKING`** —
  never one a framework reads at runtime: a pydantic field, a FastAPI parameter (`python-project`).
- **Never depend transitively on something you import**; every direct dependency is declared, with
  a lower bound. **Never feature-detect with `try: import x`** in application code.
- **Anything acquired is released by a context manager** — files, locks, sessions, clients; who
  closes what and failing cleanup are in `python-wiring`.
